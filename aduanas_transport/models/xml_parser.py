# -*- coding: utf-8 -*-
from odoo import models, _
import logging
import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

_logger = logging.getLogger(__name__)

def _parse_with_lxml_recover(xml_text):
    """Si lxml está disponible, parsea en modo recuperación y devuelve (root, True) o (None, False)."""
    try:
        from lxml import etree
        parser = etree.XMLParser(recover=True, encoding="utf-8")
        root = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text, parser=parser)
        return root, True
    except Exception:
        return None, False


def _extract_mrn_from_raw_text(text):
    """Intenta extraer MRN del texto cuando el XML no se puede parsear (respuesta mal formada)."""
    if not text or not isinstance(text, str):
        return None
    # Patrones habituales: <MRN>valor</MRN> o <ns:MRN>valor</ns:MRN>
    for pattern in (
        r"<MRN>([^<]+)</MRN>",
        r"<[^:>]*:?MRN[^>]*>([^<]+)</[^:>]*:?MRN",
        r"<[^>]*MRN[^>]*>([^<]+)<",
        r"(ES\d{2}[A-Z0-9]{14,22})",  # MRN típico: país + 2 dígitos + alfanumérico
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = (m.group(1) or "").strip()
            if val and len(val) >= 10:
                return val
    return None

class AduanaXmlParser(models.AbstractModel):
    _name = "aduanas.xml.parser"
    _description = "Parser de respuestas XML de AEAT"

    def _local_name(self, tag):
        return tag.split("}")[-1] if "}" in tag else tag

    def _find_first_text(self, root, *local_names):
        names = {name.lower() for name in local_names}
        for elem in root.iter():
            if self._local_name(elem.tag).lower() in names and (elem.text or "").strip():
                return (elem.text or "").strip()
        return None

    def _find_all_text(self, root, *local_names):
        names = {name.lower() for name in local_names}
        values = []
        for elem in root.iter():
            if self._local_name(elem.tag).lower() in names and (elem.text or "").strip():
                values.append((elem.text or "").strip())
        return values

    def parse_aeat_response(self, xml_text, service_name=""):
        """Parsea respuesta XML de AEAT y extrae información relevante"""
        if not xml_text:
            return {"success": False, "error": "Respuesta vacía"}

        if service_name in ("CC515C", "CCAESC", "CC507C", "RE515C", "RE507C", "REAESC"):
            aes = self.parse_aes_export_response(xml_text, service_name)
            return self._aes_to_legacy_parse(aes)

        if service_name == "BANDEJA":
            bandeja = self.parse_bandeja_response(xml_text)
            legacy = {"success": True, "messages": [], "errors": bandeja.get("errors") or [], "incidencias": []}
            if bandeja.get("last_message_num"):
                legacy["last_message_num"] = bandeja["last_message_num"]
            for msg in bandeja.get("messages") or []:
                legacy["messages"].append(msg.get("message_type") or "")
                if msg.get("mrn"):
                    legacy["mrn"] = msg["mrn"]
                if msg.get("estado_aes"):
                    legacy["estado_aes"] = msg["estado_aes"]
                    if msg["estado_aes"].upper() == "SA":
                        legacy["exited"] = True
                    if msg["estado_aes"].upper() in ("DE", "PL", "PS"):
                        legacy["released"] = True
                if msg.get("circuito"):
                    legacy["circuito"] = msg["circuito"]
                if msg.get("fecha_salida_efectiva"):
                    legacy["fecha_salida_efectiva"] = msg["fecha_salida_efectiva"]
                    legacy["exited"] = True
                if msg.get("fecha_levante"):
                    legacy["fecha_levante"] = msg["fecha_levante"]
                if msg.get("fecha_levante_salida"):
                    legacy["fecha_levante_salida"] = msg["fecha_levante_salida"]
                if msg.get("csv_levante_export"):
                    legacy["csv_levante"] = msg["csv_levante_export"]
                if msg.get("csv_levante_salida"):
                    legacy["csv_levante_salida"] = msg["csv_levante_salida"]
                tipo = (msg.get("message_type") or "").upper()
                if tipo == "CLEVEX":
                    legacy["released"] = True
                if tipo in ("CSALID", "RESUSA"):
                    legacy["exited"] = True
            if legacy.get("errors"):
                legacy["success"] = False
            return legacy

        try:
            # Intentar parsear el XML
            root = ET.fromstring(xml_text)
            
            # Buscar namespaces comunes
            namespaces = {
                'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                'aes': 'urn:aeat:adex:jdit:ws:aes',
                'imp': 'urn:aeat:adu:importacion',
                'band': 'urn:aeat:adht:band:det',
            }
            
            result = {
                "success": True,
                "mrn": None,
                "lrn": None,
                "accepted": False,
                "released": False,
                "exited": False,
                "estado_aes": None,
                "response_code": None,
                "circuito": None,
                "circuito_llegada": None,
                "csv_declaracion": None,
                "csv_levante": None,
                "csv_levante_salida": None,
                "csv_certificado_salida": None,
                "fecha_admision": None,
                "fecha_levante": None,
                "fecha_llegada": None,
                "fecha_levante_salida": None,
                "fecha_salida_efectiva": None,
                "errors": [],
                "warnings": [],
                "messages": [],
                "raw_xml": xml_text
            }
            
            # Extraer MRN
            mrn_elements = root.findall(".//MRN") + root.findall(".//{*}MRN")
            if mrn_elements:
                result["mrn"] = mrn_elements[0].text
            
            # Extraer LRN
            lrn_elements = root.findall(".//LRN") + root.findall(".//{*}LRN")
            if lrn_elements:
                result["lrn"] = lrn_elements[0].text

            result["estado_aes"] = self._find_first_text(root, "estadoAES", "EstadoAES")
            result["response_code"] = self._find_first_text(root, "codigoRespuesta", "CódigoRespuesta")
            result["circuito"] = self._find_first_text(root, "circuitoAEAT", "circuito", "Circuito")
            result["circuito_llegada"] = self._find_first_text(root, "circuitoLlegada")
            result["csv_declaracion"] = self._find_first_text(root, "CSVDeclaracionElectronica", "CSVDeclaracion")
            result["csv_levante"] = self._find_first_text(root, "CSVLevanteExportacion", "CSVLevante")
            result["csv_levante_salida"] = self._find_first_text(root, "CSVLevanteSalida")
            result["csv_certificado_salida"] = self._find_first_text(root, "CSVCertificadoSalida")
            result["fecha_admision"] = self._find_first_text(root, "fechaAdmision", "FechaAdmision")
            result["fecha_levante"] = self._find_first_text(root, "fechaLevante", "FechaLevante")
            result["fecha_llegada"] = self._find_first_text(root, "fechaLlegada")
            result["fecha_levante_salida"] = self._find_first_text(root, "fechaLevanteSalida")
            result["fecha_salida_efectiva"] = self._find_first_text(root, "fechaSalidaEfectiva", "fechaSalida")
            if result["circuito_llegada"] and not result["circuito"]:
                result["circuito"] = result["circuito_llegada"]
            
            # Buscar errores e incidencias
            error_elements = (
                root.findall(".//Error") + 
                root.findall(".//{*}Error") +
                root.findall(".//FunctionalError") +
                root.findall(".//{*}FunctionalError") +
                root.findall(".//XMLError") +
                root.findall(".//{*}XMLError") +
                root.findall(".//XmlError") +
                root.findall(".//{*}XmlError") +
                root.findall(".//ERROR") +
                root.findall(".//{*}ERROR") +
                root.findall(".//CodigoError") +
                root.findall(".//{*}CodigoError") +
                root.findall(".//Incidencia") +
                root.findall(".//{*}Incidencia") +
                root.findall(".//Requerimiento") +
                root.findall(".//{*}Requerimiento") +
                root.findall(".//Solicitud") +
                root.findall(".//{*}Solicitud")
            )
            
            # Estructura para incidencias
            result["incidencias"] = []
            
            for err in error_elements:
                error_text = err.text or ""
                error_code = err.get("codigo") or err.get("code") or ""
                
                # Extraer información estructurada
                incidencia_data = {
                    "codigo": error_code,
                    "mensaje": error_text,
                    "tipo": "error",  # Por defecto
                    "elemento_padre": err.tag,
                }
                details = {}
                
                # Determinar tipo de incidencia por el tag o contenido
                tag_lower = err.tag.lower()
                if "requerimiento" in tag_lower or "requirement" in tag_lower:
                    incidencia_data["tipo"] = "requerimiento"
                elif "solicitud" in tag_lower or "request" in tag_lower:
                    incidencia_data["tipo"] = "solicitud_info"
                elif "advertencia" in tag_lower or "warning" in tag_lower:
                    incidencia_data["tipo"] = "advertencia"
                elif "rechazo" in tag_lower or "rejected" in tag_lower:
                    incidencia_data["tipo"] = "rechazo"
                elif "suspension" in tag_lower or "suspended" in tag_lower:
                    incidencia_data["tipo"] = "suspension"
                
                # Buscar más información en elementos hijos
                for child in err:
                    local_child = self._local_name(child.tag)
                    child_text = (child.text or "").strip()
                    if child_text:
                        details[local_child] = child_text
                    if local_child in ("errorDescription", "errorText", "remarks"):
                        incidencia_data["mensaje"] = child.text or incidencia_data["mensaje"]
                    elif local_child in ("errorCode", "errorReason"):
                        incidencia_data["codigo"] = child.text or incidencia_data["codigo"]
                    elif child.tag.endswith("Tipo") or child.tag.endswith("Type"):
                        incidencia_data["tipo"] = child.text or incidencia_data["tipo"]
                    elif child.tag.endswith("Descripcion") or child.tag.endswith("Description"):
                        incidencia_data["mensaje"] = child.text or incidencia_data["mensaje"]
                    elif child.tag.endswith("Codigo") or child.tag.endswith("Code"):
                        incidencia_data["codigo"] = child.text or incidencia_data["codigo"]

                if not incidencia_data["mensaje"]:
                    pointer = details.get("errorPointer") or details.get("ErrorPointer")
                    reason = details.get("errorReason") or details.get("ErrorReason")
                    code = details.get("errorCode") or details.get("ErrorCode") or incidencia_data.get("codigo")
                    remarks = details.get("remarks") or details.get("errorDescription") or details.get("errorText")
                    parts = []
                    if pointer:
                        parts.append(pointer)
                    if code:
                        parts.append("código %s" % code)
                    if reason:
                        parts.append("motivo %s" % reason)
                    if remarks:
                        parts.append(remarks)
                    incidencia_data["mensaje"] = " - ".join(parts) or "Error AEAT sin descripción textual"
                
                result["incidencias"].append(incidencia_data)
                
                # Mantener compatibilidad con formato anterior
                local_err = self._local_name(err.tag)
                formatted_error = incidencia_data["mensaje"]
                if incidencia_data.get("codigo") and incidencia_data["codigo"] not in formatted_error:
                    formatted_error = "%s: %s" % (incidencia_data["codigo"], formatted_error)
                if local_err.endswith("Error") or local_err.endswith("ERROR"):
                    result["errors"].append(formatted_error)
                elif "Codigo" in err.tag:
                    result["errors"].append(f"Código: {formatted_error}")
                else:
                    # Otros tipos también se añaden a errors para compatibilidad
                    result["errors"].append(formatted_error)
            
            # Buscar mensajes
            message_elements = (
                root.findall(".//Mensaje") + 
                root.findall(".//{*}Mensaje") +
                root.findall(".//Message") +
                root.findall(".//{*}Message")
            )
            for msg in message_elements:
                if msg.text:
                    result["messages"].append(msg.text)
            
            # Buscar estado de aceptación
            aceptacion_elements = (
                root.findall(".//ACEPTACION") +
                root.findall(".//{*}ACEPTACION") +
                root.findall(".//Aceptacion") +
                root.findall(".//{*}Aceptacion")
            )
            if aceptacion_elements:
                result["accepted"] = True
            for elem in root.iter():
                if self._local_name(elem.tag) == "CC415R":
                    result["accepted"] = True
                    break
            
            # Buscar levante
            levante_elements = (
                root.findall(".//LEVANTE") +
                root.findall(".//{*}LEVANTE") +
                root.findall(".//Levante") +
                root.findall(".//{*}Levante")
            )
            if levante_elements:
                result["released"] = True

            message_type = (self._find_first_text(root, "messageType") or "").upper()
            estado = (result.get("estado_aes") or "").upper()
            response_code = (result.get("response_code") or "").upper()
            if response_code in ("A", "B", "L", "OK") or estado:
                result["accepted"] = True
            if response_code == "L" or estado in ("DE", "PL", "PS", "SA") or result.get("fecha_levante") or result.get("fecha_levante_salida"):
                result["released"] = True
            if estado == "SA" or message_type in ("CSALID", "IE599") or result.get("fecha_salida_efectiva"):
                result["exited"] = True
            
            # Buscar NumUltimoMensaje en bandeja
            num_msg_elements = (
                root.findall(".//NumUltimoMensaje") +
                root.findall(".//{*}NumUltimoMensaje")
            )
            if num_msg_elements:
                try:
                    result["last_message_num"] = int(num_msg_elements[0].text or 0)
                except (ValueError, TypeError):
                    pass
            
            # Si hay errores, marcar como no exitoso
            if result["errors"]:
                result["success"] = False
            
            return result
            
        except ParseError as e:
            _logger.warning("Error parseando XML de %s: %s. Intentando lxml recover o extracción por texto.", service_name, e)
            # Intentar con lxml en modo recuperación (tolera XML mal formado)
            root_recover, ok = _parse_with_lxml_recover(xml_text)
            if ok and root_recover is not None:
                mrn_el = root_recover.find(".//{*}MRN") or root_recover.find(".//MRN")
                lrn_el = root_recover.find(".//{*}LRN") or root_recover.find(".//LRN")
                mrn_val = (mrn_el.text or "").strip() if mrn_el is not None else None
                lrn_val = (lrn_el.text or "").strip() if lrn_el is not None else None
                if mrn_val:
                    return {
                        "success": True,
                        "mrn": mrn_val,
                        "lrn": lrn_val,
                        "errors": [],
                        "warnings": ["XML con errores de formato; MRN extraído con parser recuperación."],
                        "messages": ["MRN obtenido correctamente."],
                        "raw_xml": xml_text,
                    }
            mrn_fallback = _extract_mrn_from_raw_text(xml_text)
            if mrn_fallback:
                return {
                    "success": True,
                    "mrn": mrn_fallback,
                    "lrn": None,
                    "errors": [],
                    "warnings": ["La respuesta no es XML válido pero se encontró MRN. Revisar adjunto DUA_CUSDEC_EX1_response.xml."],
                    "messages": ["MRN extraído de la respuesta (formato de respuesta inesperado)."],
                    "raw_xml": xml_text,
                }
            return {
                "success": False,
                "error": "La respuesta de la AEAT no es un XML válido (posible página de error o formato distinto). Revisar el adjunto de respuesta.",
                "errors": ["mismatched tag o XML mal formado. Revisar DUA_CUSDEC_EX1_response.xml."],
                "raw_xml": xml_text,
            }
        except Exception as e:
            _logger.exception("Error inesperado parseando XML de %s", service_name)
            mrn_fallback = _extract_mrn_from_raw_text(xml_text)
            if mrn_fallback:
                return {
                    "success": True,
                    "mrn": mrn_fallback,
                    "lrn": None,
                    "errors": [],
                    "warnings": ["Error al parsear pero se encontró MRN en la respuesta."],
                    "messages": ["MRN extraído de la respuesta."],
                    "raw_xml": xml_text,
                }
            return {
                "success": False,
                "error": "Error inesperado: %s. Revisar el adjunto de respuesta." % str(e),
                "raw_xml": xml_text,
            }

    def extract_mrn_from_xml(self, xml_text):
        """Extrae MRN de una respuesta XML (método legacy para compatibilidad)"""
        parsed = self.parse_aeat_response(xml_text)
        return parsed.get("mrn")

    def parse_ie615_response(self, xml_text):
        """
        Parsea la respuesta del servicio IE615 (EXS): IE628 (aceptación), IE616 (rechazo funcional)
        o IE919 (rechazo XML). La respuesta suele venir en un envelope SOAP.
        Devuelve: success, mrn, exs_circuito, exs_dec_csv, exs_rel_csv, exs_tipo_declaracion,
                  exs_predeclaracion, errors, response_type (CC628A/CC616A/CD919B).
        """
        if not xml_text or not xml_text.strip():
            return {"success": False, "errors": [_("Respuesta vacía")], "response_type": None}
        try:
            root = ET.fromstring(xml_text)
            # Quitar namespace para búsquedas
            def strip_ns(tag):
                return tag.split("}")[-1] if "}" in tag else tag
            # Buscar Body y dentro el mensaje (CC628A, CC616A o CD919B)
            body = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body")
            if body is None:
                body = root.find(".//Body") or root
            msg = None
            for child in body:
                if child.tag and strip_ns(child.tag) in ("CC628A", "CC616A", "CD919B"):
                    msg = child
                    break
            if msg is None:
                # Quizá la respuesta es directa (sin SOAP)
                for elem in [root] + list(root):
                    if elem.tag and strip_ns(elem.tag) in ("CC628A", "CC616A", "CD919B"):
                        msg = elem
                        break
            if msg is None:
                return {"success": False, "errors": [_("No se encontró mensaje IE628/IE616/IE919 en la respuesta")], "raw_xml": xml_text, "response_type": None}
            msg_tag = strip_ns(msg.tag)
            result = {"success": False, "mrn": None, "exs_circuito": None, "exs_dec_csv": None, "exs_rel_csv": None, "exs_tipo_declaracion": None, "exs_predeclaracion": None, "errors": [], "response_type": msg_tag}
            def find_text(parent, local_name):
                for e in parent.iter():
                    if strip_ns(e.tag) == local_name and (e.text or "").strip():
                        return (e.text or "").strip()
                return None
            # HEAHEA común
            hea = None
            for e in msg.iter():
                if strip_ns(e.tag) == "HEAHEA":
                    hea = e
                    break
            if hea is not None:
                result["mrn"] = find_text(hea, "DocNumHEA5")
                result["exs_tipo_declaracion"] = find_text(hea, "DecTypeHEA")
                result["exs_predeclaracion"] = find_text(hea, "PreDecCodeHEA")
                result["exs_circuito"] = find_text(hea, "CusChanHEA")
                result["exs_dec_csv"] = find_text(hea, "DecCsvHEA")
                result["exs_rel_csv"] = find_text(hea, "RelCsvHEA")
            if msg_tag == "CC628A":
                result["success"] = True
                return result
            if msg_tag == "CC616A":
                for err in msg.iter():
                    if strip_ns(err.tag) == "FUNERRER1":
                        err_typ = find_text(err, "ErrTypER11")
                        err_poi = find_text(err, "ErrPoiER12")
                        err_val = find_text(err, "OriAttValER14")
                        result["errors"].append("%s: %s (valor: %s)" % (err_typ or "", err_poi or "", err_val or ""))
                if not result["errors"]:
                    result["errors"].append(_("Rechazo funcional IE616 sin detalle"))
                return result
            if msg_tag == "CD919B":
                for err in msg.iter():
                    if strip_ns(err.tag) == "XMLERR805":
                        err_reason = find_text(err, "ErrReaXMLER802") or find_text(err, "OriAttValXMLER804")
                        result["errors"].append(err_reason or _("Error de formato XML"))
                if not result["errors"]:
                    result["errors"].append(_("Rechazo XML IE919 sin detalle"))
                return result
            return result
        except ParseError as e:
            _logger.exception("Error parseando respuesta IE615")
            return {"success": False, "errors": [_("Error parseando XML: %s") % str(e)], "raw_xml": xml_text, "response_type": None}
        except Exception as e:
            _logger.exception("Error inesperado parseando respuesta IE615")
            return {"success": False, "errors": [str(e)], "raw_xml": xml_text, "response_type": None}

    def _aes_to_legacy_parse(self, aes):
        """Adapta salida de parse_aes_export_response al formato usado por _apply_aeat_parsed_response."""
        legacy = {
            "success": aes.get("success"),
            "mrn": aes.get("mrn"),
            "estado_aes": aes.get("estado_aes"),
            "circuito": aes.get("circuito"),
            "circuito_llegada": aes.get("circuito"),
            "csv_declaracion": aes.get("csv_declaracion"),
            "csv_levante": aes.get("csv_levante_export"),
            "csv_levante_salida": aes.get("csv_levante_salida"),
            "csv_certificado_salida": aes.get("csv_certificado_salida"),
            "fecha_levante": aes.get("fecha_levante"),
            "fecha_llegada": aes.get("fecha_llegada"),
            "fecha_levante_salida": aes.get("fecha_levante_salida"),
            "fecha_salida_efectiva": aes.get("fecha_salida_efectiva"),
            "released": aes.get("released"),
            "exited": aes.get("exited"),
            "accepted": aes.get("success") and bool(aes.get("mrn")),
            "errors": list(aes.get("errors") or []),
            "messages": [],
            "incidencias": [],
            "tipo_respuesta": aes.get("tipo_respuesta"),
            "raw_xml": aes.get("raw_xml"),
        }
        for fe in aes.get("functional_errors") or []:
            legacy["errors"].append(
                "%s: %s" % (fe.get("error_pointer") or "", fe.get("error_description") or "")
            )
            legacy["incidencias"].append({
                "tipo": "error",
                "codigo": fe.get("error_code") or fe.get("error_reason") or "",
                "mensaje": fe.get("error_description") or fe.get("error_pointer") or "",
            })
        for xe in aes.get("xml_errors") or []:
            legacy["errors"].append(xe.get("error_text") or "Error XML")
        if (aes.get("tipo_respuesta") or "").upper() in ("EF", "EX"):
            legacy["success"] = False
        return legacy

    def _xml_text(self, root, tag):
        """Primer texto de un elemento por nombre local (ignora namespace)."""
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == tag and el.text:
                return (el.text or "").strip()
        return None

    def _xml_all(self, root, tag):
        out = []
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == tag:
                out.append(el)
        return out

    def parse_aes_export_response(self, xml_text, service_name=""):
        """
        Parser unificado respuestas AES export (CC515C, CCAESC, CC507C).
        GuiaWEBExp: ControlRespuesta/tipoRespuesta, FunctionalError, DatosRespuestaCorrecta, DatosComunicacion.
        """
        if not xml_text or not xml_text.strip():
            return {"success": False, "error": "Respuesta vacía", "errors": []}
        result = {
            "success": False,
            "service": service_name,
            "tipo_respuesta": None,
            "codigo_respuesta": None,
            "mrn": None,
            "estado_aes": None,
            "circuito": None,
            "csv_declaracion": None,
            "csv_levante_export": None,
            "csv_levante_salida": None,
            "csv_certificado_salida": None,
            "fecha_levante": None,
            "fecha_llegada": None,
            "fecha_levante_salida": None,
            "fecha_salida_efectiva": None,
            "functional_errors": [],
            "xml_errors": [],
            "errors": [],
            "released": False,
            "exited": False,
            "raw_xml": xml_text,
        }
        try:
            root, ok = _parse_with_lxml_recover(xml_text)
            if not ok or root is None:
                root = ET.fromstring(xml_text)
            result["tipo_respuesta"] = self._xml_text(root, "tipoRespuesta")
            result["codigo_respuesta"] = self._xml_text(root, "codigoRespuesta")
            result["mrn"] = self._xml_text(root, "MRN") or _extract_mrn_from_raw_text(xml_text)
            result["estado_aes"] = self._xml_text(root, "estadoAES")
            result["circuito"] = (
                self._xml_text(root, "circuitoLlegada")
                or self._xml_text(root, "circuito")
            )
            result["csv_declaracion"] = self._xml_text(root, "CSVDeclaracionElectronica")
            result["csv_levante_export"] = self._xml_text(root, "CSVLevanteExportacion")
            result["csv_levante_salida"] = self._xml_text(root, "CSVLevanteSalida")
            result["csv_certificado_salida"] = self._xml_text(root, "CSVCertificadoSalida")
            fecha_levante = self._xml_text(root, "fechaLevante")
            if fecha_levante and len(fecha_levante) >= 10:
                result["fecha_levante"] = fecha_levante[:10]
            fecha_lleg = self._xml_text(root, "fechaLlegada") or self._xml_text(root, "fechaLlegadaSalida")
            if fecha_lleg and len(fecha_lleg) >= 10:
                result["fecha_llegada"] = fecha_lleg[:10]
            fecha_levante_salida = self._xml_text(root, "fechaLevanteSalida")
            if fecha_levante_salida and len(fecha_levante_salida) >= 10:
                result["fecha_levante_salida"] = fecha_levante_salida[:10]
            fecha_se = self._xml_text(root, "fechaSalidaEfectiva")
            if fecha_se and len(fecha_se) >= 10:
                result["fecha_salida_efectiva"] = fecha_se[:10]
            for fe in self._xml_all(root, "FunctionalError"):
                result["functional_errors"].append({
                    "error_pointer": self._xml_text(fe, "errorPointer"),
                    "error_code": self._xml_text(fe, "errorCode"),
                    "error_reason": self._xml_text(fe, "errorReason"),
                    "error_description": self._xml_text(fe, "errorDescription"),
                })
            for xe in self._xml_all(root, "XMLError"):
                result["xml_errors"].append({
                    "error_text": self._xml_text(xe, "errorText"),
                    "error_code": self._xml_text(xe, "errorCode"),
                })
            tr = (result["tipo_respuesta"] or "").upper()
            if tr == "EF":
                result["success"] = False
                for fe in result["functional_errors"]:
                    result["errors"].append(
                        "%s: %s" % (fe.get("error_pointer") or "", fe.get("error_description") or "")
                    )
            elif tr == "EX":
                result["success"] = False
                for xe in result["xml_errors"]:
                    result["errors"].append(xe.get("error_text") or "Error XML")
            elif tr in ("OK", "AC", "P") or result["mrn"]:
                result["success"] = True
            if result["estado_aes"] in ("DE", "PL", "PS"):
                result["released"] = True
            if result["estado_aes"] in ("SA", "SE") or result["fecha_salida_efectiva"]:
                result["exited"] = True
            if result["codigo_respuesta"] == "L":
                result["released"] = True
            return result
        except Exception as e:
            _logger.warning("parse_aes_export_response %s: %s", service_name, e)
            mrn = _extract_mrn_from_raw_text(xml_text)
            if mrn:
                return {"success": True, "mrn": mrn, "errors": [], "raw_xml": xml_text}
            return {"success": False, "error": str(e), "errors": [str(e)], "raw_xml": xml_text}

    def parse_bandeja_response(self, xml_text):
        """
        Extrae mensajes de bandeja EXPORAES embebidos (ComunicaLevanteExpor, ComunicaResulSalida, etc.).
        """
        result = {"messages": [], "last_message_num": 0, "incidencias": [], "errors": []}
        if not xml_text:
            return result
        try:
            root, ok = _parse_with_lxml_recover(xml_text)
            if not ok or root is None:
                root = ET.fromstring(xml_text)
            num = self._xml_text(root, "NumUltimoMensaje")
            if num:
                try:
                    result["last_message_num"] = int(num)
                except ValueError:
                    pass
            # Cada bloque con messageType + DatosComunicacion
            for el in root.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local != "messageType" or not el.text:
                    continue
                msg_type = (el.text or "").strip().upper()
                if not hasattr(el, "getparent"):
                    continue
                block = el
                for _ in range(15):
                    parent = block.getparent()
                    if parent is None:
                        break
                    block = parent
                msg = {"message_type": msg_type}
                for sub in block.iter() if hasattr(block, "iter") else []:
                    loc = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                    if loc == "MRN" and sub.text:
                        msg["mrn"] = sub.text.strip()
                    elif loc == "estadoAES" and sub.text:
                        msg["estado_aes"] = sub.text.strip()
                    elif loc == "fechaLevante" and sub.text:
                        msg["fecha_levante"] = sub.text.strip()[:10]
                    elif loc == "fechaSalidaEfectiva" and sub.text:
                        msg["fecha_salida_efectiva"] = sub.text.strip()[:10]
                    elif loc == "fechaLevanteSalida" and sub.text:
                        msg["fecha_levante_salida"] = sub.text.strip()[:10]
                    elif loc == "CSVLevanteExportacion" and sub.text:
                        msg["csv_levante_export"] = sub.text.strip()
                    elif loc == "CSVLevanteSalida" and sub.text:
                        msg["csv_levante_salida"] = sub.text.strip()
                if msg_type or msg.get("mrn"):
                    result["messages"].append(msg)
            # Fallback: regex sobre XML completo si no hay getparent (ElementTree estándar)
            if not result["messages"]:
                import re
                for m in re.finditer(
                    r"<messageType>([^<]+)</messageType>.*?<MRN>([^<]+)</MRN>",
                    xml_text,
                    re.DOTALL | re.IGNORECASE,
                ):
                    result["messages"].append({
                        "message_type": m.group(1).strip().upper(),
                        "mrn": m.group(2).strip(),
                    })
                for m in re.finditer(
                    r"<messageType>(CSALID|CLEVEX|CLEVSA|CDISSA)[^<]*</messageType>",
                    xml_text,
                    re.IGNORECASE,
                ):
                    msg = {"message_type": m.group(1).upper()}
                    mrn_m = re.search(
                        r"<MRN>([^<]+)</MRN>",
                        xml_text[m.end() : m.end() + 800],
                        re.IGNORECASE,
                    )
                    if mrn_m:
                        msg["mrn"] = mrn_m.group(1).strip()
                    fe_m = re.search(
                        r"<fechaSalidaEfectiva>([^<]+)</fechaSalidaEfectiva>",
                        xml_text[m.end() : m.end() + 800],
                        re.IGNORECASE,
                    )
                    if fe_m:
                        msg["fecha_salida_efectiva"] = fe_m.group(1).strip()[:10]
                    fls_m = re.search(
                        r"<fechaLevanteSalida>([^<]+)</fechaLevanteSalida>",
                        xml_text[m.end() : m.end() + 800],
                        re.IGNORECASE,
                    )
                    if fls_m:
                        msg["fecha_levante_salida"] = fls_m.group(1).strip()[:10]
                    estado_m = re.search(
                        r"<estadoAES>([^<]+)</estadoAES>",
                        xml_text[m.end() : m.end() + 800],
                        re.IGNORECASE,
                    )
                    if estado_m:
                        msg["estado_aes"] = estado_m.group(1).strip()
                    csv_m = re.search(
                        r"<CSVLevanteSalida>([^<]+)</CSVLevanteSalida>",
                        xml_text[m.end() : m.end() + 800],
                        re.IGNORECASE,
                    )
                    if csv_m:
                        msg["csv_levante_salida"] = csv_m.group(1).strip()
                    result["messages"].append(msg)
        except Exception as e:
            _logger.warning("parse_bandeja_response: %s", e)
            result["errors"].append(str(e))
        return result

