from odoo import api, fields, models, _

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Export
    aeat_endpoint_cc515c = fields.Char(string="Endpoint CC515C (Export)", config_parameter="aduanas_transport.endpoint.cc515c",
        default="https://prewww1.agenciatributaria.gob.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP")
    aeat_endpoint_cc511c = fields.Char(string="Endpoint CC511C (Export)", config_parameter="aduanas_transport.endpoint.cc511c",
        default="https://prewww1.agenciatributaria.gob.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP")
    # Import
    aeat_endpoint_imp_decl = fields.Char(string="Endpoint Declaración Importación", config_parameter="aduanas_transport.endpoint.imp_decl",
        default="https://prewww1.agenciatributaria.gob.es/wlpl/ADIM-JDIT/ws/imp/DeclaracionSOAP")
    # Bandeja
    aeat_endpoint_bandeja = fields.Char(string="Endpoint Bandeja", config_parameter="aduanas_transport.endpoint.bandeja",
        default="https://prewww1.agenciatributaria.gob.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP")

    # Certificado (pendiente firma XAdES)
    cert_password = fields.Char(string="Password Certificado", config_parameter="aduanas_transport.cert_password")
    cert_attachment_id = fields.Many2one("ir.attachment", string="Certificado P12/PFX (adjunto)")

    # MSoft
    msoft_dsn = fields.Char(string="MSoft DSN/Host", config_parameter="aduanas_transport.msoft.dsn")
    msoft_db = fields.Char(string="MSoft DB", config_parameter="aduanas_transport.msoft.db")
    msoft_user = fields.Char(string="MSoft User", config_parameter="aduanas_transport.msoft.user")
    msoft_pass = fields.Char(string="MSoft Pass", config_parameter="aduanas_transport.msoft.pass")
    
    # OpenAI API para OCR de facturas con GPT-4o Vision
    openai_api_key = fields.Char(
        string="OpenAI API Key", 
        config_parameter="aduanas_transport.openai_api_key",
        help="API Key de OpenAI para usar GPT-4o Vision. Obtener en: https://platform.openai.com/api-keys. "
             "Dejar vacío para usar OCR alternativo (pdfplumber/PyPDF2).")

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env["ir.config_parameter"].sudo()
        attach_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
        if attach_id:
            # Convertir ID a recordset para Many2one
            attachment = self.env["ir.attachment"].browse(attach_id)
            if attachment.exists():
                res.update(cert_attachment_id=attachment)
            else:
                res.update(cert_attachment_id=False)
        else:
            res.update(cert_attachment_id=False)
        return res

    def set_values(self):
        super().set_values()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("aduanas_transport.cert_attachment_id", self.cert_attachment_id.id or 0)