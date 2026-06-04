from odoo import api, fields, models, _

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Export (presentar DUA = CC515C). Preproducción: prewww1.aeat.es (agenciatributaria.gob.es no resuelve en preprod)
    aeat_endpoint_cc515c = fields.Char(
        string="Endpoint presentar DUA (CC515C)",
        config_parameter="aduanas_transport.endpoint.cc515c",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP",
        help="Preproducción por defecto. Cambiar a producción (www1.agenciatributaria.gob.es) cuando vaya a presentar DUAs reales.")
    aeat_endpoint_cc511c = fields.Char(string="Endpoint CC511C (Export)", config_parameter="aduanas_transport.endpoint.cc511c",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP")
    aeat_endpoint_ccaesc = fields.Char(
        string="Endpoint consulta exportación (CCAESC)",
        config_parameter="aduanas_transport.endpoint.ccaesc",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP",
        help="Consulta completa de una declaración AES por MRN.")
    aeat_endpoint_cc507c = fields.Char(
        string="Endpoint llegada aduana salida (CC507C)",
        config_parameter="aduanas_transport.endpoint.cc507c",
        default="https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP",
        help="Notificación de llegada de mercancías a la aduana de salida.")
    # Import
    aeat_endpoint_imp_decl = fields.Char(
        string="Endpoint Declaración Importación H1 (CC415A)",
        config_parameter="aduanas_transport.endpoint.imp_decl",
        default="https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP",
        help="Alta de declaración completa H1/CAU mediante CC415A. Preproducción por defecto; editable si AEAT cambia el WSDL/endpoint. No usar endpoints AES/CC515C.",
    )
    aeat_endpoint_imp_query = fields.Char(
        string="Endpoint consulta importación (V3)",
        config_parameter="aduanas_transport.endpoint.imp_query",
        default="https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP",
        help="Consulta completa de importación CAU/H1 por MRN. Preproducción: prewww1; producción: www1.agenciatributaria.gob.es.",
    )
    # Bandeja
    aeat_endpoint_bandeja = fields.Char(string="Endpoint Bandeja", config_parameter="aduanas_transport.endpoint.bandeja",
        default="https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP")
    # EXS (Declaración Sumaria de Salida - IE615 V5)
    aeat_endpoint_ie615 = fields.Char(
        string="Endpoint EXS (IE615 V5)",
        config_parameter="aduanas_transport.endpoint.ie615",
        default="https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP",
        help="Presentación DUA EXS. Preproducción: prewww1.aeat.es; Producción: www1.agenciatributaria.gob.es")

    # Certificado electrónico AEAT (autenticación cliente HTTPS; evita 403 en Presentar DUA)
    cert_password = fields.Char(
        string="Contraseña del certificado",
        config_parameter="aduanas_transport.cert_password",
        help="Contraseña del archivo P12/PFX. Obligatoria para que las peticiones a la AEAT usen el certificado."
    )
    cert_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Certificado actual",
        readonly=True,
        help="Adjunto del certificado P12/PFX (se crea al subir un archivo abajo)."
    )
    cert_upload = fields.Binary(
        string="Subir certificado P12/PFX",
        help="Seleccione el archivo .p12 o .pfx de la AEAT. Al guardar se usará en las peticiones HTTPS."
    )
    cert_upload_filename = fields.Char(string="Nombre del archivo")

    # NIF del firmante (certificado): por defecto = empresa si actúa como agente (representación directa), o remitente si autodespacho.
    aeat_nif_firmante = fields.Char(
        string="NIF del firmante (opcional)",
        config_parameter="aduanas_transport.aeat_nif_firmante",
        help="Dejar vacío: si la empresa (ej. Traldis Porta) es distinta del remitente (ej. Dorel), se envía representación directa y se firma con el certificado de la empresa (agente). Si empresa = remitente, autodespacho con certificado del remitente. Rellene solo para forzar otro NIF como firmante."
    )

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
    
    # Campo opcional para compatibilidad con otros módulos (ej: unsplash)
    # Este campo se define aquí para evitar errores cuando otros módulos lo referencian
    unsplash_access_key = fields.Char(
        string="Unsplash Access Key",
        config_parameter="unsplash.access_key",
        help="API Key de Unsplash (definido para compatibilidad con otros módulos)")

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env["ir.config_parameter"].sudo()
        attach_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
        # Devolver siempre el ID (entero), no el recordset, para evitar "can't adapt type 'ir.attachment'" al guardar
        res.update(cert_attachment_id=attach_id or False)
        return res

    def set_values(self):
        super().set_values()
        icp = self.env["ir.config_parameter"].sudo()
        if self.cert_upload:
            name = self.cert_upload_filename or "cert_aeat.p12"
            if not name.lower().endswith((".p12", ".pfx")):
                name = name + ".p12" if "." not in name else name
            attachment = self.env["ir.attachment"].sudo().create({
                "name": name,
                "datas": self.cert_upload,
                "res_model": "res.config.settings",
                "res_id": 0,
                "mimetype": "application/x-pkcs12",
            })
            icp.set_param("aduanas_transport.cert_attachment_id", attachment.id)
        else:
            aid = (self.cert_attachment_id and self.cert_attachment_id.id) or 0
            icp.set_param("aduanas_transport.cert_attachment_id", aid)
    
    @api.model
    def get_openai_api_key(self):
        """
        Método helper para obtener la API key de OpenAI desde la configuración del módulo.
        """
        icp = self.env["ir.config_parameter"].sudo()
        return icp.get_param("aduanas_transport.openai_api_key") or False