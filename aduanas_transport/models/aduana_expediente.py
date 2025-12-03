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
    factura_procesada = fields.Boolean(string="Factura Procesada", default=False, help="Indica si la factura ha sido procesada con IA")
    factura_estado_procesamiento = fields.Selection([
        ("pendiente", "Pendiente de Procesar"),
        ("procesando", "Procesando..."),
        ("completado", "Completado"),
        ("error", "Error en Procesamiento"),
        ("advertencia", "Completado con Advertencias"),
    ], string="Estado Procesamiento", default="pendiente", readonly=True, help="Estado del procesamiento de la factura")
    factura_mensaje_error = fields.Text(string="Mensaje de Error/Advertencia", readonly=True, help="Mensajes de error o advertencias durante el procesamiento")
    factura_datos_extraidos = fields.Text(string="Datos Extraídos de Factura", readonly=True, help="Datos extraídos de la factura por IA/OCR")
    
    
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

    # ===== Exportación (AES) =====
    def action_generate_cc515c(self):
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("CC515C solo aplica a exportación"))
            # Validar datos antes de generar
            validator = self.env["aduanas.validator"]
            validator.validate_expediente_export(rec)
            xml = self.env['ir.ui.view']._render_template(
                "aduanas_transport.tpl_cc515c",
                {"exp": rec}
            )
            rec._attach_xml(f"{rec.name}_CC515C.xml", xml)
            rec.state = "predeclared"
            rec.error_message = False
        return True



    def action_send_cc515c(self):
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        for rec in self:
            if rec.direction != "export":
                raise UserError(_("CC515C solo aplica a exportación"))
            settings = rec._get_settings()
            xmls = self.env["ir.attachment"].search([("res_model","=",rec._name),("res_id","=",rec.id),("name","like","%CC515C.xml")], limit=1)
            if not xmls:
                rec.action_generate_cc515c()
                xmls = self.env["ir.attachment"].search([("res_model","=",rec._name),("res_id","=",rec.id),("name","like","%CC515C.xml")], limit=1)
            xml_content = base64.b64decode(xmls.datas or b"").decode("utf-8")
            resp_xml = client.send_xml(settings.get("aeat_endpoint_cc515c"), xml_content, service="CC515C")
            rec._attach_xml(f"{rec.name}_CC515C_response.xml", resp_xml or "")
            
            # Parsear respuesta mejorada
            parsed = parser.parse_aeat_response(resp_xml, "CC515C")
            rec.last_response_date = fields.Datetime.now()
            
            if parsed.get("success") and parsed.get("mrn"):
                rec.mrn = parsed["mrn"]
                rec.state = "accepted"
                rec.error_message = False
                if parsed.get("messages"):
                    rec.message_post(body=_("Expediente aceptado. MRN: %s\nMensajes: %s") % (
                        rec.mrn, "\n".join(parsed["messages"])
                    ))
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cc515c")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al enviar CC515C:\n%s") % error_msg, subtype_xmlid='mail.mt_note')
                # Procesar incidencias de error
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cc515c")
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
                rec.message_post(body=_("CC511C presentado correctamente"))
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "cc511c")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al presentar CC511C:\n%s") % error_msg, subtype_xmlid='mail.mt_note')
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
                    rec.message_post(body=_("Declaración aceptada. MRN: %s\nMensajes: %s") % (
                        rec.mrn, "\n".join(parsed["messages"])
                    ))
                # Procesar incidencias si las hay
                if parsed.get("incidencias"):
                    rec._procesar_incidencias(parsed["incidencias"], "imp_decl")
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al enviar declaración:\n%s") % error_msg, subtype_xmlid='mail.mt_note')
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
                rec.message_post(body=_("Levante confirmado desde bandeja AEAT"))
            
            # Procesar incidencias detectadas
            if parsed.get("incidencias"):
                rec._procesar_incidencias(parsed["incidencias"], "bandeja")
            
            if parsed.get("errors"):
                rec.message_post(body=_("Errores en bandeja:\n%s") % "\n".join(parsed["errors"]), subtype_xmlid='mail.mt_note')
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
            self.message_post(
                body=_("Nueva incidencia detectada: %s\nTipo: %s\nCódigo: %s") % (
                    incidencia.titulo,
                    dict(incidencia._fields["tipo_incidencia"].selection).get(incidencia.tipo_incidencia),
                    incidencia.codigo_incidencia or _("N/A")
                ),
                subtype_xmlid='mail.mt_note',
                partner_ids=[(4, p.id) for p in self.message_partner_ids]
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
        self.ensure_one()
        # Renderizar correctamente con QWeb (no plantilla literal)
        xml = self.env['ir.ui.view']._render_template(
            "aduanas_transport.tpl_cc515c",
            {"exp": self}
        )
        # Crear o actualizar adjunto
        att = self._get_xml_attachment("CC515C.xml")
        if att:
            att.datas = base64.b64encode(xml.encode("utf-8"))
            return att
        self._attach_xml(f"{self.name}_CC515C.xml", xml)
        return self._get_xml_attachment("CC515C.xml")

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
        self.ensure_one()
        att = self._ensure_cc515c_xml()
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
            
            # Marcar como procesando
            rec.factura_estado_procesamiento = "procesando"
            rec.factura_mensaje_error = False
            
            # Obtener servicio OCR
            ocr_service = self.env["aduanas.invoice.ocr.service"]
            
            # Extraer datos de la factura
            try:
                invoice_data = ocr_service.extract_invoice_data(rec.factura_pdf)
                
                # Validar que se extrajo texto
                if invoice_data.get("error"):
                    rec.factura_estado_procesamiento = "error"
                    rec.factura_mensaje_error = invoice_data.get("error", _("Error desconocido al procesar el PDF"))
                    rec.message_post(
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
                
                # Rellenar expediente con datos extraídos
                ocr_service.fill_expediente_from_invoice(rec, invoice_data)
                
                # Determinar estado final
                if advertencias:
                    rec.factura_estado_procesamiento = "advertencia"
                    rec.factura_mensaje_error = "\n".join([_("ADVERTENCIAS:")] + advertencias)
                else:
                    rec.factura_estado_procesamiento = "completado"
                    rec.factura_mensaje_error = False
                
                # Mensaje de éxito con detalles
                mensaje_body = _("Factura procesada correctamente.\n\nDatos extraídos:\n%s") % "\n".join(datos_extraidos)
                if advertencias:
                    mensaje_body += "\n\n" + _("Advertencias:\n%s") % "\n".join(advertencias)
                
                rec.message_post(
                    body=mensaje_body,
                    subtype_xmlid='mail.mt_note'
                )
                
                # Notificación según estado
                notif_type = "warning" if advertencias else "success"
                notif_title = _("Factura Procesada con Advertencias") if advertencias else _("Factura Procesada")
                notif_message = _("La factura se ha procesado, pero hay algunas advertencias. Revisa los datos extraídos.") if advertencias else _("La factura se ha procesado correctamente y los datos se han extraído.")
                
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": notif_title,
                        "message": notif_message,
                        "type": notif_type,
                        "sticky": bool(advertencias),  # Hacer sticky si hay advertencias
                    }
                }
            except UserError:
                # Re-raise UserError sin modificar
                rec.factura_estado_procesamiento = "error"
                raise
            except Exception as e:
                error_msg = str(e)
                rec.factura_estado_procesamiento = "error"
                rec.factura_mensaje_error = _("Error al procesar la factura: %s\n\nPosibles causas:\n- El PDF está corrupto o protegido\n- El PDF es una imagen escaneada de muy baja calidad\n- No se pudo conectar con el servicio de OCR\n- El formato del PDF no es compatible") % error_msg
                rec.message_post(
                    body=_("Error al procesar factura: %s") % error_msg,
                    subtype_xmlid='mail.mt_note'
                )
                _logger.exception("Error al procesar factura PDF: %s", e)
                raise UserError(_("Error al procesar la factura:\n%s\n\nRevisa el campo 'Mensaje de Error' para más detalles.") % error_msg)

    def action_auto_generate_dua(self):
        """
        Procesa la factura PDF, rellena la expedición y genera el DUA automáticamente.
        Este es el flujo principal: Factura → Procesar → Generar DUA
        """
        for rec in self:
            # Validar que hay factura
            if not rec.factura_pdf:
                raise UserError(_("Debe subir una factura PDF primero. Este es el punto de partida del expediente."))
            
            # Procesar la factura si no está procesada
            if not rec.factura_procesada:
                rec.action_process_invoice_pdf()
            
            # Validar que tenemos los datos mínimos después del procesamiento
            if not rec.remitente:
                raise UserError(_("No se pudo extraer el remitente de la factura. Por favor, complételo manualmente."))
            
            if not rec.consignatario:
                raise UserError(_("No se pudo extraer el consignatario de la factura. Por favor, complételo manualmente."))
            
            # Validar que hay líneas si son necesarias
            if not rec.line_ids:
                rec.message_post(
                    body=_("Advertencia: No se extrajeron líneas de productos de la factura. Puede que necesites agregarlas manualmente."),
                    subtype_xmlid='mail.mt_note'
                )
            
            # Determinar qué tipo de DUA generar según la dirección
            if rec.direction == "export":
                # Generar y enviar CC515C (exportación)
                rec.action_generate_cc515c()
                rec.message_post(
                    body=_("DUA de exportación (CC515C) generado automáticamente desde la factura."),
                    subtype_xmlid='mail.mt_note'
                )
            elif rec.direction == "import":
                # Generar declaración de importación
                rec.action_generate_imp_decl()
                rec.message_post(
                    body=_("DUA de importación generado automáticamente desde la factura."),
                    subtype_xmlid='mail.mt_note'
                )
            else:
                raise UserError(_("Debe especificar el sentido (export/import) antes de generar el DUA."))
            
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("DUA Generado"),
                    "message": _("El DUA se ha generado automáticamente desde la factura."),
                    "type": "success",
                    "sticky": False,
                }
            }
