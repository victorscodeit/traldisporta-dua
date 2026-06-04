import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    aeat_endpoint_cc515c = fields.Char(
        string="Endpoint presentar DUA (CC515C)",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP",
        help="Exportación AES: presentación CC515C.",
    )
    aeat_endpoint_cc511c = fields.Char(
        string="Endpoint CC511C (Export)",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP",
    )
    aeat_endpoint_ccaesc = fields.Char(
        string="Endpoint consulta exportación (CCAESC)",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP",
    )
    aeat_endpoint_cc507c = fields.Char(
        string="Endpoint llegada aduana salida (CC507C)",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP",
    )
    aeat_endpoint_imp_decl = fields.Char(
        string="Endpoint Declaración Importación H1 (CC415A)",
        default="https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP",
        help="Importación H1/CAU. No usar endpoints AES/CC515C.",
    )
    aeat_endpoint_imp_query = fields.Char(
        string="Endpoint consulta importación (V3)",
        default="https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP",
    )
    aeat_endpoint_bandeja = fields.Char(
        string="Endpoint Bandeja",
        default="https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP",
    )
    aeat_endpoint_ie615 = fields.Char(
        string="Endpoint EXS (IE615 V5)",
        default="https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP",
    )

    aeat_cert_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Certificado AEAT actual",
        readonly=True,
    )
    aeat_cert_upload = fields.Binary(string="Subir certificado P12/PFX")
    aeat_cert_upload_filename = fields.Char(string="Nombre certificado")
    aeat_cert_password = fields.Char(string="Contraseña certificado AEAT")
    aeat_nif_firmante = fields.Char(
        string="NIF firmante AEAT",
        help="Opcional. Si está vacío se usa el NIF de la empresa o del remitente según el flujo.",
    )

    def _create_aeat_certificate_attachment(self):
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
            company.sudo().write({
                "aeat_cert_attachment_id": attachment.id,
                "aeat_cert_upload": False,
                "aeat_cert_upload_filename": False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._create_aeat_certificate_attachment()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if vals.get("aeat_cert_upload"):
            self._create_aeat_certificate_attachment()
        return res

    @api.model
    def _aduanas_aeat_columns_ready(self):
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'res_company' AND column_name = 'aeat_endpoint_cc515c'
            LIMIT 1
            """
        )
        return bool(self.env.cr.fetchone())

    @api.model
    def init(self):
        """Tras crear columnas en -u, migra configuración legacy desde ir.config_parameter."""
        if not self._aduanas_aeat_columns_ready():
            return
        try:
            from ..hooks import migrate_aeat_config_to_companies

            migrate_aeat_config_to_companies(self.env)
        except Exception:
            _logger.exception("No se pudo migrar configuración AEAT a res.company")
