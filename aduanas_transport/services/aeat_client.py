import base64
import logging
import os
import tempfile
from datetime import datetime, timezone

import requests
from odoo import _, models

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

    def _get_cert_source(self):
        """Certificado de la compañía activa o parámetro global legacy."""
        company = self.env.company
        icp = self.env["ir.config_parameter"].sudo()
        attach_id = (
            company.aeat_cert_attachment_id.id
            or int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
        )
        password = (
            (company.aeat_cert_password or "").strip()
            or (icp.get_param("aduanas_transport.cert_password") or "").strip()
        )
        return attach_id, password

    def _load_p12_certificate(self):
        """Carga el P12 configurado. Retorna (p12_bytes, x509_cert) o (None, None)."""
        attach_id, password = self._get_cert_source()
        if not attach_id or not password:
            return None, None
        attachment = self.env["ir.attachment"].sudo().browse(attach_id)
        if not attachment.exists() or not attachment.datas:
            return None, None
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12

            p12_data = base64.b64decode(attachment.datas)
            _key, cert, _additional = pkcs12.load_key_and_certificates(
                p12_data, password.encode("utf-8")
            )
            if cert is None:
                return p12_data, None
            return p12_data, cert
        except ImportError:
            _logger.warning("cryptography no disponible para validar certificado P12")
            return None, None
        except Exception as e:
            _logger.warning("No se pudo cargar el certificado P12: %s", e)
            return None, None

    def check_certificate_ready(self):
        """
        Comprueba que hay certificado usable para AEAT.
        Retorna None si OK, o mensaje de error traducible.
        """
        attach_id, password = self._get_cert_source()
        if not attach_id or not password:
            return _(
                "Configure el certificado P12/PFX y su contraseña en "
                "Aduanas > Configuración (o en la ficha de la compañía)."
            )
        attachment = self.env["ir.attachment"].sudo().browse(attach_id)
        if not attachment.exists() or not attachment.datas:
            return _("No se encuentra el archivo del certificado configurado.")
        _p12_data, cert = self._load_p12_certificate()
        if cert is None:
            return _(
                "No se pudo leer el certificado P12. Revise el archivo, la contraseña "
                "y que el paquete cryptography esté instalado en el servidor Odoo."
            )
        not_after = getattr(cert, "not_valid_after_utc", None)
        if not_after is None:
            not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
        if not_after < datetime.now(timezone.utc):
            return _(
                "El certificado AEAT caducó el %s. Renueve el P12 en Aduanas > Configuración "
                "antes de presentar declaraciones."
            ) % not_after.strftime("%d/%m/%Y")
        return None

    def _get_cert_tuple_for_requests(self):
        """
        Obtiene (cert_pem_path, key_pem_path) para requests usando el P12 configurado.
        Convierte P12 a PEM con cryptography. Retorna (None, None) si no hay cert o falla.
        """
        p12_data, _cert = self._load_p12_certificate()
        if not p12_data:
            return None, None
        _attach_id, password = self._get_cert_source()
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
        attach_id, password = self._get_cert_source()
        cert_required = bool(attach_id and password)
        cert_path, key_path = self._get_cert_tuple_for_requests()
        temp_paths = []
        if cert_path:
            temp_paths.append(cert_path)
        if key_path:
            temp_paths.append(key_path)
        if cert_required and not (cert_path and key_path):
            msg = _(
                "Certificado AEAT configurado pero no se pudo cargar para la petición HTTPS. "
                "Revise P12, contraseña y que cryptography esté instalado."
            )
            _logger.error("AEAT %s: %s", service, msg)
            return (0, msg)
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