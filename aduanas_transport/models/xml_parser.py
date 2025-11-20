# -*- coding: utf-8 -*-
from odoo import models
import logging
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

_logger = logging.getLogger(__name__)

class AduanaXmlParser(models.AbstractModel):
    _name = "aduanas.xml.parser"
    _description = "Parser de respuestas XML de AEAT"

    def parse_aeat_response(self, xml_text, service_name=""):
        """Parsea respuesta XML de AEAT y extrae información relevante"""
        if not xml_text:
            return {"success": False, "error": "Respuesta vacía"}
        
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
            
            # Buscar errores e incidencias
            error_elements = (
                root.findall(".//Error") + 
                root.findall(".//{*}Error") +
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
                    if child.tag.endswith("Tipo") or child.tag.endswith("Type"):
                        incidencia_data["tipo"] = child.text or incidencia_data["tipo"]
                    elif child.tag.endswith("Descripcion") or child.tag.endswith("Description"):
                        incidencia_data["mensaje"] = child.text or incidencia_data["mensaje"]
                    elif child.tag.endswith("Codigo") or child.tag.endswith("Code"):
                        incidencia_data["codigo"] = child.text or incidencia_data["codigo"]
                
                result["incidencias"].append(incidencia_data)
                
                # Mantener compatibilidad con formato anterior
                if err.tag.endswith("Error") or err.tag.endswith("ERROR"):
                    result["errors"].append(error_text)
                elif "Codigo" in err.tag:
                    result["errors"].append(f"Código: {error_text}")
                else:
                    # Otros tipos también se añaden a errors para compatibilidad
                    result["errors"].append(error_text)
            
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
            
            # Buscar levante
            levante_elements = (
                root.findall(".//LEVANTE") +
                root.findall(".//{*}LEVANTE") +
                root.findall(".//Levante") +
                root.findall(".//{*}Levante")
            )
            if levante_elements:
                result["released"] = True
            
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
            _logger.exception("Error parseando XML de %s", service_name)
            return {
                "success": False,
                "error": f"Error parseando XML: {str(e)}",
                "raw_xml": xml_text
            }
        except Exception as e:
            _logger.exception("Error inesperado parseando XML de %s", service_name)
            return {
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "raw_xml": xml_text
            }

    def extract_mrn_from_xml(self, xml_text):
        """Extrae MRN de una respuesta XML (método legacy para compatibilidad)"""
        parsed = self.parse_aeat_response(xml_text)
        return parsed.get("mrn")

