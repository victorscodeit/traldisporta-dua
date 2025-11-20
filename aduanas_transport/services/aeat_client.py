import logging
import requests
from odoo import models
_logger = logging.getLogger(__name__)

class AduanasAeatClient(models.AbstractModel):
    _name = "aduanas.aeat.client"
    _description = "Cliente AEAT Aduanas (SOAP)"

    def sign_xml(self, xml_text: str, service: str) -> str:
        """Punto de inserción para firma XAdES/WS-Security.
        MVP: devuelve el XML sin firmar. En productivo: firmar el envelope SOAP.
        """
        return xml_text

    def send_xml(self, endpoint: str, xml_text: str, service: str, timeout=30) -> str:
        if not endpoint:
            raise ValueError("Endpoint no configurado para %s" % service)
        xml_signed = self.sign_xml(xml_text, service)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}
        try:
            resp = requests.post(endpoint, data=xml_signed.encode("utf-8"), headers=headers, timeout=timeout)
            resp.raise_for_status()
            _logger.info("AEAT %s → %s (%s)", service, endpoint, resp.status_code)
            return resp.text
        except Exception as e:
            _logger.exception("Error enviando a AEAT %s: %s", service, e)
            return ""