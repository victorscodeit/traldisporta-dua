import base64
import logging
import os
import tempfile
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

    def _p12_to_pem_files(self, p12_data, password):
        """
        Convierte P12/PFX a archivos temporales PEM (cert + key) usando cryptography
        (compatible con Odoo 16 / cryptography 3.4.x). Retorna (cert_pem_path, key_pem_path) o (None, None).
        """
        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
                pkcs12,
            )
        except ImportError as e:
            _logger.warning("cryptography no disponible para P12: %s", e)
            return None, None
        password_bytes = password.encode("utf-8") if isinstance(password, str) else password
        try:
            key, cert, _additional_certs = pkcs12.load_key_and_certificates(
                p12_data, password_bytes
            )
        except TypeError:
            # cryptography < 3.0 puede requerir backend
            try:
                from cryptography.hazmat.backends import default_backend
                key, cert, _additional_certs = pkcs12.load_key_and_certificates(
                    p12_data, password_bytes, default_backend()
                )
            except Exception as e:
                _logger.warning("Error cargando P12 (contraseña o formato): %s", e)
                return None, None
        except Exception as e:
            _logger.warning("Error cargando P12 (contraseña o formato): %s", e)
            return None, None
        if key is None or cert is None:
            _logger.warning("El P12 no contiene clave privada y certificado")
            return None, None
        try:
            key_pem = key.private_bytes(
                Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
            )
            cert_pem = cert.public_bytes(Encoding.PEM)
        except Exception as e:
            _logger.warning("Error serializando P12 a PEM: %s", e)
            return None, None
        cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
        key_fd, key_path = tempfile.mkstemp(suffix=".pem")
        try:
            os.write(cert_fd, cert_pem)
            os.close(cert_fd)
            cert_fd = None
            os.write(key_fd, key_pem)
            os.close(key_fd)
            key_fd = None
            return cert_path, key_path
        except Exception as e:
            _logger.warning("Error escribiendo PEM temporales: %s", e)
            for fd, path in ((cert_fd, cert_path), (key_fd, key_path)):
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
            return None, None

    def _get_cert_tuple_for_requests(self):
        """
        Obtiene (cert_pem_path, key_pem_path) para requests usando el P12 configurado.
        Convierte P12 a PEM con cryptography. Retorna (None, None) si no hay cert o falla.
        """
        icp = self.env["ir.config_parameter"].sudo()
        attach_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
        password = (icp.get_param("aduanas_transport.cert_password") or "").strip()
        if not attach_id or not password:
            return None, None
        attachment = self.env["ir.attachment"].sudo().browse(attach_id)
        if not attachment.exists() or not attachment.datas:
            return None, None
        try:
            p12_data = base64.b64decode(attachment.datas)
        except Exception as e:
            _logger.warning("No se pudo decodificar el certificado P12: %s", e)
            return None, None
        return self._p12_to_pem_files(p12_data, password)

    def send_xml(self, endpoint: str, xml_text: str, service: str, timeout=30):
        """
        Envía XML al endpoint AEAT. Retorna (status_code, response_text).
        Si hay certificado P12 configurado, se convierte a PEM con cryptography y se usa con requests (sin requests-pkcs12).
        """
        if not endpoint:
            raise ValueError("Endpoint no configurado para %s" % service)
        xml_signed = self.sign_xml(xml_text, service)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}
        data = xml_signed.encode("utf-8")
        cert_path, key_path = self._get_cert_tuple_for_requests()
        temp_paths = []
        if cert_path:
            temp_paths.append(cert_path)
        if key_path:
            temp_paths.append(key_path)
        try:
            if cert_path and key_path:
                resp = requests.post(
                    endpoint,
                    data=data,
                    headers=headers,
                    timeout=timeout,
                    cert=(cert_path, key_path),
                    verify=True,
                )
                _logger.info("AEAT %s → %s (%s) [con certificado PEM]", service, endpoint, resp.status_code)
                return (resp.status_code, resp.text)
            resp = requests.post(endpoint, data=data, headers=headers, timeout=timeout)
            _logger.info("AEAT %s → %s (%s)", service, endpoint, resp.status_code)
            return (resp.status_code, resp.text)
        except requests.exceptions.RequestException as e:
            _logger.exception("Error enviando a AEAT %s: %s", service, e)
            return (0, "")
        finally:
            for path in temp_paths:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass

    def send_xml_legacy(self, endpoint: str, xml_text: str, service: str, timeout=30) -> str:
        """Compatibilidad: devuelve solo el texto. Si status != 200 devuelve vacío."""
        status, text = self.send_xml(endpoint, xml_text, service, timeout)
        return text if status == 200 else ""