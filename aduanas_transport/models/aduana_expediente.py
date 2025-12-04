from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging
_logger = logging.getLogger(__name__)

class AduanaExpedienteLine(models.Model):
    _name = "aduana.expediente.line"
    _description = "Línea de mercancía (expediente aduanero)"
    expediente_id = fields.Many2one("aduana.expediente", required=True, ondelete="cascade")
    item_number = fields.Integer(string="Nº línea", default=1)
    partida = fields.Char(string="Partida arancelaria (NC)")
    descripcion = fields.Char()
    unidades = fields.Float(string="Unidades", default=1.0)
    bultos = fields.Integer(default=1)
    peso_bruto = fields.Float()
    peso_neto = fields.Float()
    valor_linea = fields.Float()
    descuento = fields.Float(string="Descuento (%)", help="Porcentaje de descuento aplicado a la línea")
    pais_origen = fields.Char(default="ES")

class AduanaExpediente(models.Model):
    _name = "aduana.expediente"
    _description = "Expediente Aduanero"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Nuevo"))
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

    # Totales factura
    valor_factura = fields.Float()
    moneda = fields.Selection([("EUR","EUR"),("USD","USD")], default="EUR")

    # Líneas
    line_ids = fields.One2many("aduana.expediente.line", "expediente_id", string="Líneas")

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
    
    @api.depends('factura_pdf', 'name')
    def _compute_documento_ids(self):
        """Obtiene todos los documentos (attachments) relacionados con este expediente"""
        for rec in self:
            # No podemos depender de 'id' en @api.depends, pero podemos usarlo en el método
            if rec.id:
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', rec._name),
                    ('res_id', '=', rec.id)
                ])
                rec.documento_ids = attachments
            else:
                rec.documento_ids = False
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create para asegurar que se creen attachments cuando se sube factura_pdf"""
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
        ("pendiente", "Pendiente de Procesar"),
        ("procesando", "Procesando..."),
        ("completado", "Completado"),
        ("error", "Error en Procesamiento"),
        ("advertencia", "Completado con Advertencias"),
    ], string="Estado Procesamiento", default="pendiente", readonly=True, help="Estado del procesamiento de la factura")
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
            elif estado == 'completado':
                # Verde para éxito
                if mensaje:
                    rec.factura_mensaje_html = f'<div class="alert alert-success" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-check-circle"></i> {mensaje}</div>'
                else:
                    rec.factura_mensaje_html = '<div class="alert alert-success" role="alert" style="display: block; margin: 0; padding: 10px; border-radius: 4px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box;"><i class="fa fa-check-circle"></i> Procesamiento completado correctamente</div>'
            else:
                # Otros estados (pendiente, procesando) - no mostrar mensaje
                rec.factura_mensaje_html = False
    
    
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
        Procesa la factura PDF adjunta, extrae datos con OCR/IA y rellena la expedición.
        """
        for rec in self:
            if not rec.factura_pdf:
                rec.factura_estado_procesamiento = "error"
                rec.factura_mensaje_error = _("No hay factura PDF adjunta para procesar")
                raise UserError(_("No hay factura PDF adjunta para procesar"))
            
            # Desactivar notificaciones de email durante todo el proceso
            ctx_no_mail = dict(self.env.context)
            ctx_no_mail.update({
                'mail_notrack': True,
                'mail_create_nolog': True,
                'mail_create_nosubscribe': True,
                'tracking_disable': True,
                'mail_notify_force_send': False,
            })
            
            # Marcar como procesando (sin tracking)
            rec.with_context(**ctx_no_mail).factura_estado_procesamiento = "procesando"
            rec.with_context(**ctx_no_mail).factura_mensaje_error = False
            
            # Obtener servicio OCR
            ocr_service = self.env["aduanas.invoice.ocr.service"]
            
            # Extraer datos de la factura
            try:
                # Asegurar que factura_pdf esté en el formato correcto
                pdf_data = rec.factura_pdf
                if not pdf_data:
                    rec.factura_estado_procesamiento = "error"
                    rec.factura_mensaje_error = _("No hay datos de PDF para procesar")
                    raise UserError(_("No hay datos de PDF para procesar"))
                
                # En Odoo, los campos Binary vienen como string base64
                # Si viene como bytes, convertirlo a base64
                if isinstance(pdf_data, bytes):
                    import base64
                    pdf_data = base64.b64encode(pdf_data).decode('utf-8')
                
                invoice_data = ocr_service.extract_invoice_data(pdf_data)
                
                # Validar que se extrajo texto
                if invoice_data.get("error"):
                    rec.factura_estado_procesamiento = "error"
                    rec.factura_mensaje_error = invoice_data.get("error", _("Error desconocido al procesar el PDF"))
                    rec.with_context(mail_notrack=True).message_post(
                        body=_("Error al procesar factura: %s") % invoice_data.get("error"),
                        subtype_xmlid='mail.mt_note'
                    )
                    raise UserError(_("Error al procesar el PDF: %s") % invoice_data.get("error"))
                
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
                
                if not invoice_data.get("lineas"):
                    advertencias.append(_("No se pudieron extraer líneas de productos. Deberás agregarlas manualmente."))
                else:
                    datos_extraidos.append(_("Líneas extraídas: %d") % len(invoice_data.get("lineas", [])))
                
                # Rellenar expediente con datos extraídos (sin notificaciones)
                rec = rec.with_context(**ctx_no_mail)
                ocr_service.fill_expediente_from_invoice(rec, invoice_data)
                
                # Determinar estado final (sin tracking)
                if advertencias:
                    rec.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'advertencia',
                        'factura_mensaje_error': "\n".join([_("ADVERTENCIAS:")] + advertencias)
                    })
                else:
                    rec.with_context(**ctx_no_mail).write({
                        'factura_estado_procesamiento': 'completado',
                        'factura_mensaje_error': False
                    })
                
                # Crear mensaje detallado para el chatter con todos los datos extraídos
                mensaje_chatter = _("<b>✅ Factura procesada correctamente</b><br/><br/>")
                
                # Resumen de datos extraídos
                mensaje_chatter += _("<b>📋 Resumen de datos extraídos:</b><br/>")
                mensaje_chatter += "<ul>"
                for dato in datos_extraidos:
                    mensaje_chatter += f"<li>{dato}</li>"
                mensaje_chatter += "</ul><br/>"
                
                # Detalles de remitente y consignatario
                if invoice_data.get("remitente_nombre") or invoice_data.get("remitente_nif"):
                    mensaje_chatter += _("<b>📤 Remitente:</b><br/>")
                    if invoice_data.get("remitente_nombre"):
                        mensaje_chatter += f"• Nombre: {invoice_data.get('remitente_nombre')}<br/>"
                    if invoice_data.get("remitente_nif"):
                        mensaje_chatter += f"• NIF: {invoice_data.get('remitente_nif')}<br/>"
                    if invoice_data.get("remitente_direccion"):
                        mensaje_chatter += f"• Dirección: {invoice_data.get('remitente_direccion')}<br/>"
                    mensaje_chatter += "<br/>"
                
                if invoice_data.get("consignatario_nombre") or invoice_data.get("consignatario_nif"):
                    mensaje_chatter += _("<b>📥 Consignatario:</b><br/>")
                    if invoice_data.get("consignatario_nombre"):
                        mensaje_chatter += f"• Nombre: {invoice_data.get('consignatario_nombre')}<br/>"
                    if invoice_data.get("consignatario_nif"):
                        mensaje_chatter += f"• NIF: {invoice_data.get('consignatario_nif')}<br/>"
                    if invoice_data.get("consignatario_direccion"):
                        mensaje_chatter += f"• Dirección: {invoice_data.get('consignatario_direccion')}<br/>"
                    mensaje_chatter += "<br/>"
                
                # Información de factura
                mensaje_chatter += _("<b>🧾 Información de factura:</b><br/>")
                if invoice_data.get("numero_factura"):
                    mensaje_chatter += f"• Nº Factura: {invoice_data.get('numero_factura')}<br/>"
                if invoice_data.get("fecha_factura"):
                    mensaje_chatter += f"• Fecha: {invoice_data.get('fecha_factura')}<br/>"
                if invoice_data.get("valor_total"):
                    mensaje_chatter += f"• Valor Total: {invoice_data.get('valor_total')} {invoice_data.get('moneda', 'EUR')}<br/>"
                if invoice_data.get("incoterm"):
                    mensaje_chatter += f"• Incoterm: {invoice_data.get('incoterm')}<br/>"
                mensaje_chatter += "<br/>"
                
                # Información de transporte
                if invoice_data.get("transportista") or invoice_data.get("matricula"):
                    mensaje_chatter += _("<b>🚚 Información de transporte:</b><br/>")
                    if invoice_data.get("transportista"):
                        mensaje_chatter += f"• Transportista: {invoice_data.get('transportista')}<br/>"
                    if invoice_data.get("matricula"):
                        mensaje_chatter += f"• Matrícula: {invoice_data.get('matricula')}<br/>"
                    if invoice_data.get("referencia_transporte"):
                        mensaje_chatter += f"• Referencia: {invoice_data.get('referencia_transporte')}<br/>"
                    if invoice_data.get("remolque"):
                        mensaje_chatter += f"• Remolque: {invoice_data.get('remolque')}<br/>"
                    if invoice_data.get("codigo_transporte"):
                        mensaje_chatter += f"• Código: {invoice_data.get('codigo_transporte')}<br/>"
                    mensaje_chatter += "<br/>"
                
                # Líneas de productos
                if invoice_data.get("lineas"):
                    mensaje_chatter += _("<b>📦 Líneas de productos extraídas ({0}):</b><br/>").format(len(invoice_data.get("lineas", [])))
                    mensaje_chatter += "<ul>"
                    for idx, linea in enumerate(invoice_data.get("lineas", [])[:10], 1):  # Mostrar máximo 10 líneas
                        mensaje_chatter += f"<li><b>Línea {idx}:</b> "
                        if linea.get("articulo"):
                            mensaje_chatter += f"Art. {linea.get('articulo')} - "
                        if linea.get("descripcion"):
                            mensaje_chatter += f"{linea.get('descripcion')[:50]}"
                            if len(linea.get("descripcion", "")) > 50:
                                mensaje_chatter += "..."
                        if linea.get("cantidad"):
                            mensaje_chatter += f" | Cantidad: {linea.get('cantidad')}"
                        if linea.get("partida"):
                            mensaje_chatter += f" | H.S.: {linea.get('partida')}"
                        if linea.get("total"):
                            mensaje_chatter += f" | Total: {linea.get('total')} {invoice_data.get('moneda', 'EUR')}"
                        mensaje_chatter += "</li>"
                    mensaje_chatter += "</ul>"
                    if len(invoice_data.get("lineas", [])) > 10:
                        mensaje_chatter += _("<i>(Mostrando las primeras 10 líneas de {0} totales)</i><br/>").format(len(invoice_data.get("lineas", [])))
                    mensaje_chatter += "<br/>"
                
                # Advertencias si las hay
                if advertencias:
                    mensaje_chatter += _("<b>⚠️ Advertencias:</b><br/>")
                    mensaje_chatter += "<ul>"
                    for adv in advertencias:
                        mensaje_chatter += f"<li>{adv}</li>"
                    mensaje_chatter += "</ul><br/>"
                
                # Método usado
                if invoice_data.get("metodo_usado"):
                    mensaje_chatter += _("<i>Método de extracción: {0}</i>").format(invoice_data.get("metodo_usado"))
                
                rec.with_context(mail_notrack=True).message_post(
                    body=mensaje_chatter,
                    subtype_xmlid='mail.mt_note'
                )
                
                # Marcar factura como procesada
                rec.factura_procesada = True
                
                # Forzar recarga del registro para actualizar la vista
                rec.invalidate_recordset()
                
                # Preparar mensaje de notificación
                notif_title = _("Factura Procesada con Advertencias") if advertencias else _("Factura Procesada")
                notif_message = _("La factura se ha procesado, pero hay algunas advertencias. Revisa los datos extraídos.") if advertencias else _("La factura se ha procesado correctamente y los datos se han extraído.")
                
                # Recargar el formulario y mostrar notificación
                # Usar una acción combinada: mostrar notificación y recargar formulario
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
                        "active_id": rec.id,
                        "active_model": "aduana.expediente",
                    },
                    "res_model": "aduana.expediente",
                    "res_id": rec.id,
                    "view_mode": "form",
                    "target": "current",
                }
            except UserError as ue:
                # Guardar estado de error y mensaje
                error_msg = str(ue)
                rec.factura_estado_procesamiento = "error"
                rec.factura_mensaje_error = error_msg
                rec.with_context(mail_notrack=True).message_post(
                    body=_("Error al procesar factura: %s") % error_msg,
                    subtype_xmlid='mail.mt_note'
                )
                _logger.error("Error al procesar factura PDF (UserError): %s", error_msg)
                rec.invalidate_recordset()
                # Devolver acción que recarga el formulario
                return {
                    "type": "ir.actions.act_window",
                    "res_model": "aduana.expediente",
                    "res_id": rec.id,
                    "view_mode": "form",
                    "target": "current",
                }
            except Exception as e:
                error_msg = str(e)
                rec.factura_estado_procesamiento = "error"
                # Mensaje de error más detallado
                mensaje_error_detallado = _("Error al procesar la factura: %s\n\nPosibles causas:\n- El PDF está corrupto o protegido\n- El PDF es una imagen escaneada de muy baja calidad\n- No se pudo conectar con el servicio de OCR\n- El formato del PDF no es compatible\n- Error en la API de OpenAI\n- Falta configuración de API Key") % error_msg
                rec.factura_mensaje_error = mensaje_error_detallado
                rec.with_context(mail_notrack=True).message_post(
                    body=_("Error al procesar factura: %s\n\nDetalles técnicos:\n%s") % (error_msg, mensaje_error_detallado),
                    subtype_xmlid='mail.mt_note'
                )
                _logger.exception("Error al procesar factura PDF: %s", e)
                rec.invalidate_recordset()
                # Devolver acción que recarga el formulario
                return {
                    "type": "ir.actions.act_window",
                    "res_model": "aduana.expediente",
                    "res_id": rec.id,
                    "view_mode": "form",
                    "target": "current",
                }

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
