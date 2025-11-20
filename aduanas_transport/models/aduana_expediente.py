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
    incoterm = fields.Char()
    oficina = fields.Char(string="Oficina Aduanas", help="Ej. 0801 Barcelona")
    transportista = fields.Char()
    matricula = fields.Char()
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
    numero_factura = fields.Char(string="Nº Factura Comercial")
    referencia_transporte = fields.Char(string="Referencia Transporte")
    conductor_nombre = fields.Char(string="Nombre Conductor")
    conductor_dni = fields.Char(string="DNI Conductor")
    observaciones = fields.Text(string="Observaciones")
    error_message = fields.Text(string="Último Error", readonly=True)
    last_response_date = fields.Datetime(string="Última Respuesta", readonly=True)

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
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al enviar CC515C:\n%s") % error_msg, subtype='mail.mt_note')
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
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al presentar CC511C:\n%s") % error_msg, subtype='mail.mt_note')
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
            else:
                rec.state = "error"
                error_msg = "\n".join(parsed.get("errors", [])) or parsed.get("error", _("Error desconocido"))
                rec.error_message = error_msg
                rec.message_post(body=_("Error al enviar declaración:\n%s") % error_msg, subtype='mail.mt_note')
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
            
            if parsed.get("errors"):
                rec.message_post(body=_("Errores en bandeja:\n%s") % "\n".join(parsed["errors"]), subtype='mail.mt_note')
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
