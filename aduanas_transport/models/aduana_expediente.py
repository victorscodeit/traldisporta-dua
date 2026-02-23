from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging
import time
from xml.sax.saxutils import escape as xml_escape
_logger = logging.getLogger(__name__)

# Queue job support (opcional)
try:
    from odoo.addons.queue_job.job import job
    QUEUE_JOB_AVAILABLE = True
except Exception:
    QUEUE_JOB_AVAILABLE = False

    def job(func):
        return func

# Solo añadimos el mixin si realmente está disponible en la versión instalada.
_EXPEDIENTE_INHERIT = ["mail.thread", "mail.activity.mixin"]
if QUEUE_JOB_AVAILABLE:
    _EXPEDIENTE_INHERIT.append("queue.job.mixin")

class AduanaExpedienteLine(models.Model):
    _name = "aduana.expediente.line"
    _description = "Línea de mercancía (expediente aduanero)"
    expediente_id = fields.Many2one("aduana.expediente", required=True, ondelete="cascade")
    factura_id = fields.Many2one("aduana.expediente.factura", string="Factura", ondelete="set null", index=True,
                                 help="Factura del expediente de la que proviene esta línea, si aplica")
    item_number = fields.Integer(string="Nº línea", default=1)
    partida = fields.Char(string="Partida arancelaria (NC)")
    descripcion = fields.Char()
    unidades = fields.Float(string="Unidades", default=1.0)
    bultos = fields.Integer(default=1)
    peso_bruto = fields.Float()
    peso_neto = fields.Float()
    valor_linea = fields.Float()
    precio_unitario = fields.Float(string="Precio Unitario")
    descuento = fields.Float(string="Descuento (%)", help="Porcentaje de descuento aplicado a la línea")
    subtotal = fields.Float(string="Subtotal")
    pais_origen = fields.Char(default="ES")
    verificacion_estado = fields.Selection([
        ("pendiente", "Pendiente"),
        ("correcto", "Correcto"),
        ("corregido", "Corregido"),
        ("sugerido", "Sugerido"),
        ("verificado", "Verificado"),
    ], string="Estado verificación", default="pendiente")
    verificacion_detalle = fields.Text(string="Verificación IA/QA")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Calcular precio_unitario automáticamente si no está en los valores (valor_linea es el total)"""
        for vals in vals_list:
            # Calcular precio_unitario desde valor_linea (total) / unidades
            # Solo si no viene de la IA (no está en vals o es None/0)
            if 'precio_unitario' not in vals or vals.get('precio_unitario') is None or vals.get('precio_unitario') == 0:
                if vals.get('valor_linea') and vals.get('unidades') and vals.get('unidades') > 0:
                    # valor_linea es el total, calcular precio unitario
                    descuento = vals.get('descuento', 0) or 0
                    factor_descuento = 1.0 - (descuento / 100.0) if descuento else 1.0
                    # Precio unitario = (total / unidades) * factor_descuento
                    # Pero si ya aplicamos descuento en el total, solo dividir
                    precio_unitario_sin_descuento = vals.get('valor_linea', 0) / vals.get('unidades', 1)
                    vals['precio_unitario'] = precio_unitario_sin_descuento * factor_descuento
        return super().create(vals_list)
    
    def write(self, vals):
        """Recalcular precio_unitario si cambian valor_linea, unidades o descuento"""
        result = super().write(vals)
        
        # Si se modifican campos base y no se está escribiendo precio_unitario directamente
        if any(field in vals for field in ['valor_linea', 'unidades', 'descuento']):
            if 'precio_unitario' not in vals:
                for line in self:
                    # Recalcular precio_unitario desde valor_linea (total) / unidades
                    if line.valor_linea and line.unidades and line.unidades > 0:
                        factor_descuento = 1.0 - (line.descuento / 100.0) if line.descuento else 1.0
                        precio_unitario_sin_descuento = line.valor_linea / line.unidades
                        line.precio_unitario = precio_unitario_sin_descuento * factor_descuento
        
        return result

class AduanaExpediente(models.Model):
    _name = "aduana.expediente"
    _description = "Expediente Aduanero"
    _inherit = _EXPEDIENTE_INHERIT
    _order = "create_date desc"

    name = fields.Char(string="Referencia", required=True, copy=False, readonly=True, default=lambda self: _("Nuevo"))
    direction = fields.Selection([
        ("export", "España → Andorra (Exportación)"),
        ("import", "Andorra → España (Importación)"),
    ], string="Sentido", required=True, default="export", tracking=True)

    # Datos clave (ingresan desde MSoft)
    remitente = fields.Many2one("res.partner", string="Remitente")
    consignatario = fields.Many2one("res.partner", string="Consignatario")
    incoterm = fields.Selection([
        ("EXW", "EXW – En fábrica"),
        ("FCA", "FCA – Free Carrier"),
        ("CPT", "CPT – Carriage Paid To"),
        ("CIP", "CIP – Carriage and Insurance Paid To"),
        ("DAP", "DAP – Delivered At Place"),
        ("DPU", "DPU – Delivered at Place Unloaded"),
        ("DDP", "DDP – Delivered Duty Paid"),
    ], string="Incoterm", default="DAP", tracking=True)
    incoterm_info = fields.Html(string="Información Incoterm", compute="_compute_incoterm_info")
    oficina = fields.Char(string="Oficina Aduanas", help="Ej. 0801 Barcelona")
    transportista = fields.Char(string="Transportista")
    matricula = fields.Char(string="Matrícula")
    fecha_prevista = fields.Datetime()

    # Totales factura (editable; se rellena con la suma de líneas al procesar facturas)
    valor_factura = fields.Float(string="Valor total",
                                help="Importe total del expediente. Se puede editar manualmente; al procesar facturas se rellena con la suma de las líneas.")
    moneda = fields.Selection([("EUR","EUR"),("USD","USD")], default="EUR")

    # Líneas
    line_ids = fields.One2many("aduana.expediente.line", "expediente_id", string="Líneas")
    
    # Resumen Verificación IA
    verificacion_ia_estado = fields.Selection([
        ("ok", "OK"),
        ("advertencia", "Advertencia"),
        ("critico", "Crítico"),
        ("pendiente", "Pendiente"),
    ], string="Estado Verificación IA", compute="_compute_verificacion_ia_resumen", store=False)
    verificacion_ia_resumen = fields.Char(string="Resumen Verificación IA", compute="_compute_verificacion_ia_resumen", store=False)
    
    # Documentos requeridos por partida arancelaria (TARIC)
    documento_requerido_ids = fields.One2many("aduana.expediente.documento.requerido", "expediente_id", string="Documentos Requeridos")

    # Facturas del expediente (varios PDF por expediente; no son expedientes hijo)
    factura_ids = fields.One2many("aduana.expediente.factura", "expediente_id", string="Facturas", help="Facturas PDF subidas a este expediente")
    
    # Campos para expediente con una sola factura (opcional)
    lineas_count = fields.Integer(string="Nº Líneas", compute="_compute_lineas_count", store=False)
    fecha_procesamiento = fields.Datetime(string="Fecha Procesamiento", readonly=True, help="Fecha en que se procesó la factura (cuando hay una sola factura en el expediente)")

    # Países
    pais_origen = fields.Char(default="ES")
    pais_destino = fields.Char(default="AD")

    # Identificadores aduaneros
    lrn = fields.Char(string="LRN")
    mrn = fields.Char(string="MRN", index=True)
    bandeja_last_num = fields.Integer(string="Último mensaje bandeja procesado", default=0)
    
    # Campos adicionales
    fecha_salida_real = fields.Datetime(string="Fecha Salida Real")
    fecha_entrada_real = fields.Datetime(string="Fecha Entrada Real")
    fecha_levante = fields.Datetime(string="Fecha Levante")
    fecha_recepcion = fields.Datetime(string="Fecha Recepción")
    numero_factura = fields.Char(string="Nº Factura Comercial")
    referencia_transporte = fields.Char(string="Referencia Transporte")
    conductor_nombre = fields.Char(string="Nombre Conductor")
    conductor_dni = fields.Char(string="DNI Conductor")
    remolque = fields.Char(string="Remolque")
    codigo_transporte = fields.Char(string="Código Transporte")
    observaciones = fields.Text(string="Observaciones")
    error_message = fields.Text(string="Último Error", readonly=True)
    last_response_date = fields.Datetime(string="Última Respuesta", readonly=True)

    # Respuesta EXS (IE615/IE628)
    exs_circuito = fields.Char(string="Circuito EXS", readonly=True, help="V=verde, N=naranja, R=rojo")
    exs_dec_csv = fields.Char(string="CSV declaración EXS", readonly=True)
    exs_rel_csv = fields.Char(string="CSV levante EXS", readonly=True)
    exs_tipo_declaracion = fields.Char(string="Tipo declaración EXS", readonly=True, help="A1, A2, A3, NR")
    exs_predeclaracion = fields.Char(string="PreEXS", readonly=True, help="DE si es predeclaración")
    
    # Referencias MSoft (para sincronización)
    msoft_codigo = fields.Char(string="Código MSoft", index=True, help="Código original del expediente en MSoft (ExpCod)")
    msoft_recepcion_num = fields.Integer(string="Nº Recepción MSoft", help="Número de recepción en MSoft (ExpRecNum)")
    msoft_fecha_recepcion = fields.Datetime(string="Fecha Recepción MSoft")
    msoft_fecha_modificacion = fields.Datetime(string="Fecha Modificación MSoft", index=True, help="Última modificación en MSoft para sincronización incremental")
    msoft_usuario_modificacion = fields.Char(string="Usuario Modificación MSoft")
    msoft_usuario_creacion = fields.Char(string="Usuario Creación MSoft")
    msoft_fecha_creacion = fields.Datetime(string="Fecha Creación MSoft")
    msoft_estado_original = fields.Integer(string="Estado MSoft Original", help="Estado original en MSoft (ExpSit)")
    msoft_sincronizado = fields.Boolean(string="Sincronizado con MSoft", default=False)
    msoft_ultima_sincronizacion = fields.Datetime(string="Última Sincronización")
    
    # Flags de control
    flag_confirmado = fields.Boolean(string="Confirmado", help="Expediente confirmado en MSoft")
    flag_origen_ok = fields.Boolean(string="Origen OK", help="Origen validado")
    flag_destino_ok = fields.Boolean(string="Destino OK", help="Destino validado")
    flag_anulado = fields.Boolean(string="Anulado", help="Expediente anulado (no procesar)")
    
    # Documentación adicional
    numero_albaran_remitente = fields.Char(string="Albarán Remitente")
    numero_albaran_destinatario = fields.Char(string="Albarán Destinatario")
    codigo_orden = fields.Char(string="Código Orden")
    descripcion_orden = fields.Char(string="Descripción Orden")
    referencia_proveedor = fields.Char(string="Referencia Proveedor")
    
    # Oficinas adicionales
    oficina_destino = fields.Char(string="Oficina Aduanas Destino")
    
    # Factura PDF y procesamiento IA (FLUJO PRINCIPAL)
    factura_pdf = fields.Binary(string="Factura PDF", help="Sube la factura PDF para extraer datos automáticamente. Este es el punto de partida del expediente.")
    factura_pdf_filename = fields.Char(string="Nombre Archivo Factura")
    factura_pdf_url = fields.Char(string="URL Factura PDF", compute="_compute_factura_pdf_url", help="URL para previsualizar el PDF")
    
    # Documentos relacionados
    documento_ids = fields.Many2many("ir.attachment", string="Documentos", compute="_compute_documento_ids", store=False)
    dua_generado = fields.Boolean(string="DUA Generado", compute="_compute_dua_generado", store=False)
    
    @api.depends('name')
    def _compute_dua_generado(self):
        """Verifica si el DUA está generado"""
        for rec in self:
            # No podemos depender de 'id' en @api.depends, pero podemos usarlo en el método
            if rec.id:
                att = rec._get_xml_attachment("DUA_CUSDEC_EX1.xml")
                rec.dua_generado = bool(att)
            else:
                rec.dua_generado = False
    
    @api.depends('factura_ids', 'factura_ids.factura_pdf')
    def _compute_documento_ids(self):
        """Documentos del expediente: attachments con res_model=expediente (incluyen facturas subidas, que se copian al expediente al subir)."""
        for rec in self:
            if not rec.id:
                rec.documento_ids = self.env['ir.attachment']
                continue
            attachments = self.env['ir.attachment'].search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id)
            ])
            rec.documento_ids = attachments
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create para asegurar que se creen attachments cuando se sube factura_pdf"""
        # Generar secuencia automáticamente si no se proporciona name o es "Nuevo"
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == _("Nuevo"):
                vals['name'] = self.env['ir.sequence'].next_by_code('aduana.expediente') or _("Nuevo")
            # Si se sube una factura, cambiar el estado a "pendiente", si no, mantener "sin_factura"
            if vals.get('factura_pdf') and not vals.get('factura_estado_procesamiento'):
                vals['factura_estado_procesamiento'] = 'pendiente'
            elif not vals.get('factura_pdf') and not vals.get('factura_estado_procesamiento'):
                vals['factura_estado_procesamiento'] = 'sin_factura'
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if vals.get('factura_pdf') and vals.get('factura_pdf_filename'):
                # Crear attachment para la factura PDF si no existe
                existing = self.env['ir.attachment'].search([
                    ('res_model', '=', rec._name),
                    ('res_id', '=', rec.id),
                    ('name', '=', vals['factura_pdf_filename'])
                ], limit=1)
                if not existing:
                    self.env['ir.attachment'].create({
                        'name': vals['factura_pdf_filename'],
                        'res_model': rec._name,
                        'res_id': rec.id,
                        'type': 'binary',
                        'mimetype': 'application/pdf',
                        'datas': vals['factura_pdf']
                    })
        return records
    
    def write(self, vals):
        """Override write para crear/actualizar attachment cuando se cambia factura_pdf"""
        # Si se sube una factura y el estado es "sin_factura", cambiar a "pendiente"
        if 'factura_pdf' in vals and vals.get('factura_pdf'):
            for rec in self:
                if rec.factura_estado_procesamiento == 'sin_factura':
                    vals['factura_estado_procesamiento'] = 'pendiente'
        # Si se elimina la factura, volver a "sin_factura"
        elif 'factura_pdf' in vals and not vals.get('factura_pdf'):
            vals['factura_estado_procesamiento'] = 'sin_factura'
        
        result = super().write(vals)
        if 'factura_pdf' in vals or 'factura_pdf_filename' in vals:
            for rec in self:
                if rec.factura_pdf and rec.factura_pdf_filename:
                    # Buscar attachment existente
                    existing = self.env['ir.attachment'].search([
                        ('res_model', '=', rec._name),
                        ('res_id', '=', rec.id),
                        ('name', '=', rec.factura_pdf_filename)
                    ], limit=1)
                    if existing:
                        existing.write({'datas': rec.factura_pdf})
                    else:
                        self.env['ir.attachment'].create({
                            'name': rec.factura_pdf_filename,
                            'res_model': rec._name,
                            'res_id': rec.id,
                            'type': 'binary',
                            'mimetype': 'application/pdf',
                            'datas': rec.factura_pdf
                        })
                # Invalidar el campo computed para que se recalcule
                rec.invalidate_recordset(['documento_ids'])
        return result
    
    @api.depends('factura_pdf')
    def _compute_factura_pdf_url(self):
        """Genera la URL del PDF para previsualización"""
        for record in self:
            if record.factura_pdf:
                # Buscar el attachment más reciente asociado a este registro con el nombre del archivo
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'aduana.expediente'),
                    ('res_id', '=', record.id),
                    ('name', '=', record.factura_pdf_filename)
                ], limit=1, order='create_date desc')
                
                if not attachment and record.factura_pdf_filename:
                    # Si no se encuentra, buscar por nombre similar
                    attachment = self.env['ir.attachment'].search([
                        ('res_model', '=', 'aduana.expediente'),
                        ('res_id', '=', record.id),
                        ('name', 'ilike', record.factura_pdf_filename.split('.')[0] if '.' in record.factura_pdf_filename else record.factura_pdf_filename)
                    ], limit=1, order='create_date desc')
                
                if attachment:
                    record.factura_pdf_url = f'/web/content/{attachment.id}?download=0'
                else:
                    record.factura_pdf_url = False
            else:
                record.factura_pdf_url = False
    factura_procesada = fields.Boolean(string="Factura Procesada", default=False, help="Indica si la factura ha sido procesada con IA")
    factura_estado_procesamiento = fields.Selection([
        ("sin_factura", "Sin Factura"),
        ("pendiente", "Pendiente de Procesar"),
        ("en_cola", "En cola (background)"),
        ("procesando", "Procesando..."),
        ("completado", "Completado"),
        ("error", "Error en Procesamiento"),
        ("advertencia", "Completado con Advertencias"),
    ], string="Estado Procesamiento", default="sin_factura", readonly=True, help="Estado del procesamiento de la factura")
    factura_en_cola_at = fields.Datetime(string="Fecha en cola", readonly=True)
    factura_mensaje_error = fields.Text(string="Mensaje de Error/Advertencia", readonly=True, help="Mensajes de error o advertencias durante el procesamiento")
    factura_mensaje_html = fields.Html(string="Mensaje de Procesamiento", compute="_compute_factura_mensaje_html", store=False, sanitize=False)
    factura_datos_extraidos = fields.Text(string="Datos Extraídos de Factura", readonly=True, help="Datos extraídos de la factura por IA/OCR")
    
    @api.depends('factura_estado_procesamiento', 'factura_mensaje_error')
    def _compute_factura_mensaje_html(self):
        """Genera el mensaje HTML con colores según el estado"""
        for rec in self:
            estado = rec.factura_estado_procesamiento
            mensaje = rec.factura_mensaje_error or ''
            
            if estado == 'error':
                # Rojo para errores
                rec.factura_mensaje_html = f'<div class="alert alert-danger" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-exclamation-circle"></i> {mensaje}</div>' if mensaje else False
            elif estado == 'advertencia':
                # Amarillo/Naranja para advertencias
                rec.factura_mensaje_html = f'<div class="alert alert-warning" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #fff3cd; color: #856404; border: 1px solid #ffeaa7; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-exclamation-triangle"></i> {mensaje}</div>' if mensaje else False
            elif estado == 'en_cola':
                rec.factura_mensaje_html = '<div class="alert alert-info" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #e8f4ff; color: #0c5460; border: 1px solid #bee5eb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-clock-o"></i> Factura en cola para procesamiento en background</div>'
            elif estado == 'completado':
                # Verde para éxito
                if mensaje:
                    rec.factura_mensaje_html = f'<div class="alert alert-success" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-check-circle"></i> {mensaje}</div>'
                else:
                    rec.factura_mensaje_html = '<div class="alert alert-success" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-check-circle"></i> Procesamiento completado correctamente</div>'
            else:
                # Otros estados (pendiente, procesando) - no mostrar mensaje
                rec.factura_mensaje_html = False

    def _recompute_factura_estado_from_facturas(self):
        """Actualiza factura_estado_procesamiento del expediente según el estado de factura_ids.
        Solo aplica cuando el expediente tiene facturas (factura_ids); si no tiene, se mantiene
        el estado legacy (factura_pdf único).
        """
        for expediente in self:
            if not expediente.factura_ids:
                # Sin facturas: si no usa factura_pdf legacy, poner sin_factura
                if not expediente.factura_pdf and expediente.factura_estado_procesamiento != "sin_factura":
                    expediente.write({"factura_estado_procesamiento": "sin_factura"})
                continue
            estados = expediente.factura_ids.mapped("factura_estado_procesamiento")
            if "error" in estados:
                nuevo = "error"
            elif "procesando" in estados:
                nuevo = "procesando"
            elif "en_cola" in estados:
                nuevo = "en_cola"
            elif "pendiente" in estados or "sin_factura" in estados:
                nuevo = "pendiente"
            elif "advertencia" in estados:
                nuevo = "advertencia"
            elif estados and all(s in ("completado", "advertencia") for s in estados):
                nuevo = "advertencia" if "advertencia" in estados else "completado"
            else:
                nuevo = "pendiente"
            if expediente.factura_estado_procesamiento != nuevo:
                expediente.write({"factura_estado_procesamiento": nuevo})

    # Incidencias
    incidencia_ids = fields.One2many("aduana.incidencia", "expediente_id", string="Incidencias")
    incidencias_count = fields.Integer(string="Nº Incidencias", compute="_compute_incidencias_count", store=True)
    incidencias_pendientes_count = fields.Integer(string="Nº Incidencias Pendientes", compute="_compute_incidencias_count", store=True)

    state = fields.Selection([
        ("draft","Borrador"),
        ("predeclared","Predeclarado / Declarado"),
        ("presented","Presentado"),
        ("accepted","Aceptado (MRN)"),
        ("released","Levante"),
        ("exited","Salida/Entrada confirmada"),
        ("closed","Cerrado"),
        ("error","Error"),
    ], default="draft", tracking=True)

    @api.depends("incidencia_ids", "incidencia_ids.state")
    def _compute_incidencias_count(self):
        """Calcula número de incidencias"""
        for rec in self:
            rec.incidencias_count = len(rec.incidencia_ids)
            rec.incidencias_pendientes_count = len(rec.incidencia_ids.filtered(lambda i: i.state in ("pendiente", "en_revision")))
    
    @api.depends("incidencia_ids", "incidencia_ids.state")
    def _compute_incidencias_count(self):
        """Calcula número de incidencias"""
        for rec in self:
            rec.incidencias_count = len(rec.incidencia_ids)
            rec.incidencias_pendientes_count = len(rec.incidencia_ids.filtered(lambda i: i.state in ("pendiente", "en_revision")))
    
    @api.depends("line_ids")
    def _compute_lineas_count(self):
        """Calcula el número de líneas del expediente"""
        for rec in self:
            rec.lineas_count = len(rec.line_ids)
    
    @api.depends("line_ids", "line_ids.verificacion_estado", "line_ids.verificacion_detalle", 
                 "line_ids.valor_linea", "valor_factura", 
                 "documento_requerido_ids", "documento_requerido_ids.mandatory", "documento_requerido_ids.estado")
    def _compute_verificacion_ia_resumen(self):
        """Calcula el resumen del estado de verificación IA basado en todas las líneas"""
        for rec in self:
            if not rec.line_ids:
                rec.verificacion_ia_estado = "pendiente"
                rec.verificacion_ia_resumen = "Sin líneas para verificar"
                continue
            
            # Contar estados de verificación
            estados = rec.line_ids.mapped("verificacion_estado")
            total = len(estados)
            correctos = estados.count("correcto") + estados.count("verificado")
            corregidos = estados.count("corregido")
            sugeridos = estados.count("sugerido")
            pendientes = estados.count("pendiente")
            
            # Verificar incongruencias entre totales y líneas
            suma_lineas = sum(rec.line_ids.mapped("valor_linea") or [0])
            valor_factura = rec.valor_factura or 0
            diferencia = abs(suma_lineas - valor_factura)
            tiene_incongruencia_totales = diferencia > 0.01  # Tolerancia para decimales
            
            # Verificar documentos faltantes (obligatorios sin subir)
            documentos_faltantes = rec.documento_requerido_ids.filtered(
                lambda d: d.mandatory and d.estado == 'pendiente'
            )
            num_docs_faltantes = len(documentos_faltantes)
            tiene_docs_faltantes = num_docs_faltantes > 0
            
            # Construir resumen con todas las verificaciones
            problemas = []
            
            # Problemas críticos
            if pendientes > 0:
                problemas.append(f"{pendientes} línea(s) pendiente(s)")
            if tiene_docs_faltantes:
                problemas.append(f"{num_docs_faltantes} documento(s) obligatorio(s) faltante(s)")
            
            # Problemas de advertencia
            if tiene_incongruencia_totales:
                problemas.append(f"Incongruencia totales: {suma_lineas:.2f} vs {valor_factura:.2f}")
            if corregidos > 0:
                problemas.append(f"{corregidos} línea(s) corregida(s)")
            if sugeridos > 0:
                problemas.append(f"{sugeridos} línea(s) con sugerencias")
            
            # Determinar estado general
            if pendientes > 0 or tiene_docs_faltantes:
                # Si hay líneas pendientes o documentos faltantes, es crítico
                rec.verificacion_ia_estado = "critico"
                rec.verificacion_ia_resumen = " | ".join(problemas) if problemas else "Problemas críticos detectados"
            elif tiene_incongruencia_totales or corregidos > 0 or sugeridos > 0:
                # Si hay incongruencias, correcciones o sugerencias, es advertencia
                rec.verificacion_ia_estado = "advertencia"
                rec.verificacion_ia_resumen = " | ".join(problemas) if problemas else "Advertencias detectadas"
            elif correctos == total:
                # Todas correctas
                rec.verificacion_ia_estado = "ok"
                rec.verificacion_ia_resumen = f"✓ {total} línea(s) verificada(s) correctamente"
            else:
                # Estado desconocido
                rec.verificacion_ia_estado = "pendiente"
                rec.verificacion_ia_resumen = "Verificación incompleta"
    
    @api.depends("incoterm")
    def _compute_incoterm_info(self):
        """Calcula información contextual del incoterm"""
        incoterm_data = {
            "EXW": {
                "transporte": "Comprador",
                "seguro": "Comprador",
                "riesgo": "Comprador (desde origen)",
                "aduana_exp": "Comprador",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor pone la mercancía a disposición del comprador en sus instalaciones. El comprador asume todos los costes y riesgos.",
            },
            "FCA": {
                "transporte": "Comprador",
                "seguro": "Comprador",
                "riesgo": "Comprador (desde punto entrega)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor entrega la mercancía al transportista designado por el comprador en el punto acordado.",
            },
            "CPT": {
                "transporte": "Vendedor",
                "seguro": "Comprador",
                "riesgo": "Comprador (desde entrega al transportista)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor paga el transporte hasta el destino, pero el riesgo se transfiere al comprador cuando se entrega al primer transportista.",
            },
            "CIP": {
                "transporte": "Vendedor",
                "seguro": "Vendedor",
                "riesgo": "Comprador (desde entrega al transportista)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor paga transporte y seguro hasta el destino, pero el riesgo se transfiere al comprador cuando se entrega al primer transportista.",
            },
            "DAP": {
                "transporte": "Vendedor",
                "seguro": "Vendedor",
                "riesgo": "Vendedor (hasta destino)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor entrega la mercancía en el lugar de destino acordado. El comprador asume los trámites aduaneros de importación.",
            },
            "DPU": {
                "transporte": "Vendedor",
                "seguro": "Vendedor",
                "riesgo": "Vendedor (hasta descarga)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Comprador",
                "descripcion": "El vendedor entrega la mercancía descargada en el lugar de destino. El comprador asume los trámites aduaneros de importación.",
            },
            "DDP": {
                "transporte": "Vendedor",
                "seguro": "Vendedor",
                "riesgo": "Vendedor (hasta destino)",
                "aduana_exp": "Vendedor",
                "aduana_imp": "Vendedor",
                "descripcion": "El vendedor asume todos los costes, riesgos y trámites aduaneros hasta la entrega en destino.",
            },
        }
        
        for rec in self:
            if rec.incoterm and rec.incoterm in incoterm_data:
                data = incoterm_data[rec.incoterm]
                rec.incoterm_info = f"""
                <div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 4px; padding: 12px; margin: 8px 0;">
                    <p style="margin: 0 0 12px 0; font-size: 14px; line-height: 1.5;">
                        <strong style="font-size: 16px;">{rec.incoterm}</strong> - {data['descripcion']}
                    </p>
                    <table style="width: 100%; border-collapse: collapse; margin: 0;">
                        <tr>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb; width: 40%;"><strong>Transporte:</strong></td>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;">{data['transporte']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;"><strong>Seguro:</strong></td>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;">{data['seguro']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;"><strong>Riesgo:</strong></td>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;">{data['riesgo']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;"><strong>Aduana Exportación:</strong></td>
                            <td style="padding: 6px 8px; border-bottom: 1px solid #bee5eb;">{data['aduana_exp']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 8px;"><strong>Aduana Importación:</strong></td>
                            <td style="padding: 6px 8px;">{data['aduana_imp']}</td>
                        </tr>
                    </table>
                </div>
                """
            else:
                rec.incoterm_info = False

    def _get_settings(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "aeat_endpoint_cc515c": icp.get_param("aduanas_transport.endpoint.cc515c") or "",
            "aeat_endpoint_cc511c": icp.get_param("aduanas_transport.endpoint.cc511c") or "",
            "aeat_endpoint_imp_decl": icp.get_param("aduanas_transport.endpoint.imp_decl") or "",
            "aeat_endpoint_bandeja": icp.get_param("aduanas_transport.endpoint.bandeja") or "",
            "aeat_endpoint_ie615": icp.get_param("aduanas_transport.endpoint.ie615") or "",
        }

    def _attach_xml(self, filename, xml_text, mimetype="application/xml"):
        for rec in self:
            self.env["ir.attachment"].create({
                "name": filename,
                "res_model": rec._name,
                "res_id": rec.id,
                "type": "binary",
                "mimetype": mimetype,
                "datas": base64.b64encode((xml_text or "").encode("utf-8"))
            })
    
    def _attach_pdf(self, filename, pdf_data):
        """Adjunta un PDF como documento al expediente"""
        for rec in self:
            # Si pdf_data es bytes, codificarlo en base64
            if isinstance(pdf_data, bytes):
                pdf_b64 = base64.b64encode(pdf_data)
            elif isinstance(pdf_data, str):
                # Si ya es base64 string, usarlo directamente, si no codificarlo
                try:
                    # Intentar decodificar para verificar si ya es base64 válido
                    base64.b64decode(pdf_data)
                    pdf_b64 = pdf_data
                except:
                    pdf_b64 = base64.b64encode(pdf_data.encode('utf-8'))
            else:
                pdf_b64 = base64.b64encode(str(pdf_data).encode('utf-8'))
            
            self.env["ir.attachment"].create({
                "name": filename,
                "res_model": rec._name,
                "res_id": rec.id,
                "type": "binary",
                "mimetype": "application/pdf",
                "datas": pdf_b64
            })

    def action_anadir_documento(self):
        """Abre el formulario para subir un nuevo documento (PDF u otro) al expediente."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Añadir documento"),
            "res_model": "ir.attachment",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_res_model": self._name,
                "default_res_id": self.id,
                "default_name": _("Documento"),
            },
        }

    def _generate_dua_pdf(self):
        """Genera el PDF del DUA usando el sistema de reportes de Odoo"""
        self.ensure_one()
        try:
            # Buscar el reporte del DUA por su ID externo
            report = self.env.ref('aduanas_transport.report_dua_pdf', raise_if_not_found=False)
            if report:
                # Usar el reporte para generar el PDF
                pdf_content, _ = report._render_qweb_pdf(self.ids)
                return pdf_content
            else:
                # Si no existe el reporte, intentar usar el template directamente
                _logger.warning("No se encontró el reporte DUA, intentando generar desde template")
                html_content = self.env['ir.ui.view']._render_template(
                    "aduanas_transport.template_report_dua_pdf",
                    {"exp": self, "docs": self}
                )
                # Convertir HTML a PDF
                pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf([html_content])
                return pdf_content
        except Exception as e:
            _logger.error("Error generando PDF del DUA: %s", e)
            # Si falla, retornar None para que no se rompa el proceso
            return None

    # ===== Exportación (AES) =====
    def action_generate_cc515c(self):
        """Genera el DUA en formato CUSDEC EX1 (formato oficial)"""
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("DUA solo aplica a exportación"))
            # Validar datos antes de generar
            validator = self.env["aduanas.validator"]
            validator.validate_expediente_export(rec)
            # Generar CUSDEC EX1 (formato oficial del DUA)
            xml = self.env['ir.ui.view']._render_template(
                "aduanas_transport.tpl_cusdec_ex1",
                {"exp": rec}
            )
            rec._attach_xml("DUA_CUSDEC_EX1.xml", xml)
            
            # Generar también el PDF del DUA oficial imprimible
            try:
                pdf_content = rec._generate_dua_pdf()
                if pdf_content:
                    rec._attach_pdf(f"DUA_{rec.name}_OFICIAL.pdf", pdf_content)
                    _logger.info("PDF del DUA generado correctamente para expediente %s", rec.name)
                else:
                    _logger.warning("No se pudo generar el PDF del DUA para expediente %s", rec.name)
            except Exception as pdf_error:
                _logger.error("Error generando PDF del DUA para expediente %s: %s", rec.name, pdf_error)
                # No fallar el proceso si el PDF falla, solo loguear el error
            
            rec.state = "predeclared"
            rec.error_message = False
        return True



    def action_send_cc515c(self):
        """Envía el DUA en formato CUSDEC EX1 a AEAT"""
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("DUA solo aplica a exportación"))
            settings = rec._get_settings()
            # Buscar el archivo DUA_CUSDEC_EX1.xml
            xmls = self.env["ir.attachment"].search([
                ("res_model","=",rec._name),
                ("res_id","=",rec.id),
                ("name","=","DUA_CUSDEC_EX1.xml")
            ], limit=1)
            if not xmls:
                rec.action_generate_cc515c()
                xmls = self.env["ir.attachment"].search([
                    ("res_model","=",rec._name),
                    ("res_id","=",rec.id),
                    ("name","=","DUA_CUSDEC_EX1.xml")
                ], limit=1)
            xml_content = base64.b64decode(xmls.datas or b"").decode("utf-8")
            resp_xml = client.send_xml(settings.get("aeat_endpoint_cc515c"), xml_content, service="CUSDEC_EX1")
            rec._attach_xml("DUA_CUSDEC_EX1_response.xml", resp_xml or "")
            
            # Parsear respuesta mejorada
            parsed = parser.parse_aeat_response(resp_xml, "CUSDEC_EX1")
            rec.last_response_date = fields.Datetime.now()
            
            if parsed.get("success") and parsed.get("mrn"):
                rec.mrn = parsed["mrn"]
                rec.state = "accepted"
                rec.error_message = False
                if parsed.get("messages"):
                    rec.with_context(mail_notrack=True).message_post(
                        body=_("DUA aceptado. MRN: %s\nMensajes: %s") % (
                            rec.mrn, "\n".join(parsed["messages"])
                        ),
                        subtype_xmlid='mail.mt_note'
                    )
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cusdec_ex1")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.with_context(mail_notrack=True).message_post(body=_("Error al enviar DUA (CUSDEC EX1):\n%s") % error_msg, subtype_xmlid='mail.mt_note')
                # Procesar incidencias de error
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cusdec_ex1")
                raise UserError(_("Error al enviar a AEAT:\n%s") % error_msg)
        return True

    def action_present_cc511c(self):
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("CC511C solo aplica a exportación"))
            if not rec.mrn:
                raise UserError(_("Debe tener un MRN antes de presentar CC511C"))
            xml = self.env['ir.ui.view']._render_template(
                "aduanas_transport.tpl_cc511c",
                {"exp": rec}
            )
            rec._attach_xml(f"{rec.name}_CC511C.xml", xml)
            settings = rec._get_settings()
            resp_xml = client.send_xml(settings.get("aeat_endpoint_cc511c"), xml, service="CC511C")
            rec._attach_xml(f"{rec.name}_CC511C_response.xml", resp_xml or "")
            
            # Parsear respuesta mejorada
            parsed = parser.parse_aeat_response(resp_xml, "CC511C")
            rec.last_response_date = fields.Datetime.now()
            
            if parsed.get("accepted") or parsed.get("success"):
                rec.state = "presented"
                rec.error_message = False
                rec.with_context(mail_notrack=True).message_post(
                    body=_("CC511C presentado correctamente"),
                    subtype_xmlid='mail.mt_note'
                )
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cc511c")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.with_context(mail_notrack=True).message_post(body=_("Error al presentar CC511C:\n%s") % error_msg, subtype_xmlid='mail.mt_note')
                # Procesar incidencias de error
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cc511c")
                raise UserError(_("Error al presentar CC511C:\n%s") % error_msg)
        return True

    # ===== EXS (Declaración Sumaria de Salida - IE615 V5) =====
    def _build_ie615_body(self, preprod_maritimo=True, preprod_doc_ref=None, preprod_doc_item="00001"):
        """
        Construye el cuerpo XML del mensaje IE615 (CC615A) para presentación EXS.
        preprod_maritimo: True = recinto 9999 (marítimo), False = 9998 (aéreo).
        preprod_doc_ref: referencia DSDT en preprod (marítimo: 99992600404, aéreo: 99985000383).
        preprod_doc_item: 00001=verde, 00002=naranja, 00003=rojo.
        """
        self.ensure_one()
        company = self.env.company
        nif_declarante = (company.vat or "").replace(" ", "").replace(".", "").replace("-", "").strip() or "ESA99999996"
        if nif_declarante.upper().startswith("ES"):
            nif_declarante = nif_declarante.upper()
        else:
            nif_declarante = "ES" + nif_declarante if len(nif_declarante) <= 9 else nif_declarante
        now = fields.Datetime.now()
        dt = now.strftime("%y%m%d") if now else "250123"
        tm = now.strftime("%H%M") if now else "1200"
        dec_dat_tim = now.strftime("%Y%m%d%H%M") if now else "202501231200"
        mes_id = (self.name or "EX").replace(" ", "")[:8] + str(int(time.time()))[-6:]
        mes_id = mes_id[:14]
        lrn = self.lrn or self.name or "LRN%s" % mes_id
        num_items = len(self.line_ids) or 1
        tot_packages = sum((l.bultos or 1) for l in self.line_ids) or 1
        tot_gross = sum((l.peso_bruto or 0) for l in self.line_ids) or 1.0
        if preprod_maritimo:
            cus_sub_pla = "9999AAAAAA"
            ref_num_col = "ES009999"
        else:
            cus_sub_pla = "9998AAAAAA"
            ref_num_col = "ES009998"
        doc_ref = preprod_doc_ref or ("99992600404" if preprod_maritimo else "99985000383")
        dec_place = (company.city or company.name or "Valencia").strip()[:35]
        declarant_name = (company.name or "Declarante").strip()[:70]
        declarant_street = (company.street or " ").strip()[:70]
        declarant_zip = (company.zip or "28000").strip()[:9]
        declarant_city = (company.city or "Madrid").strip()[:35]
        declarant_country = (company.country_id and company.country_id.code) or "ES"
        declarant_email = (company.email or "info@empresa.com").strip()[:80]
        consignee = self.consignatario
        if consignee:
            consignee_name = (consignee.name or "").strip()[:70]
            consignee_street = (consignee.street or "").strip()[:70]
            consignee_zip = (consignee.zip or "00000").strip()[:9]
            consignee_city = (consignee.city or "").strip()[:35]
            consignee_country = (consignee.country_id and consignee.country_id.code) or "AD"
            consignee_tin = (consignee.vat or "ADXXXXXXXXX").replace(" ", "").strip()[:17]
        else:
            consignee_name = "Consignatario"
            consignee_street = "Calle"
            consignee_zip = "00000"
            consignee_city = "Ciudad"
            consignee_country = self.pais_destino or "AD"
            consignee_tin = "ADXXXXXXXXX"
        trans_ref = (self.referencia_transporte or "V010102567780").strip()[:35]
        # TRACONCO1 = carrier/sender (remitente o compañía)
        sender = self.remitente or company
        if sender:
            sender_name = (sender.name or "Remitente").strip()[:70]
            sender_street = (sender.street or " ").strip()[:70]
            sender_zip = (sender.zip or "28000").strip()[:9]
            sender_city = (sender.city or "Madrid").strip()[:35]
            sender_country = (sender.country_id and sender.country_id.code) or "ES"
            sender_tin = (sender.vat or "ESA99999998").replace(" ", "").strip()[:17]
        else:
            sender_name, sender_street, sender_zip, sender_city, sender_country, sender_tin = "Remitente", "Calle", "28000", "Madrid", "ES", "ESA99999998"
        ns = "https://www2.agenciatributaria.gob.es/ADUA/internet/es/aeat/dit/adu/adrx/ws/IE615V5Ent.xsd"
        lines_xml = []
        for idx, line in enumerate(self.line_ids or [None]):
            if line is None:
                item_num = 1
                desc = "Mercancía"
                gross = "%.6g" % (tot_gross or 1)
                partida = "840999"
            else:
                item_num = line.item_number or (idx + 1)
                desc = (line.descripcion or "Mercancía")[:350]
                gross = "%.6g" % (line.peso_bruto or 0) or "1"
                partida = (line.partida or "840999").replace(" ", "")[:10]
            lines_xml.append("""<GOOITEGDS>
<IteNumGDS7>%s</IteNumGDS7>
<GooDesGDS23>%s</GooDesGDS23>
<GroMasGDS46>%s</GroMasGDS46>
<PREDOCGODITM1>
<DocTypPD11>N337</DocTypPD11>
<DocRefPD12>%s</DocRefPD12>
<DocGdsIteNumPD13>%s</DocGdsIteNumPD13>
</PREDOCGODITM1>
<COMCODGODITM>
<ComNomCMD1>%s</ComNomCMD1>
</COMCODGODITM>
<PACGS2>
<MarNumOfPacGS21>MARCAS</MarNumOfPacGS21>
<KinOfPacGS23>BX</KinOfPacGS23>
<NumOfPacGS24>%s</NumOfPacGS24>
</PACGS2>
</GOOITEGDS>""" % (item_num, xml_escape(desc), gross, doc_ref, preprod_doc_item, partida, tot_packages if not self.line_ids else (line.bultos or 1)))
        dest_country = self.pais_destino or "AD"
        body = """<?xml version="1.0" encoding="UTF-8"?>
<exs:CC615A xmlns:exs="%s">
<MesSenMES3>%s</MesSenMES3>
<MesRecMES6>NICA.ES</MesRecMES6>
<DatOfPreMES9>%s</DatOfPreMES9>
<TimOfPreMES10>%s</TimOfPreMES10>
<TesIndMES18>1</TesIndMES18>
<MesIdeMES19>%s</MesIdeMES19>
<MesTypMES20>CC615A</MesTypMES20>
<HEAHEA>
<RefNumHEA4>%s</RefNumHEA4>
<CusSubPlaHEA66>%s</CusSubPlaHEA66>
<TotNumOfIteHEA305>%s</TotNumOfIteHEA305>
<TotNumOfPacHEA306>%s</TotNumOfPacHEA306>
<TotGroMasHEA307>%s</TotGroMasHEA307>
<DecDatTimHEA114>%s</DecDatTimHEA114>
<DecPlaHEA394>%s</DecPlaHEA394>
<TraChaMetOfPayHEA1>A</TraChaMetOfPayHEA1>
</HEAHEA>
<TRANSDOC1>
<TransDocType11>N705</TransDocType11>
<TransDocRefNum12>%s</TransDocRefNum12>
</TRANSDOC1>
<TRACONCO1>
<NamCO17>%s</NamCO17>
<StrAndNumCO122>%s</StrAndNumCO122>
<PosCodCO123>%s</PosCodCO123>
<CitCO124>%s</CitCO124>
<CouCO125>%s</CouCO125>
<TINCO159>%s</TINCO159>
</TRACONCO1>
<TRACONCE1>
<NamCE17>%s</NamCE17>
<StrAndNumCE122>%s</StrAndNumCE122>
<PosCodCE123>%s</PosCodCE123>
<CitCE124>%s</CitCE124>
<CouCE125>%s</CouCE125>
<TINCE159>%s</TINCE159>
</TRACONCE1>
%s
<ITI>
<CouOfRouCodITI1>%s</CouOfRouCodITI1>
</ITI>
<CUSOFFLON>
<RefNumCOL1>%s</RefNumCOL1>
</CUSOFFLON>
<PERLODSUMDEC>
<NamPLD1>%s</NamPLD1>
<StrAndNumPLD1>%s</StrAndNumPLD1>
<PosCodPLD1>%s</PosCodPLD1>
<CitPLD1>%s</CitPLD1>
<CouCodPLD1>%s</CouCodPLD1>
<TINPLD1>%s</TINPLD1>
<EmailPLD1>%s</EmailPLD1>
</PERLODSUMDEC>
<CARRIER>
<TINCAR1>%s</TINCAR1>
<ContactPersonCAR1>
<NameCAR1>%s</NameCAR1>
<PhoneNumberCAR1>555-000000</PhoneNumberCAR1>
<EmailCAR1>%s</EmailCAR1>
</ContactPersonCAR1>
</CARRIER>
<SEAID529>
<SeaIdSEAID530>XX383471</SeaIdSEAID530>
</SEAID529>
</exs:CC615A>""" % (
            ns,
            nif_declarante,
            dt,
            tm,
            mes_id,
            xml_escape(lrn),
            cus_sub_pla,
            num_items,
            tot_packages,
            "%.6g" % (tot_gross or 1),
            dec_dat_tim,
            xml_escape(dec_place),
            xml_escape(trans_ref),
            xml_escape(sender_name),
            xml_escape(sender_street),
            sender_zip,
            xml_escape(sender_city),
            sender_country,
            sender_tin,
            xml_escape(consignee_name),
            xml_escape(consignee_street),
            consignee_zip,
            xml_escape(consignee_city),
            consignee_country,
            consignee_tin,
            "\n".join(lines_xml),
            dest_country,
            ref_num_col,
            xml_escape(declarant_name),
            xml_escape(declarant_street),
            declarant_zip,
            xml_escape(declarant_city),
            declarant_country,
            nif_declarante,
            declarant_email,
            nif_declarante,
            xml_escape(declarant_name),
            declarant_email,
        )
        return body

    def _build_ie615_soap_envelope(self, body_xml):
        """Envuelve el cuerpo CC615A en un envelope SOAP 1.1. Quita la declaración XML del body."""
        if body_xml.strip().startswith("<?xml"):
            body_xml = body_xml.split("?>", 1)[-1].strip()
        return """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
<soapenv:Body>%s</soapenv:Body>
</soapenv:Envelope>""" % body_xml

    def action_presentar_exs_preprod(self, preprod_maritimo=True, preprod_doc_ref=None, preprod_doc_item="00001"):
        """
        Presenta el DUA como Declaración EXS (IE615) al endpoint configurado (preproducción por defecto)
        y almacena la respuesta (IE628/IE616/IE919).
        """
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("La presentación EXS solo aplica a exportación"))
            settings = rec._get_settings()
            endpoint = settings.get("aeat_endpoint_ie615")
            if not endpoint:
                raise UserError(_("Configure el endpoint EXS (IE615) en Aduanas > Configuración"))
            body = rec._build_ie615_body(preprod_maritimo=preprod_maritimo, preprod_doc_ref=preprod_doc_ref, preprod_doc_item=preprod_doc_item)
            rec._attach_xml("EXS_IE615_%s.xml" % rec.name, body)
            soap = rec._build_ie615_soap_envelope(body)
            resp_xml = client.send_xml(endpoint, soap, service="IE615_EXS", timeout=60)
            rec._attach_xml("EXS_IE615_response_%s.xml" % rec.name, resp_xml or "")
            rec.last_response_date = fields.Datetime.now()
            parsed = parser.parse_ie615_response(resp_xml or "")
            rec.exs_circuito = parsed.get("exs_circuito")
            rec.exs_dec_csv = parsed.get("exs_dec_csv")
            rec.exs_rel_csv = parsed.get("exs_rel_csv")
            rec.exs_tipo_declaracion = parsed.get("exs_tipo_declaracion")
            rec.exs_predeclaracion = parsed.get("exs_predeclaracion")
            if parsed.get("success"):
                rec.mrn = parsed.get("mrn") or rec.mrn
                rec.state = "accepted"
                rec.error_message = False
                rec.with_context(mail_notrack=True).message_post(
                    body=_("EXS aceptada. MRN: %s | Circuito: %s | Tipo: %s") % (
                        rec.mrn or "-", rec.exs_circuito or "-", rec.exs_tipo_declaracion or "-"
                    ),
                    subtype_xmlid="mail.mt_note",
                )
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors") or [parsed.get("error", _("Error desconocido"))])
                rec.error_message = error_msg
                rec.with_context(mail_notrack=True).message_post(
                    body=_("EXS rechazada:\n%s") % error_msg,
                    subtype_xmlid="mail.mt_note",
                )
                raise UserError(_("Error al presentar EXS:\n%s") % error_msg)
        return True

    # ===== Importación (DUA Import) =====
    def action_generate_imp_decl(self):
        for rec in self:
            if rec.direction != "import":
                raise UserError(_("La declaración de importación solo aplica a importación"))
            # Validar datos antes de generar
            validator = self.env["aduanas.validator"]
            validator.validate_expediente_import(rec)
            xml = self.env['ir.ui.view']._render_template(
                "aduanas_transport.tpl_imp_decl",
                {"exp": rec}
            )
            rec._attach_xml(f"{rec.name}_IMP_DECL.xml", xml)
            rec.state = "predeclared"
            rec.error_message = False
        return True


    def action_send_imp_decl(self):
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            if rec.direction != "import":
                raise UserError(_("La declaración de importación solo aplica a importación"))
            settings = rec._get_settings()
            xmls = self.env["ir.attachment"].search([("res_model","=",rec._name),("res_id","=",rec.id),("name","like","%IMP_DECL.xml")], limit=1)
            if not xmls:
                rec.action_generate_imp_decl()
                xmls = self.env["ir.attachment"].search([("res_model","=",rec._name),("res_id","=",rec.id),("name","like","%IMP_DECL.xml")], limit=1)
            xml_content = base64.b64decode(xmls.datas or b"").decode("utf-8")
            resp_xml = client.send_xml(settings.get("aeat_endpoint_imp_decl"), xml_content, service="IMP_DECL")
            rec._attach_xml(f"{rec.name}_IMP_DECL_response.xml", resp_xml or "")
            
            # Parsear respuesta mejorada
            parsed = parser.parse_aeat_response(resp_xml, "IMP_DECL")
            rec.last_response_date = fields.Datetime.now()
            
            if parsed.get("success") and parsed.get("mrn"):
                rec.mrn = parsed["mrn"]
                rec.state = "accepted"
                rec.error_message = False
                if parsed.get("messages"):
                    rec.with_context(mail_notrack=True).message_post(
                        body=_("Declaración aceptada. MRN: %s\nMensajes: %s") % (
                            rec.mrn, "\n".join(parsed["messages"])
                        ),
                        subtype_xmlid='mail.mt_note'
                    )
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "imp_decl")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.with_context(mail_notrack=True).message_post(body=_("Error al enviar declaración:\n%s") % error_msg, subtype_xmlid='mail.mt_note')
                # Procesar incidencias de error
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "imp_decl")
                raise UserError(_("Error al enviar a AEAT:\n%s") % error_msg)
        return True

    # ===== Bandeja AEAT (común) =====
    def action_poll_bandeja(self, limit=50):
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            settings = rec._get_settings()
            codigo = "EXPORAES" if rec.direction == "export" else "IMPORAES"
            xml = self.env['ir.ui.view']._render_template(
                "aduanas_transport.tpl_bandeja_req",
                {
                    "codigo_bandeja": codigo,
                    "ultimo": rec.bandeja_last_num,
                    "maxm": limit,
                }
            )
            resp = client.send_xml(settings.get("aeat_endpoint_bandeja"), xml, service="BANDEJA")
            self._attach_xml(f"{rec.name}_BANDEJA_response_{rec.bandeja_last_num+1}.xml", resp or "")
            # Usar parser mejorado
            parsed = parser.parse_aeat_response(resp, "BANDEJA")
            rec.last_response_date = fields.Datetime.now()
            
            if parsed.get("last_message_num"):
                rec.bandeja_last_num = max(rec.bandeja_last_num, parsed["last_message_num"])
            
            if parsed.get("released") and rec.state not in ("released", "exited", "closed"):
                rec.state = "released"
                rec.with_context(mail_notrack=True).message_post(
                    body=_("Levante confirmado desde bandeja AEAT"),
                    subtype_xmlid='mail.mt_note'
                )
            
            # Procesar incidencias detectadas
            if parsed.get("incidencias"):
                rec._procesar_incidencias(parsed["incidencias"], "bandeja")
            
            if parsed.get("errors"):
                rec.with_context(mail_notrack=True).message_post(body=_("Errores en bandeja:\n%s") % "\n".join(parsed["errors"]), subtype_xmlid='mail.mt_note')
        return True
    
    def _procesar_incidencias(self, incidencias_data, origen="bandeja"):
        """Procesa y crea incidencias desde datos parseados de AEAT"""
        self.ensure_one()
        Incidencia = self.env["aduana.incidencia"]
        
        for inc_data in incidencias_data:
            # Determinar prioridad según tipo
            prioridad_map = {
                "error": "alta",
                "rechazo": "critica",
                "suspension": "critica",
                "requerimiento": "alta",
                "solicitud_info": "media",
                "advertencia": "baja",
                "notificacion": "baja",
            }
            prioridad = prioridad_map.get(inc_data.get("tipo", "error"), "media")
            
            # Crear incidencia
            incidencia = Incidencia.create({
                "expediente_id": self.id,
                "tipo_incidencia": inc_data.get("tipo", "error"),
                "codigo_incidencia": inc_data.get("codigo", ""),
                "titulo": inc_data.get("mensaje", _("Incidencia detectada"))[:200] or _("Incidencia detectada"),
                "descripcion": inc_data.get("mensaje", ""),
                "mensaje_aeat": str(inc_data),
                "fecha_incidencia": fields.Datetime.now(),
                "origen": origen,
                "prioridad": prioridad,
                "state": "pendiente",
            })
            
            # Notificar en el chatter
            self.with_context(mail_notrack=True).message_post(
                body=_("Nueva incidencia detectada: %s\nTipo: %s\nCódigo: %s") % (
                    incidencia.titulo,
                    dict(incidencia._fields["tipo_incidencia"].selection).get(incidencia.tipo_incidencia),
                    incidencia.codigo_incidencia or _("N/A")
                ),
                subtype_xmlid='mail.mt_note'
            )
            
            # Si es crítica, cambiar estado del expediente
            if prioridad == "critica":
                self.state = "error"
                self.error_message = incidencia.descripcion
        
        return True


    @api.model
    def cron_poll_bandeja_all(self):
        domain = [("state","in",["predeclared","presented","accepted","released"])]
        for rec in self.search(domain, limit=50):
            try:
                rec.action_poll_bandeja(limit=50)
            except Exception as e:
                _logger.exception("Error al consultar bandeja para %s: %s", rec.name, e)
                rec.state = "error"
                

    def _get_xml_attachment(self, name_contains):
        self.ensure_one()
        return self.env["ir.attachment"].search([
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("name", "ilike", name_contains),
        ], limit=1)
    
    def action_view_incidencias(self):
        """Abre la vista de incidencias filtrada por este expediente"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Incidencias de %s", self.name),
            "res_model": "aduana.incidencia",
            "view_mode": "tree,form",
            "domain": [("expediente_id", "=", self.id)],
            "context": {"default_expediente_id": self.id},
        }
    
    def action_view_incidencias_pendientes(self):
        """Abre la vista de incidencias pendientes filtrada por este expediente"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Incidencias Pendientes de %s", self.name),
            "res_model": "aduana.incidencia",
            "view_mode": "tree,form",
            "domain": [
                ("expediente_id", "=", self.id),
                ("state", "in", ("pendiente", "en_revision"))
            ],
            "context": {"default_expediente_id": self.id, "search_default_pending": 1},
        }

    def action_view_lineas(self):
        """Abre la vista de líneas del expediente/factura"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Líneas de %s", self.name),
            "res_model": "aduana.expediente.line",
            "view_mode": "tree,form",
            "domain": [("expediente_id", "=", self.id)],
            "context": {"default_expediente_id": self.id},
        }

    def action_subir_facturas(self):
        """Abre el wizard para subir múltiples facturas PDF y añadirlas a este expediente."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Subir facturas a %s", self.name),
            "res_model": "aduanas.subir.facturas.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_expediente_id": self.id},
        }

    def _ensure_cc515c_xml(self):
        """Genera o recupera el XML del DUA en formato CUSDEC EX1"""
        self.ensure_one()
        # Verificar si ya existe el XML
        att = self._get_xml_attachment("DUA_CUSDEC_EX1.xml")
        if att:
            return att
        
        # Si no existe, generar el DUA primero
        # Esto requiere que la factura esté procesada y los datos estén completos
        if not self.factura_procesada:
            raise UserError(_("Debe procesar la factura primero antes de previsualizar el DUA."))
        
        # Generar el DUA
        self.action_generate_cc515c()
        
        # Recuperar el attachment generado
        att = self._get_xml_attachment("DUA_CUSDEC_EX1.xml")
        if not att:
            raise UserError(_("No se pudo generar el DUA. Verifique que todos los datos estén completos."))
        
        return att

    def _ensure_cc511c_xml(self):
        self.ensure_one()
        xml = self.env['ir.ui.view']._render_template(
            "aduanas_transport.tpl_cc511c",
            {"exp": self}
        )
        att = self._get_xml_attachment("CC511C.xml")
        if att:
            att.datas = base64.b64encode(xml.encode("utf-8"))
            return att
        self._attach_xml(f"{self.name}_CC511C.xml", xml)
        return self._get_xml_attachment("CC511C.xml")

    def _ensure_imp_decl_xml(self):
        self.ensure_one()
        xml = self.env['ir.ui.view']._render_template(
            "aduanas_transport.tpl_imp_decl",
            {"exp": self}
        )
        att = self._get_xml_attachment("IMP_DECL.xml")
        if att:
            att.datas = base64.b64encode(xml.encode("utf-8"))
            return att
        self._attach_xml(f"{self.name}_IMP_DECL.xml", xml)
        return self._get_xml_attachment("IMP_DECL.xml")



    def action_preview_cc515c(self):
        """Previsualiza el DUA. Solo funciona si el DUA ya está generado."""
        self.ensure_one()
        # Verificar si el DUA ya está generado
        att = self._get_xml_attachment("DUA_CUSDEC_EX1.xml")
        if not att:
            raise UserError(_("El DUA no está generado. Por favor, use el botón 'Generar DUA' primero."))
        
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=0",
            "target": "new",
        }

    def action_download_cc515c(self):
        self.ensure_one()
        att = self._ensure_cc515c_xml()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=1",
            "target": "self",
        }

    def action_preview_cc511c(self):
        self.ensure_one()
        att = self._ensure_cc511c_xml()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=0",
            "target": "new",
        }

    def action_download_cc511c(self):
        self.ensure_one()
        att = self._ensure_cc511c_xml()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=1",
            "target": "self",
        }

    def action_preview_imp_decl(self):
        self.ensure_one()
        att = self._ensure_imp_decl_xml()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=0",
            "target": "new",
        }

    def action_download_imp_decl(self):
        self.ensure_one()
        att = self._ensure_imp_decl_xml()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=1",
            "target": "self",
        }

    # ===== Procesamiento de Factura PDF con IA/OCR =====
    def action_process_invoice_pdf(self):
        """
        Encola el procesamiento de la factura en background y devuelve notificación inmediata.
        Si se pasa context force_sync=True o process_async=False, ejecuta en línea.
        """
        force_sync = self.env.context.get("force_sync") or (self.env.context.get("process_async") is False)
        if force_sync:
            return self._process_invoice_pdf_sync()
        
        for rec in self:
            if not rec.factura_pdf:
                raise UserError(_("No hay factura PDF adjunta para procesar"))
            rec.write({
                "factura_estado_procesamiento": "en_cola",
                "factura_mensaje_error": _("Factura en cola para procesamiento en background"),
                "factura_en_cola_at": fields.Datetime.now(),
                "factura_procesada": False,
            })
            # Encolar con queue_job si está disponible; si no, forzar sync
            rec.with_delay(
                description=f"Procesar factura PDF expediente {rec.name}",
                max_retries=3,
                identity_key=lambda job, rec_id=rec.id: f"process_pdf_{rec_id}",
            ).process_pdf_job()
        # Notificación inmediata
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Procesamiento en background"),
                "message": _("La factura se ha encolado y se procesará en segundo plano. Puedes seguir trabajando, la vista se actualizará al terminar."),
                "type": "info",
                "sticky": False,
            },
        }
    
    def action_procesar_todas_facturas(self):
        """Procesa todas las facturas (PDF) del expediente; las encola para procesamiento en background."""
        self.ensure_one()
        facturas = self.factura_ids.filtered(
            lambda f: f.factura_pdf
            and f.factura_estado_procesamiento in ("pendiente", "sin_factura")
            and not f.factura_procesada
        )
        if not facturas:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin facturas para procesar"),
                    "message": _("No hay facturas pendientes para procesar."),
                    "type": "info",
                    "sticky": False,
                },
            }
        facturas_procesadas = 0
        for factura in facturas:
            try:
                factura.write({
                    "factura_estado_procesamiento": "en_cola",
                    "factura_mensaje_error": _("Factura en cola para procesamiento en background"),
                    "factura_en_cola_at": fields.Datetime.now(),
                    "factura_procesada": False,
                })
                factura.with_delay(
                    description=_("Procesar factura PDF %s", factura.name),
                    max_retries=3,
                    identity_key=lambda job, rec_id=factura.id: f"process_pdf_factura_{rec_id}",
                ).process_pdf_job()
                facturas_procesadas += 1
            except Exception as e:
                _logger.exception("Error encolando factura %s: %s", factura.name, e)
                factura.write({
                    "factura_estado_procesamiento": "error",
                    "factura_mensaje_error": _("Error al encolar: %s") % str(e),
                })
        
        # Notificación
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Procesamiento iniciado"),
                "message": _("Se han encolado %d factura(s) para procesamiento en segundo plano. Puedes seguir trabajando, la vista se actualizará al terminar.") % facturas_procesadas,
                "type": "success",
                "sticky": False,
            },
        }

    def _normalize_partida_arancelaria(self, partida):
        """
        Normaliza una partida arancelaria a 10 dígitos.
        Si tiene menos de 10 dígitos, rellena con ceros al final (a la derecha).
        Si tiene más de 10 dígitos, trunca a 10.
        Si no es válida, devuelve None.
        IMPORTANTE: Preserva códigos de exactamente 10 dígitos tal cual vienen.
        """
        if not partida:
            return None
        # Convertir a string preservando el formato original
        # Si viene como número, convertir manteniendo todos los dígitos
        if isinstance(partida, (int, float)):
            # Convertir a string sin formateo adicional para preservar ceros finales
            partida_str = str(int(partida))
        else:
            partida_str = str(partida).strip()
        # Limpiar espacios, puntos y otros caracteres
        partida_limpia = partida_str.replace(' ', '').replace('.', '').replace('-', '')
        # Solo mantener dígitos
        partida_limpia = ''.join(filter(str.isdigit, partida_limpia))
        if not partida_limpia:
            return None
        # Si tiene más de 10 dígitos, truncar
        if len(partida_limpia) > 10:
            partida_limpia = partida_limpia[:10]
        # Si tiene menos de 10 dígitos, rellenar con ceros al final (a la derecha)
        if len(partida_limpia) < 10:
            partida_limpia = partida_limpia.ljust(10, '0')
        # Si tiene exactamente 10 dígitos, devolver tal cual (sin modificar)
        return partida_limpia

    def action_realizar_verificacion_ia(self):
        """
        Realiza la verificación IA de las líneas del expediente sin procesar la factura completa.
        Valida partidas arancelarias, sugiere correcciones y normaliza a 10 dígitos.
        """
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("No hay líneas de productos para verificar. Primero debes procesar la factura o agregar líneas manualmente."))
            
            # Obtener servicio OCR
            ocr_service = self.env['aduanas.invoice.ocr.service']
            
            # Realizar validación IA
            ai_validation = None
            ai_validation_error = None
            try:
                ai_validation = ocr_service.validate_invoice_consistency(rec)
                ai_validation_error = ai_validation.get("error") if ai_validation else None
            except Exception as val_err:
                ai_validation_error = str(val_err)
                _logger.warning("Error ejecutando verificación IA: %s", val_err)
            
            if ai_validation_error:
                raise UserError(_("Error al realizar la verificación IA: %s") % ai_validation_error)
            
            if not ai_validation:
                raise UserError(_("No se pudo obtener resultados de la verificación IA"))
            
            # Contexto para evitar notificaciones durante la actualización
            ctx_no_mail = {
                'mail_notrack': True,
                'tracking_disable': True,
            }
            
            # Actualizar líneas con resultados de IA
            lineas_result = ai_validation.get("lineas", []) or []
            lines_sorted = rec.line_ids.sorted(lambda l: l.item_number or l.id)
            cambios_lineas = {}
            
            for res in lineas_result:
                try:
                    idx = int(res.get("index", 0))
                except Exception:
                    idx = 0
                if not idx or idx > len(lines_sorted):
                    continue
                line = lines_sorted[idx - 1]
                estado = (res.get("estado") or "pendiente").lower()
                if estado not in ("correcto", "corregido", "sugerido"):
                    estado = "pendiente"
                detalle = res.get("detalle") or ""
                partida_validada = res.get("partida_validada")
                
                # Limpiar y normalizar partida_validada
                if partida_validada in (None, "null", "None", ""):
                    partida_validada = None
                else:
                    # Convertir a string preservando el formato original (importante para códigos con ceros)
                    # Si viene como número, convertirlo a string manteniendo todos los dígitos
                    # IMPORTANTE: No usar formateo con :010d porque rellena con ceros a la izquierda
                    # En su lugar, convertir directamente a string para preservar el formato original
                    if isinstance(partida_validada, (int, float)):
                        # Convertir a string sin formateo adicional para preservar ceros finales
                        # Si el número es 1212210000, str() debería dar "1212210000"
                        partida_validada = str(int(partida_validada))
                    else:
                        partida_validada = str(partida_validada).strip() if partida_validada else None
                    # Normalizar a 10 dígitos (solo si es necesario, preserva códigos de 10 dígitos tal cual)
                    if partida_validada:
                        partida_validada = rec._normalize_partida_arancelaria(partida_validada)
                
                vals_linea = {
                    "verificacion_estado": estado,
                    "verificacion_detalle": detalle,
                }
                
                # Actualizar partida según el estado
                if estado == "corregido" and partida_validada:
                    # Si está corregida, siempre actualizar la partida (normalizada a 10 dígitos)
                    vals_linea["partida"] = partida_validada
                    if partida_validada not in detalle:
                        vals_linea["verificacion_detalle"] = f"{detalle} (Corregida: {partida_validada})" if detalle else f"Partida corregida: {partida_validada}"
                elif estado == "sugerido" and partida_validada:
                    # Si está sugerida y no hay partida actual, actualizarla automáticamente
                    if not line.partida or not line.partida.strip():
                        vals_linea["partida"] = partida_validada
                        if partida_validada not in detalle:
                            vals_linea["verificacion_detalle"] = f"{detalle} (Sugerida: {partida_validada})" if detalle else f"Partida sugerida: {partida_validada}"
                    else:
                        # Si ya hay partida, solo añadir al detalle
                        if partida_validada not in detalle:
                            vals_linea["verificacion_detalle"] = f"{detalle} (Sugerida: {partida_validada})" if detalle else f"Sugerida: {partida_validada}"
                
                cambios_lineas[line.id] = vals_linea
            
            # Normalizar partidas existentes a 10 dígitos
            for line in rec.line_ids:
                if line.partida:
                    partida_normalizada = rec._normalize_partida_arancelaria(line.partida)
                    if partida_normalizada and partida_normalizada != line.partida:
                        if line.id not in cambios_lineas:
                            cambios_lineas[line.id] = {}
                        cambios_lineas[line.id]["partida"] = partida_normalizada
            
            # Aplicar cambios a las líneas
            for line_id, vals_linea in cambios_lineas.items():
                line = rec.line_ids.browse(line_id)
                if line.exists():
                    line.with_context(**ctx_no_mail).write(vals_linea)
            
            # Crear mensaje en el chatter
            mensaje_chatter = _("🤖 Verificación IA completada<br/><br/>")
            
            # Resumen de totales
            totales_info = ai_validation.get("totales") or {}
            if totales_info:
                estado_totales = _("✅ OK") if totales_info.get("es_coherente") else _("⚠️ Revisar")
                detalle_totales = totales_info.get("detalle") or ""
                diferencia = totales_info.get("diferencia")
                diferencia_txt = f" (diferencia: {diferencia})" if diferencia is not None else ""
                mensaje_chatter += _("📊 Totales: %s. %s%s<br/>") % (estado_totales, detalle_totales, diferencia_txt)
            
            # Resumen de líneas
            if lineas_result:
                mensaje_chatter += _("<br/>📦 Líneas revisadas:<br/>")
                for res in lineas_result:
                    idx_txt = res.get("index")
                    estado_txt = (res.get("estado") or "").capitalize()
                    detalle_txt = res.get("detalle") or ""
                    partida_txt = res.get("partida_validada") or ""
                    if partida_txt:
                        partida_txt = rec._normalize_partida_arancelaria(partida_txt) or partida_txt
                    extra = f" | Partida: {partida_txt}" if partida_txt else ""
                    mensaje_chatter += f"Línea {idx_txt}: {estado_txt}{extra}. {detalle_txt}<br/>"
            
            if ai_validation.get("resumen"):
                mensaje_chatter += f"<br/>{ai_validation.get('resumen')}<br/>"
            
            # Crear mensaje en el chatter
            try:
                subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
                if not subtype:
                    subtype = self.env['mail.message.subtype'].search([('name', '=', 'Note')], limit=1)
                
                self.env['mail.message'].sudo().create({
                    'model': 'aduana.expediente',
                    'res_id': rec.id,
                    'message_type': 'notification',
                    'subtype_id': subtype.id if subtype else False,
                    'body': mensaje_chatter,
                    'author_id': False,
                    'email_from': False,
                })
            except Exception as msg_error:
                _logger.warning("No se pudo crear mensaje en chatter: %s", msg_error)
            
            # Forzar recarga del registro
            rec.invalidate_recordset()
            rec.refresh()
            
            # Retornar acción para recargar la vista del expediente
            # Esto automáticamente recargará la vista con los datos actualizados
            return {
                "type": "ir.actions.act_window",
                "res_model": "aduana.expediente",
                "res_id": rec.id,
                "view_mode": "form",
                "target": "current",
            }
        
        return True

    def cron_process_invoice_pdf_queue(self, limit=2):
        """Procesa en background las facturas encoladas (expedientes con PDF directo y facturas del modelo factura)."""
        # Expedientes con factura PDF directa (una sola factura en el expediente)
        pending_exp = self.search([("factura_estado_procesamiento", "=", "en_cola")], limit=limit, order="factura_en_cola_at asc, id asc")
        for rec in pending_exp:
            try:
                rec.with_delay(
                    description=_("Procesar factura PDF expediente %s", rec.name),
                    max_retries=3,
                    identity_key=lambda job, rec_id=rec.id: f"process_pdf_{rec_id}",
                ).process_pdf_job()
            except Exception as e:
                _logger.exception("Error procesando factura en cola (expediente %s): %s", rec.id, e)
        # Facturas (PDF) del expediente (modelo aduana.expediente.factura)
        Factura = self.env["aduana.expediente.factura"]
        pending_facturas = Factura.search(
            [("factura_estado_procesamiento", "=", "en_cola")],
            limit=limit,
            order="factura_en_cola_at asc, id asc",
        )
        for factura in pending_facturas:
            try:
                factura.with_delay(
                    description=_("Procesar factura PDF %s", factura.name),
                    max_retries=3,
                    identity_key=lambda job, fid=factura.id: f"process_pdf_factura_{fid}",
                ).process_pdf_job()
            except Exception as e:
                _logger.exception("Error procesando factura en cola (factura %s): %s", factura.id, e)
        return True

    # Job encolado (configuración de canal/reintentos se gestiona en with_delay o via queue.job.function)
    @job
    def process_pdf_job(self):
        """Job de cola para procesar la factura sin límite del hilo HTTP/cron."""
        # Desactivar prefetch para evitar problemas de caché durante transacciones largas
        self = self.with_context(prefetch_fields=False)
        for rec in self:
            try:
                rec.with_context(process_async=True)._process_invoice_pdf_sync()
            except Exception as e:
                # Marcar estado de error con un único write final
                msg = _("Error procesando factura en background: %s") % (str(e),)
                ctx_no_mail = dict(self.env.context, mail_notrack=True, tracking_disable=True, prefetch_fields=False)
                
                # Verificar si se está procesando una factura específica
                factura_id = self.env.context.get('factura_id')
                if factura_id:
                    factura = self.env['aduana.expediente.factura'].browse(factura_id)
                    if factura.exists():
                        factura.with_context(**ctx_no_mail).write({
                            "factura_estado_procesamiento": "error",
                            "factura_mensaje_error": msg,
                        })
                        _logger.exception("Error en job de factura %s del expediente %s", factura_id, rec.id)
                    else:
                        # Si la factura no existe, actualizar el expediente (modo legacy)
                        rec.with_context(**ctx_no_mail).write({
                            "factura_estado_procesamiento": "error",
                            "factura_mensaje_error": msg,
                        })
                        _logger.exception("Error en job de factura expediente %s (factura %s no existe)", rec.id, factura_id)
                else:
                    # Modo legacy: actualizar el expediente
                    rec.with_context(**ctx_no_mail).write({
                        "factura_estado_procesamiento": "error",
                        "factura_mensaje_error": msg,
                    })
                    _logger.exception("Error en job de factura expediente %s", rec.id)
                raise

    def _process_factura_pdf_sync(self, factura):
        """Procesa el PDF de una factura (aduana.expediente.factura) y rellena este expediente con las líneas."""
        self.ensure_one()
        return self.with_context(factura_id=factura.id)._process_invoice_pdf_sync()

    def _process_invoice_pdf_sync(self):
        """
        Procesa la factura PDF adjunta, extrae datos con OCR/IA y rellena la expedición.
        Si viene factura_id en el contexto, procesa esa factura (aduana.expediente.factura) del expediente.
        """
        for rec in self:
            # Desactivar notificaciones de email durante todo el proceso
            ctx_no_mail = dict(self.env.context)
            ctx_no_mail.update({
                'mail_notrack': True,
                'mail_create_nolog': True,
                'mail_create_nosubscribe': True,
                'tracking_disable': True,
                'mail_notify_force_send': False,
                'mail_auto_delete': False,
                'default_message_type': 'notification',
                'prefetch_fields': False,  # Evitar problemas de caché en transacciones largas
            })
            
            # factura_id en contexto = procesar una factura (aduana.expediente.factura) del expediente
            factura_id = self.env.context.get('factura_id')
            factura = None
            if factura_id:
                factura = self.env['aduana.expediente.factura'].browse(factura_id)
                if not factura.exists():
                    raise UserError(_("La factura especificada no existe"))
                pdf_data = factura.factura_pdf
                if not pdf_data:
                    factura.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': _("No hay factura PDF adjunta para procesar")
                    })
                    raise UserError(_("No hay factura PDF adjunta para procesar"))
            else:
                # Expediente con factura PDF directa (una sola factura en el expediente)
                if not rec.factura_pdf:
                    rec.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': _("No hay factura PDF adjunta para procesar")
                    })
                    raise UserError(_("No hay factura PDF adjunta para procesar"))
                pdf_data = rec.factura_pdf
            
            # Obtener servicio OCR
            ocr_service = self.env["aduanas.invoice.ocr.service"]
            
            # Acumulador de cambios para el write final
            cambios_finales = {}
            cambios_factura = {}  # Cambios para la factura específica si existe
            mensaje_chatter = None
            
            # Extraer datos de la factura (pdf_data ya viene asignado arriba si hay factura)
            try:
                if not factura:
                    pdf_data = rec.factura_pdf
                if not pdf_data:
                    cambios_finales.update({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': _("No hay datos de PDF para procesar")
                    })
                    raise UserError(_("No hay datos de PDF para procesar"))
                
                # En Odoo, los campos Binary siempre vienen como string base64
                # Si viene como bytes, convertirlo a base64
                if isinstance(pdf_data, bytes):
                    import base64
                    pdf_data = base64.b64encode(pdf_data).decode('utf-8')
                
                invoice_data = ocr_service.extract_invoice_data(pdf_data)
                
                # Validar que se extrajo texto
                if invoice_data.get("error"):
                    error_msg = invoice_data.get("error", _("Error desconocido al procesar el PDF"))
                    if factura:
                        factura.with_context(**ctx_no_mail).write({
                            'factura_estado_procesamiento': 'error',
                            'factura_mensaje_error': error_msg
                        })
                    else:
                        cambios_finales.update({
                            'factura_estado_procesamiento': 'error',
                            'factura_mensaje_error': error_msg
                        })
                    mensaje_chatter = _("❌ Error al procesar factura: %s") % error_msg
                    raise UserError(_("Error al procesar el PDF: %s") % error_msg)
                
                # Validar datos mínimos extraídos
                advertencias = []
                datos_extraidos = []
                
                if not invoice_data.get("texto_extraido"):
                    advertencias.append(_("No se pudo extraer texto del PDF. Puede ser una imagen escaneada de baja calidad."))
                
                if not invoice_data.get("remitente_nombre") and not invoice_data.get("remitente_nif"):
                    advertencias.append(_("No se pudo identificar el remitente en la factura."))
                else:
                    datos_extraidos.append(_("Remitente: %s") % (invoice_data.get("remitente_nombre") or invoice_data.get("remitente_nif")))
                
                if not invoice_data.get("consignatario_nombre") and not invoice_data.get("consignatario_nif"):
                    advertencias.append(_("No se pudo identificar el consignatario en la factura."))
                else:
                    datos_extraidos.append(_("Consignatario: %s") % (invoice_data.get("consignatario_nombre") or invoice_data.get("consignatario_nif")))
                
                if not invoice_data.get("valor_total"):
                    advertencias.append(_("No se pudo extraer el valor total de la factura."))
                else:
                    datos_extraidos.append(_("Valor: %s %s") % (invoice_data.get("valor_total", 0), invoice_data.get("moneda", "EUR")))
                
                if not invoice_data.get("numero_factura"):
                    advertencias.append(_("No se pudo extraer el número de factura."))
                else:
                    datos_extraidos.append(_("Nº Factura: %s") % invoice_data.get("numero_factura"))
                
                # Advertencias sobre CIF/NIF faltantes
                if not invoice_data.get("remitente_nif"):
                    advertencias.append(_("No se pudo extraer el CIF/NIF del remitente."))
                if not invoice_data.get("consignatario_nif"):
                    advertencias.append(_("No se pudo extraer el CIF/NIF del consignatario."))
                
                # Advertencias sobre incoterm
                if invoice_data.get("_incoterm_mapeado"):
                    mapeo = invoice_data["_incoterm_mapeado"]
                    advertencias.append(_("Incoterm '%s' mapeado a '%s' (formato estándar)") % (mapeo["original"], mapeo["mapeado"]))
                if invoice_data.get("_incoterm_invalido"):
                    advertencias.append(_("Incoterm '%s' no es válido y no se pudo asignar. Revise manualmente.") % invoice_data["_incoterm_invalido"])
                
                if not invoice_data.get("lineas"):
                    advertencias.append(_("No se pudieron extraer líneas de productos. Deberás agregarlas manualmente."))
                else:
                    datos_extraidos.append(_("Líneas extraídas: %d") % len(invoice_data.get("lineas", [])))
                
                # Rellenar expediente; si hay factura (modelo factura), las líneas se crean en este expediente con factura_id
                rec = rec.with_context(**ctx_no_mail)
                if factura:
                    ocr_service.fill_expediente_from_invoice(rec, invoice_data, factura=factura)
                else:
                    ocr_service.fill_expediente_from_invoice(rec, invoice_data)
                expediente_con_lineas = rec
                # Actualizar valor total con la suma de las líneas (el usuario puede editarlo después en Totales)
                if expediente_con_lineas.line_ids:
                    total_lineas = sum(expediente_con_lineas.line_ids.mapped("valor_linea") or [0])
                    expediente_con_lineas.write({"valor_factura": total_lineas})

                # Acumular estado final (en factura si existe, sino en expediente)
                if advertencias:
                    estado_final = 'advertencia'
                    mensaje_final = "\n".join([_("ADVERTENCIAS:")] + advertencias)
                else:
                    estado_final = 'completado'
                    mensaje_final = False
                
                if factura:
                    cambios_factura.update({
                        'factura_estado_procesamiento': estado_final,
                        'factura_mensaje_error': mensaje_final,
                        'fecha_procesamiento': fields.Datetime.now(),
                        'factura_procesada': True,
                    })
                else:
                    # Modo legacy: guardar en expediente
                    cambios_finales.update({
                        'factura_estado_procesamiento': estado_final,
                        'factura_mensaje_error': mensaje_final
                    })
                
                # Validación de coherencia y partidas con IA (sobre el expediente que tiene las líneas)
                ai_validation = None
                ai_validation_error = None
                lineas_result = []
                try:
                    ctx_validation = dict(ctx_no_mail)
                    if factura:
                        ctx_validation["factura_id"] = factura.id
                    ai_validation = ocr_service.with_context(**ctx_validation).validate_invoice_consistency(expediente_con_lineas)
                    ai_validation_error = ai_validation.get("error") if ai_validation else None
                except Exception as val_err:
                    ai_validation_error = str(val_err)
                    _logger.warning("Error ejecutando validación IA de coherencia: %s", val_err)
                
                # Actualizar líneas con resultados de IA (estado/verificación y partida sugerida)
                # Acumular cambios de líneas en un diccionario (línea_id -> cambios)
                cambios_lineas = {}
                if ai_validation and not ai_validation_error:
                    lineas_result = ai_validation.get("lineas", []) or []
                    # Si procesamos una factura, solo las líneas de esa factura; si no, todas las del expediente
                    lineas_a_validar = expediente_con_lineas.line_ids.filtered(lambda l: not factura or l.factura_id == factura)
                    lines_sorted = lineas_a_validar.sorted(lambda l: l.item_number or l.id)
                    for res in lineas_result:
                        try:
                            idx = int(res.get("index", 0))
                        except Exception:
                            idx = 0
                        if not idx or idx > len(lines_sorted):
                            continue
                        line = lines_sorted[idx - 1]
                        estado = (res.get("estado") or "pendiente").lower()
                        if estado not in ("correcto", "corregido", "sugerido"):
                            estado = "pendiente"
                        detalle = res.get("detalle") or ""
                        partida_validada = res.get("partida_validada")
                        # Limpiar partida_validada si es null, "null", "None" o vacío
                        if partida_validada in (None, "null", "None", ""):
                            partida_validada = None
                        else:
                            # Convertir a string preservando el formato original (importante para códigos con ceros)
                            # Si viene como número, convertirlo a string manteniendo todos los dígitos
                            # IMPORTANTE: No usar formateo con :010d porque rellena con ceros a la izquierda
                            # En su lugar, convertir directamente a string para preservar el formato original
                            if isinstance(partida_validada, (int, float)):
                                # Convertir a string sin formateo adicional para preservar ceros finales
                                # Si el número es 1212210000, str() debería dar "1212210000"
                                partida_validada = str(int(partida_validada))
                            else:
                                partida_validada = str(partida_validada).strip() if partida_validada else None
                            # Normalizar a 10 dígitos (solo si es necesario, preserva códigos de 10 dígitos tal cual)
                            if partida_validada:
                                partida_validada = expediente_con_lineas._normalize_partida_arancelaria(partida_validada)
                        
                        vals_linea = {
                            "verificacion_estado": estado,
                            "verificacion_detalle": detalle,
                        }
                        # Actualizar partida según el estado
                        if estado == "corregido" and partida_validada:
                            # Si está corregida, siempre actualizar la partida (normalizada a 10 dígitos)
                            vals_linea["partida"] = partida_validada
                            if partida_validada not in detalle:
                                vals_linea["verificacion_detalle"] = f"{detalle} (Corregida: {partida_validada})" if detalle else f"Partida corregida: {partida_validada}"
                        elif estado == "sugerido" and partida_validada:
                            # Si está sugerida y no hay partida actual, actualizarla automáticamente
                            if not line.partida or not line.partida.strip():
                                vals_linea["partida"] = partida_validada
                                if partida_validada not in detalle:
                                    vals_linea["verificacion_detalle"] = f"{detalle} (Sugerida: {partida_validada})" if detalle else f"Partida sugerida: {partida_validada}"
                            else:
                                # Si ya hay partida, solo añadir al detalle
                                if partida_validada not in detalle:
                                    vals_linea["verificacion_detalle"] = f"{detalle} (Sugerida: {partida_validada})" if detalle else f"Sugerida: {partida_validada}"
                        # Acumular cambios de líneas en diccionario (se escribirán después del write principal)
                        cambios_lineas[line.id] = vals_linea
                
                # Normalizar partidas existentes a 10 dígitos (solo las de esta factura si aplica)
                lineas_a_normalizar = expediente_con_lineas.line_ids.filtered(lambda l: not factura or l.factura_id == factura)
                for line in lineas_a_normalizar:
                    if line.partida:
                        partida_normalizada = expediente_con_lineas._normalize_partida_arancelaria(line.partida)
                        if partida_normalizada and partida_normalizada != line.partida:
                            if line.id not in cambios_lineas:
                                cambios_lineas[line.id] = {}
                            cambios_lineas[line.id]["partida"] = partida_normalizada
                
                # Crear mensaje detallado para el chatter con todos los datos extraídos
                mensaje_chatter = _("✅ Factura procesada correctamente<br/><br/>")
                
                # Resumen de datos extraídos
                mensaje_chatter += _("📋 Resumen de datos extraídos:<br/><br/>")
                for dato in datos_extraidos:
                    mensaje_chatter += f"{dato}<br/>"
                mensaje_chatter += "<br/>"
                
                # Detalles de remitente
                if invoice_data.get("remitente_nombre") or invoice_data.get("remitente_nif"):
                    mensaje_chatter += _("📤 Remitente:<br/><br/>")
                    if invoice_data.get("remitente_nombre"):
                        mensaje_chatter += f"Nombre: {invoice_data.get('remitente_nombre')}<br/>"
                    if invoice_data.get("remitente_nif"):
                        mensaje_chatter += f"NIF: {invoice_data.get('remitente_nif')}<br/>"
                    if invoice_data.get("remitente_direccion"):
                        mensaje_chatter += f"Dirección: {invoice_data.get('remitente_direccion')}<br/>"
                    mensaje_chatter += "<br/>"
                
                # Detalles de consignatario
                if invoice_data.get("consignatario_nombre") or invoice_data.get("consignatario_nif"):
                    mensaje_chatter += _("📥 Consignatario:<br/><br/>")
                    if invoice_data.get("consignatario_nombre"):
                        mensaje_chatter += f"Nombre: {invoice_data.get('consignatario_nombre')}<br/>"
                    if invoice_data.get("consignatario_nif"):
                        mensaje_chatter += f"NIF: {invoice_data.get('consignatario_nif')}<br/>"
                    if invoice_data.get("consignatario_direccion"):
                        mensaje_chatter += f"Dirección: {invoice_data.get('consignatario_direccion')}<br/>"
                    mensaje_chatter += "<br/>"
                
                # Información de factura
                mensaje_chatter += _("🧾 Información de factura:<br/><br/>")
                if invoice_data.get("numero_factura"):
                    mensaje_chatter += f"Nº Factura: {invoice_data.get('numero_factura')}<br/>"
                if invoice_data.get("fecha_factura"):
                    mensaje_chatter += f"Fecha: {invoice_data.get('fecha_factura')}<br/>"
                if invoice_data.get("valor_total"):
                    mensaje_chatter += f"Valor Total: {invoice_data.get('valor_total')} {invoice_data.get('moneda', 'EUR')}<br/>"
                if invoice_data.get("incoterm"):
                    mensaje_chatter += f"Incoterm: {invoice_data.get('incoterm')}<br/>"
                mensaje_chatter += "<br/>"
                
                # Información de transporte
                if invoice_data.get("transportista") or invoice_data.get("matricula") or invoice_data.get("codigo_transporte"):
                    mensaje_chatter += _("🚚 Información de transporte:<br/><br/>")
                    if invoice_data.get("transportista"):
                        mensaje_chatter += f"Transportista: {invoice_data.get('transportista')}<br/>"
                    if invoice_data.get("matricula"):
                        mensaje_chatter += f"Matrícula: {invoice_data.get('matricula')}<br/>"
                    if invoice_data.get("codigo_transporte"):
                        mensaje_chatter += f"Código: {invoice_data.get('codigo_transporte')}<br/>"
                    if invoice_data.get("referencia_transporte"):
                        mensaje_chatter += f"Referencia: {invoice_data.get('referencia_transporte')}<br/>"
                    if invoice_data.get("remolque"):
                        mensaje_chatter += f"Remolque: {invoice_data.get('remolque')}<br/>"
                    mensaje_chatter += "<br/>"
                
                # Líneas de productos
                if invoice_data.get("lineas"):
                    num_lineas = len(invoice_data.get("lineas", []))
                    mensaje_chatter += _("📦 Líneas de productos extraídas ({0}):<br/><br/>").format(num_lineas)
                    for idx, linea in enumerate(invoice_data.get("lineas", []), 1):
                        mensaje_chatter += f"Línea {idx}: "
                        if linea.get("articulo"):
                            mensaje_chatter += f"Art. {linea.get('articulo')} - "
                        if linea.get("descripcion"):
                            descripcion = linea.get('descripcion')
                            mensaje_chatter += descripcion
                        if linea.get("cantidad") or linea.get("unidades"):
                            cantidad = linea.get("cantidad") or linea.get("unidades")
                            mensaje_chatter += f" | Cantidad: {cantidad}"
                        if linea.get("total"):
                            mensaje_chatter += f" | Total: {linea.get('total')} {invoice_data.get('moneda', 'EUR')}"
                        elif linea.get("precio_unitario") and (linea.get("cantidad") or linea.get("unidades")):
                            # Calcular total si no está disponible
                            precio = linea.get("precio_unitario")
                            cantidad = linea.get("cantidad") or linea.get("unidades") or 1.0
                            total = precio * cantidad
                            mensaje_chatter += f" | Total: {total} {invoice_data.get('moneda', 'EUR')}"
                        mensaje_chatter += "<br/>"
                    mensaje_chatter += "<br/>"
                
                # Método usado
                if invoice_data.get("metodo_usado"):
                    mensaje_chatter += f"Método de extracción: {invoice_data.get('metodo_usado')}<br/>"
                
                # Advertencias si las hay
                if advertencias:
                    mensaje_chatter += "<br/>"
                    mensaje_chatter += _("⚠️ Advertencias:<br/>")
                    for adv in advertencias:
                        mensaje_chatter += f"• {adv}<br/>"
                
                # Resumen de verificación IA (totales y partidas)
                if ai_validation and not ai_validation_error:
                    mensaje_chatter += "<br/>"
                    mensaje_chatter += _("🤖 Verificación IA:<br/>")
                    totales_info = ai_validation.get("totales") or {}
                    if totales_info:
                        estado_totales = _("OK") if totales_info.get("es_coherente") else _("Revisar")
                        detalle_totales = totales_info.get("detalle") or ""
                        diferencia = totales_info.get("diferencia")
                        diferencia_txt = f" (diferencia: {diferencia})" if diferencia is not None else ""
                        mensaje_chatter += f"Totales: {estado_totales}. {detalle_totales}{diferencia_txt}<br/>"
                    if lineas_result:
                        mensaje_chatter += _("Líneas revisadas:<br/>")
                        for res in lineas_result:
                            idx_txt = res.get("index")
                            estado_txt = (res.get("estado") or "").capitalize()
                            detalle_txt = res.get("detalle") or ""
                            partida_txt = res.get("partida_validada") or ""
                            extra = f" | Partida: {partida_txt}" if partida_txt else ""
                            mensaje_chatter += f"Línea {idx_txt}: {estado_txt}{extra}. {detalle_txt}<br/>"
                    if ai_validation.get("resumen"):
                        mensaje_chatter += f"{ai_validation.get('resumen')}<br/>"
                elif ai_validation_error:
                    mensaje_chatter += "<br/>" + _("🤖 Verificación IA no disponible: %s<br/>") % ai_validation_error
                
                # PASO 1: Escribir cambios de líneas primero (si hay cambios acumulados)
                if cambios_lineas:
                    for line_id, vals_linea in cambios_lineas.items():
                        line = expediente_con_lineas.line_ids.browse(line_id)
                        if line.exists():
                            line.with_context(**ctx_no_mail).write(vals_linea)
                
                # PASO 2: ÚNICO WRITE FINAL con todos los cambios acumulados
                if factura and cambios_factura:
                    # Escribir cambios en la factura específica
                    factura.with_context(**ctx_no_mail).write(cambios_factura)
                elif cambios_finales:
                    # Modo legacy: escribir cambios en el expediente
                    cambios_finales['factura_procesada'] = True
                    cambios_finales['fecha_procesamiento'] = fields.Datetime.now()
                    rec.with_context(**ctx_no_mail).write(cambios_finales)
                
                # PASO 3: Crear mensaje en el chatter SOLO AL FINAL (después del write) en el expediente principal
                if mensaje_chatter:
                    try:
                        chatter_expediente = expediente_con_lineas  # Mensaje en el expediente que tiene las líneas
                        subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
                        if not subtype:
                            subtype = self.env['mail.message.subtype'].search([('name', '=', 'Note')], limit=1)
                        
                        self.env['mail.message'].sudo().create({
                            'model': 'aduana.expediente',
                            'res_id': chatter_expediente.id,
                            'message_type': 'notification',
                            'subtype_id': subtype.id if subtype else False,
                            'body': mensaje_chatter,
                            'author_id': False,  # Sistema, no usuario
                            'email_from': False,  # No intentar enviar correo
                        })
                    except Exception as msg_error:
                        # Si hay error al crear mensaje, solo loguear y continuar
                        _logger.warning("No se pudo crear mensaje en chatter (error ignorado): %s", msg_error)
                
                # Forzar recarga del registro para actualizar la vista
                rec.invalidate_recordset()
                
                # Preparar mensaje de notificación
                notif_title = _("Factura Procesada con Advertencias") if advertencias else _("Factura Procesada")
                notif_message = _("La factura se ha procesado, pero hay algunas advertencias. Revisa los datos extraídos.") if advertencias else _("La factura se ha procesado correctamente y los datos se han extraído.")
                
                # Si la llamada es síncrona (botón forzado), devolver notificación+reload; si viene de cron, solo continuar
                if self.env.context.get("force_sync") or self.env.context.get("process_async") is False:
                    # Mantener en el expediente principal (el que tiene las líneas) si procesamos una factura
                    id_para_vista = expediente_con_lineas.id if (factura and factura.expediente_id) else rec.id
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": notif_title,
                            "message": notif_message,
                            "type": "warning" if advertencias else "success",
                            "sticky": False,
                        },
                        "context": {
                            **self.env.context,
                            "active_id": id_para_vista,
                            "active_model": "aduana.expediente",
                        },
                        "res_model": "aduana.expediente",
                        "res_id": id_para_vista,
                        "view_mode": "form",
                        "target": "current",
                    }
            except UserError as ue:
                # Acumular error en cambios finales y escribir al final
                error_msg = str(ue)
                mensaje_chatter = _("❌ Error al procesar factura: %s") % error_msg
                # Escribir error en factura específica si existe, sino en expediente
                if factura:
                    factura.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': error_msg
                    })
                else:
                    cambios_finales.update({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': error_msg
                    })
                    if cambios_finales:
                        rec.with_context(**ctx_no_mail).write(cambios_finales)
                # Crear mensaje de error SOLO AL FINAL
                if mensaje_chatter:
                    try:
                        subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
                        if not subtype:
                            subtype = self.env['mail.message.subtype'].search([('name', '=', 'Note')], limit=1)
                        self.env['mail.message'].sudo().create({
                            'model': 'aduana.expediente',
                            'res_id': rec.id,
                            'message_type': 'notification',
                            'subtype_id': subtype.id if subtype else False,
                            'body': mensaje_chatter,
                            'author_id': False,
                            'email_from': False,
                        })
                    except Exception as msg_error:
                        _logger.warning("No se pudo crear mensaje de error en chatter (error ignorado): %s", msg_error)
                _logger.error("Error al procesar factura PDF (UserError): %s", error_msg)
                rec.invalidate_recordset()
                if self.env.context.get("force_sync") or self.env.context.get("process_async") is False:
                    return {
                        "type": "ir.actions.act_window",
                        "res_model": "aduana.expediente",
                        "res_id": rec.id,
                        "view_mode": "form",
                        "target": "current",
                    }
            except Exception as e:
                # Acumular error en cambios finales y escribir al final
                error_msg = str(e)
                mensaje_error_detallado = _("Error al procesar la factura: %s\n\nPosibles causas:\n- El PDF está corrupto o protegido\n- El PDF es una imagen escaneada de muy baja calidad\n- No se pudo conectar con el servicio de OCR\n- El formato del PDF no es compatible\n- Error en la API de OpenAI\n- Falta configuración de API Key") % error_msg
                mensaje_chatter = _("❌ Error al procesar factura: %s\n\nDetalles técnicos:\n%s") % (error_msg, mensaje_error_detallado)
                # Escribir error en factura específica si existe, sino en expediente
                if factura:
                    factura.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': mensaje_error_detallado
                    })
                else:
                    cambios_finales.update({
                        'factura_estado_procesamiento': 'error',
                        'factura_mensaje_error': mensaje_error_detallado
                    })
                    if cambios_finales:
                        rec.with_context(**ctx_no_mail).write(cambios_finales)
                # Crear mensaje de error SOLO AL FINAL
                if mensaje_chatter:
                    try:
                        subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
                        if not subtype:
                            subtype = self.env['mail.message.subtype'].search([('name', '=', 'Note')], limit=1)
                        self.env['mail.message'].sudo().create({
                            'model': 'aduana.expediente',
                            'res_id': rec.id,
                            'message_type': 'notification',
                            'subtype_id': subtype.id if subtype else False,
                            'body': mensaje_chatter,
                            'author_id': False,
                            'email_from': False,
                        })
                    except Exception as msg_error:
                        _logger.warning("No se pudo crear mensaje de error en chatter (error ignorado): %s", msg_error)
                _logger.exception("Error al procesar factura PDF: %s", e)
                rec.invalidate_recordset()
                if self.env.context.get("force_sync") or self.env.context.get("process_async") is False:
                    return {
                        "type": "ir.actions.act_window",
                        "res_model": "aduana.expediente",
                        "res_id": rec.id,
                        "view_mode": "form",
                        "target": "current",
                    }
        return True

    def action_generate_dua(self):
        """
        Genera el DUA (CC515C para exportación) sin procesar la factura.
        Requiere que los datos del expediente estén completos.
        """
        for rec in self:
            # Validar que es exportación
            if rec.direction != "export":
                raise UserError(_("Este botón solo genera DUA de exportación. Para importación, use 'Generar Declaración'."))
            
            # Validar datos mínimos necesarios
            if not rec.remitente:
                raise UserError(_("Debe especificar el remitente antes de generar el DUA."))
            
            if not rec.consignatario:
                raise UserError(_("Debe especificar el consignatario antes de generar el DUA."))
            
            if not rec.line_ids:
                raise UserError(_("Debe agregar al menos una línea de producto antes de generar el DUA."))
            
            # Generar DUA en formato CUSDEC EX1 (formato oficial)
            rec.action_generate_cc515c()
            rec.with_context(mail_notrack=True).message_post(
                body=_("DUA de exportación (CUSDEC EX1) generado."),
                subtype_xmlid='mail.mt_note'
            )
            
            # Invalidar el campo computed para que se recalcule
            rec.invalidate_recordset(['dua_generado'])
            return {
                "type": "ir.actions.act_window",
                "res_model": "aduana.expediente",
                "res_id": rec.id,
                "view_mode": "form",
                "target": "current",
            }
    
    def action_consultar_taric_manual(self):
        """Consulta TARIC para todas las partidas del expediente"""
        self.ensure_one()
        documento_model = self.env["aduana.expediente.documento.requerido"]
        # Llamar directamente a la lógica sin pasar por ensure_one
        return documento_model._consultar_taric_para_expediente(self)


class AduanaExpedienteDocumentoRequerido(models.Model):
    _name = "aduana.expediente.documento.requerido"
    _description = "Documento requerido por partida arancelaria (TARIC)"
    _order = "partida_arancelaria, mandatory desc, name"
    
    expediente_id = fields.Many2one("aduana.expediente", string="Expediente", required=True, ondelete="cascade", index=True)
    factura_id = fields.Many2one("aduana.expediente.factura", string="Factura", ondelete="set null", index=True,
                                 help="Factura del expediente asociada a este documento, si aplica")
    partida_arancelaria = fields.Char(string="Partida Arancelaria", required=True, index=True, help="Código de la partida arancelaria (8-10 dígitos)")
    codigo_documento = fields.Char(string="Código Documento", help="Código del documento según TARIC")
    name = fields.Char(string="Nombre del Documento", required=True, help="Nombre o descripción del documento requerido")
    description = fields.Text(string="Descripción", help="Descripción detallada del documento")
    mandatory = fields.Boolean(string="Obligatorio", default=True, help="Indica si el documento es obligatorio o opcional")
    documento_subido = fields.Binary(string="Documento Subido", help="Archivo del documento subido")
    documento_filename = fields.Char(string="Nombre Archivo", help="Nombre del archivo subido")
    fecha_subida = fields.Datetime(string="Fecha Subida", readonly=True, help="Fecha en que se subió el documento")
    subido_por = fields.Many2one("res.users", string="Subido por", readonly=True, help="Usuario que subió el documento")
    estado = fields.Selection([
        ("pendiente", "Pendiente"),
        ("subido", "Subido"),
        ("verificado", "Verificado"),
    ], string="Estado", default="pendiente", help="Estado del documento")
    notas = fields.Text(string="Notas", help="Notas adicionales sobre el documento")
    
    # Campos computed para previsualización
    is_pdf = fields.Boolean(string="Es PDF", compute="_compute_is_pdf", store=False)
    is_image = fields.Boolean(string="Es Imagen", compute="_compute_is_image", store=False)
    
    @api.depends('documento_filename')
    def _compute_is_pdf(self):
        """Determina si el documento subido es un PDF"""
        for rec in self:
            rec.is_pdf = rec.documento_filename and rec.documento_filename.lower().endswith('.pdf')
    
    @api.depends('documento_filename')
    def _compute_is_image(self):
        """Determina si el documento subido es una imagen"""
        for rec in self:
            if rec.documento_filename:
                ext = rec.documento_filename.lower()
                rec.is_image = ext.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))
            else:
                rec.is_image = False
    
    def action_view_documento_detalle(self):
        """Abre un popup con toda la información del documento y previsualización"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalle del Documento Requerido'),
            'res_model': 'aduana.expediente.documento.requerido',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('aduanas_transport.view_aduana_expediente_documento_requerido_popup').id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }
    
    @api.model
    def create(self, vals):
        """Al crear, registrar usuario y fecha si se sube documento"""
        if vals.get('documento_subido') and not vals.get('fecha_subida'):
            vals['fecha_subida'] = fields.Datetime.now()
            if not vals.get('subido_por'):
                vals['subido_por'] = self.env.user.id
            if vals.get('estado') == 'pendiente':
                vals['estado'] = 'subido'
        return super().create(vals)
    
    def write(self, vals):
        """Al actualizar, registrar usuario y fecha si se sube documento"""
        if vals.get('documento_subido'):
            vals['fecha_subida'] = fields.Datetime.now()
            if not vals.get('subido_por'):
                vals['subido_por'] = self.env.user.id
            if vals.get('estado') == 'pendiente' or not vals.get('estado'):
                vals['estado'] = 'subido'
        return super().write(vals)
    
    def action_consultar_taric(self):
        """Consulta la API TARIC para obtener documentos requeridos de todas las partidas del expediente"""
        # Si hay un recordset, usar el primero; si no, obtener del contexto
        if self:
            self.ensure_one()
            expediente = self.expediente_id
        else:
            # Obtener del contexto
            expediente_id = self.env.context.get('default_expediente_id')
            if not expediente_id:
                raise UserError(_("No se especificó el expediente para consultar TARIC."))
            expediente = self.env["aduana.expediente"].browse(expediente_id)
            if not expediente.exists():
                raise UserError(_("El expediente especificado no existe."))
        
        # Llamar al método auxiliar
        return self._consultar_taric_para_expediente(expediente)
    
    @api.model
    def _consultar_taric_para_expediente(self, expediente):
        """Método auxiliar para consultar TARIC para un expediente específico"""
        
        if not expediente.line_ids:
            raise UserError(_("No hay líneas de productos en el expediente para consultar documentos."))
        
        taric_service = self.env["aduanas.taric.service"]
        documentos_creados = 0
        documentos_actualizados = 0
        documentos_eliminados = 0
        errores_taric = []
        
        # Obtener todas las partidas únicas del expediente (normalizadas)
        partidas_en_lineas = expediente.line_ids.filtered(lambda l: l.partida and len(str(l.partida).strip()) >= 8).mapped('partida')
        partidas_unicas = []
        partidas_normalizadas = set()
        
        for partida in partidas_en_lineas:
            # Normalizar partida usando el método del expediente
            partida_limpia = expediente._normalize_partida_arancelaria(partida)
            if partida_limpia and len(partida_limpia) >= 8 and partida_limpia not in partidas_normalizadas:
                partidas_unicas.append(partida_limpia)
                partidas_normalizadas.add(partida_limpia)
        
        if not partidas_unicas:
            raise UserError(_("No hay partidas arancelarias válidas (mínimo 8 dígitos) en las líneas del expediente."))
        
        # PASO 1: Eliminar documentos TARIC que ya no corresponden a ninguna partida actual
        documentos_existentes = self.search([('expediente_id', '=', expediente.id)])
        for doc in documentos_existentes:
            # Normalizar la partida del documento para comparar usando el método del expediente
            doc_partida_limpia = expediente._normalize_partida_arancelaria(doc.partida_arancelaria)
            # Si la partida del documento no está en las partidas actuales, eliminarlo
            if not doc_partida_limpia or doc_partida_limpia not in partidas_normalizadas:
                doc.unlink()
                documentos_eliminados += 1
        
        # PASO 2: Consultar TARIC y actualizar/crear documentos para las partidas actuales
        for partida_limpia in partidas_unicas:
            # Consultar TARIC
            try:
                documentos_taric = taric_service.get_required_documents(
                    goods_code=partida_limpia,
                    country_code=expediente.pais_destino or ("AD" if expediente.direction == "export" else "ES"),
                    direction=expediente.direction
                )
            except Exception as e:
                _logger.warning("Error consultando TARIC para partida %s: %s", partida_limpia, e)
                errores_taric.append(f"Partida {partida_limpia}: {str(e)}")
                documentos_taric = []
            
            if documentos_taric:
                # Crear o actualizar documentos requeridos
                for doc_info in documentos_taric:
                    # Buscar si ya existe un documento con el mismo código y partida
                    existing = self.search([
                        ('expediente_id', '=', expediente.id),
                        ('partida_arancelaria', '=', partida_limpia),
                        ('codigo_documento', '=', doc_info.get('code', ''))
                    ], limit=1)
                    
                    if existing:
                        # Actualizar existente
                        existing.write({
                            'name': doc_info.get('name', ''),
                            'description': doc_info.get('description', ''),
                            'mandatory': doc_info.get('mandatory', True),
                        })
                        documentos_actualizados += 1
                    else:
                        # Crear nuevo
                        self.create({
                            'expediente_id': expediente.id,
                            'partida_arancelaria': partida_limpia,
                            'codigo_documento': doc_info.get('code', ''),
                            'name': doc_info.get('name', _("Documento requerido para partida %s") % partida_limpia),
                            'description': doc_info.get('description', ''),
                            'mandatory': doc_info.get('mandatory', True),
                            'estado': 'pendiente',
                        })
                        documentos_creados += 1
            # Si TARIC no devuelve documentos, NO crear ningún documento genérico
            # Solo se crean documentos cuando la API devuelve resultados
        
        # Construir mensaje con resultados
        mensaje_partes = []
        if documentos_eliminados > 0:
            mensaje_partes.append(_("%d documento(s) eliminado(s) (partidas obsoletas)") % documentos_eliminados)
        if documentos_creados > 0:
            mensaje_partes.append(_("%d documento(s) creado(s)") % documentos_creados)
        if documentos_actualizados > 0:
            mensaje_partes.append(_("%d documento(s) actualizado(s)") % documentos_actualizados)
        
        if errores_taric:
            mensaje = _("Consulta TARIC completada con advertencias:\n- %s\n\nErrores:\n%s") % (
                "\n- ".join(mensaje_partes) if mensaje_partes else _("Sin cambios"),
                "\n".join(errores_taric[:5])  # Mostrar máximo 5 errores
            )
            tipo_notificacion = 'warning'
        else:
            if mensaje_partes:
                mensaje = _("Consulta TARIC completada:\n- %s") % "\n- ".join(mensaje_partes)
            else:
                mensaje = _("Consulta TARIC completada: Sin cambios necesarios.")
            tipo_notificacion = 'success'
        
        # Si no se crearon documentos y hubo errores, sugerir añadir manualmente
        if documentos_creados == 0 and documentos_actualizados == 0 and documentos_eliminados == 0 and errores_taric:
            mensaje += _("\n\nNota: El servicio TARIC no está disponible. Puedes añadir los documentos requeridos manualmente.")
        
        # Publicar resumen en el chatter (siempre, con o sin errores)
        if errores_taric:
            mensaje_chatter = _("<b>🔍 Consulta TARIC - Resumen con errores</b><br/><br/>")
        else:
            mensaje_chatter = _("<b>🔍 Consulta TARIC - Resumen</b><br/><br/>")
        
        # Agregar información de documentos procesados
        if documentos_eliminados > 0:
            mensaje_chatter += _("📄 %d documento(s) eliminado(s) (partidas obsoletas)<br/>") % documentos_eliminados
        if documentos_creados > 0:
            mensaje_chatter += _("➕ %d documento(s) creado(s)<br/>") % documentos_creados
        if documentos_actualizados > 0:
            mensaje_chatter += _("🔄 %d documento(s) actualizado(s)<br/>") % documentos_actualizados
        if not mensaje_partes:
            mensaje_chatter += _("ℹ️ Sin cambios en documentos<br/>")
        
        # Agregar información de partidas consultadas
        if partidas_unicas:
            mensaje_chatter += _("<br/><b>📋 Partidas consultadas:</b><br/>")
            for partida in partidas_unicas[:10]:  # Mostrar hasta 10 partidas
                mensaje_chatter += f"• {partida}<br/>"
            if len(partidas_unicas) > 10:
                mensaje_chatter += _("... y %d partida(s) más.<br/>") % (len(partidas_unicas) - 10)
        
        # Agregar errores si los hay
        if errores_taric:
            mensaje_chatter += _("<br/><b>⚠️ Errores encontrados:</b><br/>")
            for error in errores_taric[:10]:  # Mostrar hasta 10 errores en el chatter
                mensaje_chatter += f"• {error}<br/>"
            
            if len(errores_taric) > 10:
                mensaje_chatter += _("<br/>... y %d error(es) más.") % (len(errores_taric) - 10)
        
        # Publicar mensaje en el chatter
        try:
            expediente.with_context(mail_notrack=True).message_post(
                body=mensaje_chatter,
                subtype_xmlid='mail.mt_note'
            )
        except Exception as msg_error:
            _logger.warning("No se pudo crear mensaje en chatter (error ignorado): %s", msg_error)
        
        # Forzar recarga del registro para actualizar la vista
        expediente.invalidate_recordset()
        expediente.refresh()
        
        # Retornar acción para recargar la vista del expediente
        # Esto automáticamente recargará la vista con los datos actualizados
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'aduana.expediente',
            'res_id': expediente.id,
            'view_mode': 'form',
            'target': 'current',
        }
