from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    _AEAT_DEFAULTS = {
        "aeat_endpoint_cc515c": "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP",
        "aeat_endpoint_cc511c": "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP",
        "aeat_endpoint_ccaesc": "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP",
        "aeat_endpoint_cc507c": "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP",
        "aeat_endpoint_imp_decl": "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP",
        "aeat_endpoint_imp_query": "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP",
        "aeat_endpoint_bandeja": "https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP",
        "aeat_endpoint_ie615": "https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP",
        "aeat_cert_password": "",
        "aeat_nif_firmante": "",
    }
    _AEAT_LEGACY_PARAMS = {
        "aeat_endpoint_cc515c": "aduanas_transport.endpoint.cc515c",
        "aeat_endpoint_cc511c": "aduanas_transport.endpoint.cc511c",
        "aeat_endpoint_ccaesc": "aduanas_transport.endpoint.ccaesc",
        "aeat_endpoint_cc507c": "aduanas_transport.endpoint.cc507c",
        "aeat_endpoint_imp_decl": "aduanas_transport.endpoint.imp_decl",
        "aeat_endpoint_imp_query": "aduanas_transport.endpoint.imp_query",
        "aeat_endpoint_bandeja": "aduanas_transport.endpoint.bandeja",
        "aeat_endpoint_ie615": "aduanas_transport.endpoint.ie615",
        "aeat_cert_attachment_id": "aduanas_transport.cert_attachment_id",
        "aeat_cert_password": "aduanas_transport.cert_password",
        "aeat_nif_firmante": "aduanas_transport.aeat_nif_firmante",
    }

    aeat_endpoint_cc515c = fields.Char(
        string="Endpoint presentar DUA (CC515C)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
        help="Exportación AES: presentación CC515C.",
    )
    aeat_endpoint_cc511c = fields.Char(
        string="Endpoint CC511C (Export)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_endpoint_ccaesc = fields.Char(
        string="Endpoint consulta exportación (CCAESC)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_endpoint_cc507c = fields.Char(
        string="Endpoint llegada aduana salida (CC507C)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_endpoint_imp_decl = fields.Char(
        string="Endpoint Declaración Importación H1 (CC415A)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
        help="Importación H1/CAU. No usar endpoints AES/CC515C.",
    )
    aeat_endpoint_imp_query = fields.Char(
        string="Endpoint consulta importación (V3)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_endpoint_bandeja = fields.Char(
        string="Endpoint Bandeja",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_endpoint_ie615 = fields.Char(
        string="Endpoint EXS (IE615 V5)",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )

    aeat_cert_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Certificado AEAT actual",
        compute="_compute_aeat_config",
        readonly=True,
    )
    aeat_cert_upload = fields.Binary(
        string="Subir certificado P12/PFX",
        compute="_compute_aeat_upload",
        inverse="_inverse_aeat_upload",
        readonly=False,
    )
    aeat_cert_upload_filename = fields.Char(
        string="Nombre certificado",
        compute="_compute_aeat_upload",
        inverse="_inverse_aeat_upload",
        readonly=False,
    )
    aeat_cert_password = fields.Char(
        string="Contraseña certificado AEAT",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
    )
    aeat_nif_firmante = fields.Char(
        string="NIF firmante AEAT",
        compute="_compute_aeat_config",
        inverse="_inverse_aeat_config",
        readonly=False,
        help="Opcional. Si está vacío se usa el NIF de la empresa o del remitente según el flujo.",
    )

    def _aeat_param_key(self, field_name):
        self.ensure_one()
        return "aduanas_transport.company.%s.%s" % (self.id, field_name)

    def _get_aeat_param(self, field_name):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        value = icp.get_param(self._aeat_param_key(field_name))
        if value in (None, False, ""):
            value = icp.get_param(self._AEAT_LEGACY_PARAMS.get(field_name, ""))
        if value in (None, False, ""):
            value = self._AEAT_DEFAULTS.get(field_name, "")
        if field_name == "aeat_endpoint_imp_decl" and "ADIM-JDIT/ws/imp/DeclaracionSOAP" in (value or ""):
            value = self._AEAT_DEFAULTS["aeat_endpoint_imp_decl"]
        return value

    def _set_aeat_param(self, field_name, value):
        self.ensure_one()
        value = value or ""
        if field_name == "aeat_endpoint_imp_decl" and "ADIM-JDIT/ws/imp/DeclaracionSOAP" in value:
            value = self._AEAT_DEFAULTS["aeat_endpoint_imp_decl"]
        self.env["ir.config_parameter"].sudo().set_param(self._aeat_param_key(field_name), value)

    def _compute_aeat_config(self):
        for company in self:
            for field_name in company._AEAT_DEFAULTS:
                company[field_name] = company._get_aeat_param(field_name)
            attach_id = int(company._get_aeat_param("aeat_cert_attachment_id") or 0)
            company.aeat_cert_attachment_id = self.env["ir.attachment"].sudo().browse(attach_id)

    def _inverse_aeat_config(self):
        for company in self:
            for field_name in company._AEAT_DEFAULTS:
                company._set_aeat_param(field_name, company[field_name])

    def _compute_aeat_upload(self):
        for company in self:
            company.aeat_cert_upload = False
            company.aeat_cert_upload_filename = False

    def _inverse_aeat_upload(self):
        for company in self:
            if not company.aeat_cert_upload:
                continue
            name = company.aeat_cert_upload_filename or "cert_aeat.p12"
            if not name.lower().endswith((".p12", ".pfx")):
                name = name + ".p12" if "." not in name else name
            attachment = self.env["ir.attachment"].sudo().create({
                "name": name,
                "datas": company.aeat_cert_upload,
                "res_model": "res.company",
                "res_id": company.id,
                "mimetype": "application/x-pkcs12",
            })
            company._set_aeat_param("aeat_cert_attachment_id", attachment.id)
