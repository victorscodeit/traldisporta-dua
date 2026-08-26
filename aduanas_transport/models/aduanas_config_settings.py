from odoo import api, fields, models, _


class AduanasConfigSettings(models.TransientModel):
    _name = "aduanas.config.settings"
    _description = "Configuración Aduanas AEAT"

    aeat_endpoint_cc515c = fields.Char(string="Endpoint presentar DUA (CC515C)")
    aeat_endpoint_cc511c = fields.Char(string="Endpoint CC511C (Export)")
    aeat_endpoint_ccaesc = fields.Char(string="Endpoint consulta exportación (CCAESC)")
    aeat_endpoint_cc507c = fields.Char(string="Endpoint llegada aduana salida (CC507C)")
    aeat_endpoint_imp_decl = fields.Char(string="Endpoint Declaración Importación H1 (CC415A)")
    aeat_endpoint_imp_query = fields.Char(string="Endpoint consulta importación (V3)")
    aeat_endpoint_bandeja = fields.Char(string="Endpoint Bandeja")
    aeat_endpoint_ie615 = fields.Char(string="Endpoint EXS (IE615 V5)")
    aeat_endpoint_g4_dec = fields.Char(string="Endpoint G4 depósito temporal (G4Dec)")

    cert_attachment_id = fields.Many2one("ir.attachment", string="Certificado actual", readonly=True)
    cert_upload = fields.Binary(string="Subir certificado P12/PFX")
    cert_upload_filename = fields.Char(string="Nombre del archivo")
    cert_password = fields.Char(string="Contraseña del certificado")
    aeat_nif_firmante = fields.Char(string="NIF del firmante (opcional)")

    msoft_dsn = fields.Char(string="MSoft DSN/Host")
    msoft_db = fields.Char(string="MSoft DB")
    msoft_user = fields.Char(string="MSoft User")
    msoft_pass = fields.Char(string="MSoft Pass")
    openai_api_key = fields.Char(string="OpenAI API Key")

    default_tipo_representacion = fields.Selection(
        [("indirecta", "Indirecta (agente)"), ("directa", "Directa")],
        string="Representación por defecto",
        default="indirecta",
    )
    default_transportista = fields.Char(
        string="Transportista por defecto",
        help="Vacío = nombre de la empresa Odoo en cada expediente nuevo.",
    )
    default_oficina_export = fields.Char(string="Oficina exportación por defecto", default="ES000101")
    default_oficina_import = fields.Char(string="Oficina importación por defecto", default="ES000101")
    default_pais_transporte = fields.Char(string="País transporte por defecto", default="ES")

    auto_close_export_on_exited = fields.Boolean(
        string="Cerrar export al confirmar salida efectiva",
        default=True,
        store=False,
        help="Tras salida efectiva AEAT (bandeja/CCAESC), pasa el expediente de exportación a «Cerrado».",
    )
    auto_close_import_on_accepted = fields.Boolean(
        string="Cerrar import al admitir MRN",
        default=False,
        store=False,
        help="Tras presentación CC415A aceptada, cierra el expediente de importación automáticamente.",
    )

    _PARAMS = {
        "aeat_endpoint_cc515c": ("aduanas_transport.endpoint.cc515c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP"),
        "aeat_endpoint_cc511c": ("aduanas_transport.endpoint.cc511c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP"),
        "aeat_endpoint_ccaesc": ("aduanas_transport.endpoint.ccaesc", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP"),
        "aeat_endpoint_cc507c": ("aduanas_transport.endpoint.cc507c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP"),
        "aeat_endpoint_imp_decl": ("aduanas_transport.endpoint.imp_decl", "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP"),
        "aeat_endpoint_imp_query": ("aduanas_transport.endpoint.imp_query", "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP"),
        "aeat_endpoint_bandeja": ("aduanas_transport.endpoint.bandeja", "https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP"),
        "aeat_endpoint_ie615": ("aduanas_transport.endpoint.ie615", "https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP"),
        "aeat_endpoint_g4_dec": ("aduanas_transport.endpoint.g4_dec", "https://prewww1.aeat.es/wlpl/ADDS-JDIT/ws/G4DecV1SOAP"),
        "cert_password": ("aduanas_transport.cert_password", ""),
        "aeat_nif_firmante": ("aduanas_transport.aeat_nif_firmante", ""),
        "msoft_dsn": ("aduanas_transport.msoft.dsn", ""),
        "msoft_db": ("aduanas_transport.msoft.db", ""),
        "msoft_user": ("aduanas_transport.msoft.user", ""),
        "msoft_pass": ("aduanas_transport.msoft.pass", ""),
        "openai_api_key": ("aduanas_transport.openai_api_key", ""),
        "default_tipo_representacion": ("aduanas_transport.default_tipo_representacion", "indirecta"),
        "default_transportista": ("aduanas_transport.default_transportista", ""),
        "default_oficina_export": ("aduanas_transport.default_oficina_export", "ES000101"),
        "default_oficina_import": ("aduanas_transport.default_oficina_import", "ES000101"),
        "default_pais_transporte": ("aduanas_transport.default_pais_transporte", "ES"),
    }

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        icp = self.env["ir.config_parameter"].sudo()
        for field_name, (param, default) in self._PARAMS.items():
            if field_name in fields_list:
                value = icp.get_param(param) or default
                if field_name == "aeat_endpoint_imp_decl" and "ADIM-JDIT/ws/imp/DeclaracionSOAP" in value:
                    value = self._PARAMS[field_name][1]
                values[field_name] = value
        if "cert_attachment_id" in fields_list:
            values["cert_attachment_id"] = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0) or False
        if "auto_close_export_on_exited" in fields_list:
            values["auto_close_export_on_exited"] = icp.get_param(
                "aduanas_transport.auto_close_export_on_exited", "1"
            ) == "1"
        if "auto_close_import_on_accepted" in fields_list:
            values["auto_close_import_on_accepted"] = icp.get_param(
                "aduanas_transport.auto_close_import_on_accepted", "0"
            ) == "1"
        return values

    def action_apply(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        for field_name, (param, default) in self._PARAMS.items():
            value = self[field_name] or default
            if field_name == "aeat_endpoint_imp_decl" and "ADIM-JDIT/ws/imp/DeclaracionSOAP" in value:
                value = default
            icp.set_param(param, value)
        form_vals = {}
        if self.cert_upload:
            name = self.cert_upload_filename or "cert_aeat.p12"
            if not name.lower().endswith((".p12", ".pfx")):
                name = name + ".p12" if "." not in name else name
            # No vincular al transient: Odoo limpia adjuntos de registros temporales
            # y el certificado desaparecería; guardar como adjunto permanente.
            Attachment = self.env["ir.attachment"].sudo()
            old_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
            attachment = Attachment.create({
                "name": name,
                "datas": self.cert_upload,
                "type": "binary",
                "mimetype": "application/x-pkcs12",
                "res_model": False,
                "res_id": 0,
                "public": False,
            })
            icp.set_param("aduanas_transport.cert_attachment_id", str(attachment.id))
            if old_id and old_id != attachment.id:
                old_att = Attachment.browse(old_id).exists()
                if old_att and old_att.res_model in (False, "", "aduanas.config.settings"):
                    # Solo borrar adjuntos de certificado huérfanos / del wizard
                    try:
                        old_att.unlink()
                    except Exception:
                        pass
            form_vals.update({
                "cert_attachment_id": attachment.id,
                "cert_upload": False,
                "cert_upload_filename": False,
            })
        elif self.cert_attachment_id:
            icp.set_param("aduanas_transport.cert_attachment_id", str(self.cert_attachment_id.id))
        icp.set_param(
            "aduanas_transport.auto_close_export_on_exited",
            "1" if self.auto_close_export_on_exited else "0",
        )
        icp.set_param(
            "aduanas_transport.auto_close_import_on_accepted",
            "1" if self.auto_close_import_on_accepted else "0",
        )
        if form_vals:
            self.write(form_vals)
        # Reabrir el formulario para que «Certificado actual» muestre el adjunto nuevo
        action = self.env.ref("aduanas_transport.action_aduanas_config").sudo().read()[0]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Configuración guardada"),
                "message": _("Configuración Aduanas AEAT actualizada."),
                "type": "success",
                "sticky": False,
                "next": action,
            },
        }
