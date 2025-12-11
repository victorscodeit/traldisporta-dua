# -*- coding: utf-8 -*-
"""
Servicio para consultar la API TARIC de la Unión Europea
Documentación: https://ec.europa.eu/taxation_customs/dds2/taric/services/goods?wsdl
"""
import logging
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class TaricService(models.AbstractModel):
    _name = "aduanas.taric.service"
    _description = "Servicio para consultar API TARIC de la UE"

    TARIC_WSDL_URL = "https://ec.europa.eu/taxation_customs/dds2/taric/services/goods?wsdl"
    TARIC_SERVICE_URL = "https://ec.europa.eu/taxation_customs/dds2/taric/services/goods"
    
    def get_required_documents(self, goods_code, country_code="ES", reference_date=None, trade_movement=None, direction=None):
        """
        Consulta los documentos requeridos para una partida arancelaria usando la API TARIC.
        
        :param goods_code: Código de la partida arancelaria (8-10 dígitos)
        :param country_code: Código del país destino (AD para Andorra, ES para España)
        :param reference_date: Fecha de referencia en formato YYYY-MM-DD (opcional, por defecto hoy)
        :param trade_movement: Movimiento comercial - "E" para exportación, "I" para importación (opcional)
        :param direction: Dirección del expediente ("export" o "import") - se usa para determinar trade_movement si no se proporciona
        :return: Lista de diccionarios con información de documentos requeridos
        """
        try:
            try:
                from zeep import Client
                from zeep.exceptions import Fault
            except ImportError:
                _logger.warning("zeep no está instalado. Instala con: pip install zeep")
                return []
            
            if not goods_code or len(str(goods_code).strip()) < 8:
                _logger.warning("Código de partida arancelaria inválido: %s", goods_code)
                return []
            
            # Limpiar código (solo números)
            goods_code = ''.join(filter(str.isdigit, str(goods_code)))[:10]
            if len(goods_code) < 8:
                _logger.warning("Código de partida arancelaria debe tener al menos 8 dígitos: %s", goods_code)
                return []
            
            # Determinar trade_movement si no se proporciona
            if not trade_movement and direction:
                # E = Exportación (España → Andorra), I = Importación (Andorra → España)
                trade_movement = "E" if direction == "export" else "I"
            elif not trade_movement:
                # Por defecto, si no hay dirección, usar E (exportación)
                trade_movement = "E"
            
            # Determinar country_code según dirección si no se proporciona
            if not country_code and direction:
                # Para exportación (ES → AD), country_code es AD (destino)
                # Para importación (AD → ES), country_code es ES (destino)
                country_code = "AD" if direction == "export" else "ES"
            
            # Fecha de referencia por defecto (hoy)
            if not reference_date:
                from datetime import date
                reference_date = date.today().strftime("%Y-%m-%d")
            
            _logger.info("Consultando TARIC para código: %s, país: %s, trade_movement: %s, fecha: %s", 
                        goods_code, country_code, trade_movement, reference_date)
            
            # Usar requests directamente (método que funciona en Postman)
            # El WSDL puede dar 502, pero el endpoint del servicio funciona
            try:
                return self._call_taric_with_requests(goods_code, country_code, reference_date, trade_movement)
            except Exception as e:
                error_msg = str(e)
                _logger.warning("Error con método requests: %s", e)
                # Si es un error de conexión, intentar con zeep como fallback
                if '502' not in error_msg and 'Bad Gateway' not in error_msg:
                    try:
                        _logger.info("Intentando con zeep como fallback...")
                        return self._call_taric_with_zeep(goods_code, country_code, reference_date, trade_movement)
                    except Exception as e2:
                        _logger.error("Ambos métodos fallaron. TARIC no está disponible.")
                        return []
                else:
                    _logger.error("Servidor TARIC no disponible (502). Los usuarios pueden añadir documentos manualmente.")
                    return []
        
        except Exception as e:
            _logger.exception("Error general consultando TARIC: %s", e)
            return []
    
    def _call_taric_with_requests(self, goods_code, country_code, reference_date, trade_movement):
        """Llama a TARIC usando requests exactamente igual que Postman."""
        import requests
        import time

        payload = f"""
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:tar="http://goodsNomenclatureForWS.ws.taric.dds.s/">
   <soapenv:Header/>
   <soapenv:Body>
      <tar:goodsMeasForWs>
         <tar:goodsCode>{goods_code}</tar:goodsCode>
         <tar:countryCode>{country_code}</tar:countryCode>
         <tar:referenceDate>{reference_date}</tar:referenceDate>
         <tar:tradeMovement>{trade_movement}</tar:tradeMovement>
      </tar:goodsMeasForWs>
   </soapenv:Body>
</soapenv:Envelope>
""".strip()

        headers = {
            "Content-Type": "text/xml;charset=UTF-8",
            "SOAPAction": "",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        # Logging del request
        _logger.info("=== REQUEST TARIC ===")
        _logger.info("URL: %s", self.TARIC_SERVICE_URL)
        _logger.info("Headers: %s", headers)
        _logger.info("Payload: %s", payload)
        _logger.info("==============================")

        # TARIC NO soporta paralelismo → solo 1 request/segundo
        time.sleep(1.2)

        # 5 retries con backoff exponencial
        for attempt in range(5):
            try:
                response = requests.post(
                    self.TARIC_SERVICE_URL,
                    headers=headers,
                    data=payload.encode("utf-8"),
                    timeout=30
                )

                _logger.info("TARIC respuesta (intento %s): Status %s", attempt + 1, response.status_code)

                if response.status_code == 200:
                    _logger.info("TARIC consulta exitosa para código %s", goods_code)
                    return self._parse_xml_response(response.text, goods_code)

                if response.status_code in (429, 502, 503):
                    _logger.warning("TARIC temporalmente no disponible (%s). Reintentando…", response.status_code)
                    time.sleep(2 ** attempt)
                    continue

                raise Exception(f"HTTP {response.status_code}: {response.text[:300]}")

            except Exception as e:
                _logger.warning("Error TARIC intento %s: %s", attempt + 1, e)
                if attempt < 4:  # No esperar después del último intento
                    time.sleep(2 ** attempt)

        raise Exception("TARIC no disponible tras múltiples intentos")
    
    def _parse_xml_response(self, xml_text, goods_code):
        """Parsea la respuesta XML de TARIC"""
        documents = []
        try:
            import xml.etree.ElementTree as ET
            
            _logger.debug("Parseando respuesta XML TARIC (primeros 1000 chars): %s", xml_text[:1000])
            
            # Parsear XML
            root = ET.fromstring(xml_text)
            
            # Namespaces que pueden aparecer en la respuesta
            # La respuesta puede usar diferentes prefijos (S, soapenv, ns0, etc.)
            namespaces = {
                'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
                'S': 'http://schemas.xmlsoap.org/soap/envelope/',
                'tar': 'http://goodsNomenclatureForWS.ws.taric.dds.s/',
                'ns0': 'http://goodsNomenclatureForWS.ws.taric.dds.s/'
            }
            
            # Buscar el body de la respuesta (puede usar diferentes prefijos)
            body = None
            for ns_prefix in ['soapenv', 'S']:
                if ns_prefix in namespaces:
                    body = root.find(f'.//{{{namespaces[ns_prefix]}}}Body')
                    if body is not None:
                        break
            
            if body is None:
                # Intentar sin namespace
                body = root.find('.//Body') or root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Body')
            
            if body is None:
                _logger.warning("No se encontró Body en respuesta SOAP")
                _logger.debug("XML completo: %s", xml_text[:2000])
                return documents
            
            # Buscar la respuesta goodsMeasForWsResponse (puede usar ns0 o tar)
            response_elem = None
            taric_ns = 'http://goodsNomenclatureForWS.ws.taric.dds.s/'
            
            # Buscar con diferentes prefijos
            for prefix in ['ns0', 'tar']:
                if prefix in namespaces:
                    response_elem = body.find(f'.//{{{taric_ns}}}goodsMeasForWsResponse')
                    if response_elem is not None:
                        break
            
            # Si no se encuentra, buscar sin prefijo
            if response_elem is None:
                response_elem = body.find(f'.//{{{taric_ns}}}goodsMeasForWsResponse')
            
            if response_elem is None:
                _logger.warning("No se encontró goodsMeasForWsResponse en respuesta")
                _logger.debug("Body encontrado: %s", ET.tostring(body, encoding='unicode')[:500])
                return documents
            
            # Buscar el elemento return (sin prefijo, está en el namespace por defecto del padre)
            return_elem = response_elem.find('.//return') or response_elem.find(f'.//{{{taric_ns}}}return')
            
            if return_elem is None:
                _logger.warning("No se encontró return en respuesta")
                _logger.debug("Response elem: %s", ET.tostring(response_elem, encoding='unicode')[:500])
                return documents
            
            # Buscar result > measures > measure
            result_elem = return_elem.find('.//result')
            if result_elem is None:
                _logger.warning("No se encontró result en return")
                return documents
            
            measures_elem = result_elem.find('.//measures')
            if measures_elem is None:
                _logger.warning("No se encontró measures en result")
                return documents
            
            # Buscar todas las medidas
            measures = measures_elem.findall('.//measure')
            
            if measures:
                _logger.debug("Encontradas %d medidas en respuesta", len(measures))
                for measure in measures:
                    doc_info = self._extract_document_from_measure(measure, goods_code)
                    if doc_info:
                        documents.append(doc_info)
            else:
                _logger.warning("No se encontraron medidas dentro de measures")
            
        except ET.ParseError as e:
            _logger.error("Error parseando XML de TARIC: %s", e)
            _logger.debug("XML que causó error: %s", xml_text[:2000])
        except Exception as e:
            _logger.exception("Error parseando respuesta XML: %s", e)
        
        _logger.info("Parseados %d documentos de respuesta XML", len(documents))
        return documents
    
    def _extract_document_from_xml(self, elem, goods_code, namespaces):
        """Extrae información de documento de un elemento XML"""
        try:
            doc_code = None
            doc_name = None
            is_mandatory = True
            
            # Buscar código de documento
            code_elem = elem.find('.//tar:documentCode', namespaces) or elem.find('.//documentCode', namespaces)
            if code_elem is not None and code_elem.text:
                doc_code = code_elem.text.strip()
            
            # Buscar descripción/nombre
            desc_elem = elem.find('.//tar:description', namespaces) or elem.find('.//description', namespaces)
            if desc_elem is not None and desc_elem.text:
                doc_name = desc_elem.text.strip()
            
            # Buscar si es obligatorio
            mandatory_elem = elem.find('.//tar:mandatory', namespaces) or elem.find('.//mandatory', namespaces)
            if mandatory_elem is not None and mandatory_elem.text:
                is_mandatory = mandatory_elem.text.strip().lower() in ('true', '1', 'yes')
            
            # También buscar en atributos
            if not doc_code:
                doc_code = elem.get('code') or elem.get('documentCode')
            if not doc_name:
                doc_name = elem.get('name') or elem.get('description')
            
            if doc_code or doc_name:
                return {
                    'code': doc_code or goods_code,
                    'name': doc_name or _("Documento requerido para partida %s") % goods_code,
                    'mandatory': is_mandatory,
                    'description': doc_name or '',
                }
        except Exception as e:
            _logger.warning("Error extrayendo documento de XML: %s", e)
        
        return None
    
    def _extract_document_from_measure(self, measure_elem, goods_code):
        """Extrae información de documento requerido de un elemento measure"""
        try:
            from odoo import _
            import html
            
            # Extraer información del measure_type
            measure_type_elem = measure_elem.find('.//measure_type')
            measure_type_code = None
            measure_type_desc = None
            
            if measure_type_elem is not None:
                code_elem = measure_type_elem.find('.//measure_type')
                if code_elem is not None and code_elem.text:
                    measure_type_code = code_elem.text.strip()
                
                desc_elem = measure_type_elem.find('.//description')
                if desc_elem is not None and desc_elem.text:
                    measure_type_desc = desc_elem.text.strip()
            
            # Extraer regulation_id
            regulation_elem = measure_elem.find('.//regulation_id')
            regulation_id = regulation_elem.text.strip() if regulation_elem is not None and regulation_elem.text else None
            
            # Extraer footnotes (descripciones detalladas)
            footnotes = []
            footnotes_elem = measure_elem.find('.//footnotes')
            if footnotes_elem is not None:
                for footnote in footnotes_elem.findall('.//footnote'):
                    desc_elem = footnote.find('.//description')
                    if desc_elem is not None and desc_elem.text:
                        # Decodificar entidades HTML
                        footnote_text = html.unescape(desc_elem.text.strip())
                        footnotes.append(footnote_text)
            
            # Construir nombre del documento
            doc_name_parts = []
            if measure_type_desc:
                doc_name_parts.append(measure_type_desc)
            if regulation_id:
                doc_name_parts.append(f"({regulation_id})")
            
            doc_name = " - ".join(doc_name_parts) if doc_name_parts else _("Medida TARIC para partida %s") % goods_code
            
            # Construir descripción completa (incluyendo footnotes)
            description_parts = [doc_name]
            if footnotes:
                description_parts.append("\n\n" + "\n\n".join(footnotes))
            
            full_description = "".join(description_parts)
            
            # El código del documento será el measure_type_code o regulation_id
            doc_code = measure_type_code or regulation_id or f"MEASURE_{goods_code}"
            
            # Las medidas de TARIC generalmente son obligatorias
            is_mandatory = True
            
            return {
                'code': doc_code,
                'name': doc_name,
                'mandatory': is_mandatory,
                'description': full_description,
            }
            
        except Exception as e:
            _logger.exception("Error extrayendo documento de measure: %s", e)
            return None
    
    def _call_taric_with_zeep(self, goods_code, country_code, reference_date, trade_movement):
        """
        Llama a TARIC usando zeep (método oficial y estable según documentación TARIC)
        Configuración según ejemplo oficial de la UE
        """
        try:
            from zeep import Client
            from zeep.transports import Transport
            from requests import Session
            from requests.exceptions import HTTPError
            
            # Configurar sesión según método oficial
            session = Session()
            session.verify = True  # Verificar certificados SSL
            
            # Crear transporte con la sesión
            transport = Transport(session=session)
            
            # Crear cliente con WSDL (método oficial)
            _logger.debug("Creando cliente zeep con WSDL: %s", self.TARIC_WSDL_URL)
            try:
                client = Client(self.TARIC_WSDL_URL, transport=transport)
            except HTTPError as e:
                if e.response and e.response.status_code == 502:
                    _logger.error("Servidor TARIC no disponible (502 Bad Gateway) al cargar WSDL")
                    _logger.error("El servicio TARIC está temporalmente no disponible. Intenta más tarde o añade documentos manualmente.")
                    raise Exception("Servidor TARIC no disponible (502 Bad Gateway). El servicio puede estar en mantenimiento.")
                raise
            
            _logger.debug("Cliente SOAP TARIC (zeep) creado correctamente")
            
            # Preparar parámetros según el WSDL
            params = {
                'goodsCode': goods_code,
                'countryCode': country_code,
                'referenceDate': reference_date,
                'tradeMovement': trade_movement,
            }
            
            _logger.debug("Parámetros TARIC: %s", params)
            
            # Llamar al servicio goodsMeasForWs (método oficial)
            _logger.info("Llamando a goodsMeasForWs con parámetros: %s", params)
            response = client.service.goodsMeasForWs(**params)
            
            _logger.debug("Tipo de respuesta TARIC: %s", type(response))
            _logger.debug("Respuesta TARIC recibida")
            
            if not response:
                _logger.warning("TARIC no devolvió respuesta para código %s", goods_code)
                return []
            
            # Inspeccionar estructura de la respuesta para debug
            if hasattr(response, '__dict__'):
                _logger.debug("Atributos de respuesta: %s", list(response.__dict__.keys()))
            
            # Procesar respuesta y extraer documentos requeridos
            documents = self._parse_taric_response(response, goods_code)
            _logger.info("TARIC devolvió %d documentos para código %s", len(documents), goods_code)
            return documents
            
        except ImportError as e:
            _logger.error("Error de importación (zeep no está instalado): %s", e)
            _logger.error("Instala zeep con: pip install zeep")
            return []
        except HTTPError as e:
            if e.response and e.response.status_code == 502:
                _logger.error("Servidor TARIC no disponible (502 Bad Gateway)")
                _logger.error("El servicio TARIC está temporalmente no disponible. Los usuarios pueden añadir documentos manualmente.")
            else:
                _logger.error("Error HTTP en TARIC: %s", e)
            return []
        except Exception as e:
            error_msg = str(e)
            if '502' in error_msg or 'Bad Gateway' in error_msg:
                _logger.error("Servidor TARIC no disponible (502 Bad Gateway)")
                _logger.error("El servicio TARIC está temporalmente no disponible. Los usuarios pueden añadir documentos manualmente.")
            else:
                _logger.exception("Error consultando TARIC con zeep: %s", e)
            return []
                
        except ImportError:
            _logger.warning("zeep no está disponible. No se puede consultar TARIC.")
            return []
        except Exception as e:
            _logger.exception("Error general consultando TARIC: %s", e)
            return []
    
    def _parse_taric_response(self, response, goods_code):
        """
        Parsea la respuesta de TARIC y extrae información de documentos requeridos.
        
        :param response: Respuesta del servicio TARIC
        :param goods_code: Código de la partida arancelaria
        :return: Lista de diccionarios con documentos requeridos
        """
        documents = []
        
        try:
            _logger.debug("Parseando respuesta TARIC. Tipo: %s", type(response))
            
            # La respuesta de TARIC puede tener diferentes estructuras
            # Según el WSDL, goodsMeasuresForWsResult puede tener diferentes campos
            
            # Opción 1: Respuesta tiene atributo 'return' (estructura estándar SOAP)
            if hasattr(response, 'return'):
                return_data = getattr(response, 'return')
                if return_data:
                    _logger.debug("Respuesta tiene atributo 'return'")
                    documents = self._parse_taric_response(return_data, goods_code)
                    return documents
            
            # Opción 2: Respuesta tiene 'measures' o lista de medidas
            if hasattr(response, 'measures'):
                _logger.debug("Respuesta tiene atributo 'measures'")
                measures = response.measures
                if measures:
                    if not isinstance(measures, list):
                        measures = [measures]
                    
                    _logger.debug("Procesando %d medidas", len(measures))
                    for idx, measure in enumerate(measures):
                        _logger.debug("Procesando medida %d: %s", idx, type(measure))
                        doc_info = self._extract_document_info(measure, goods_code)
                        if doc_info:
                            documents.append(doc_info)
                            _logger.debug("Documento extraído: %s", doc_info)
            
            # Opción 3: Respuesta tiene 'documentRequirements'
            elif hasattr(response, 'documentRequirements') and response.documentRequirements:
                _logger.debug("Respuesta tiene atributo 'documentRequirements'")
                reqs = response.documentRequirements
                if not isinstance(reqs, list):
                    reqs = [reqs]
                
                for req in reqs:
                    doc_info = self._extract_document_info_from_requirement(req, goods_code)
                    if doc_info:
                        documents.append(doc_info)
            
            # Opción 4: Respuesta es un diccionario
            elif isinstance(response, dict):
                _logger.debug("Respuesta es un diccionario")
                documents = self._parse_dict_response(response, goods_code)
            
            # Opción 5: Respuesta es una lista
            elif isinstance(response, list):
                _logger.debug("Respuesta es una lista con %d elementos", len(response))
                for item in response:
                    doc_info = self._extract_document_info(item, goods_code)
                    if doc_info:
                        documents.append(doc_info)
            
            # Opción 6: Intentar acceder directamente a atributos comunes
            else:
                _logger.debug("Intentando acceder a atributos directos de la respuesta")
                # Intentar convertir a dict si es posible
                try:
                    if hasattr(response, '__dict__'):
                        response_dict = response.__dict__
                        _logger.debug("Atributos disponibles: %s", list(response_dict.keys()))
                        documents = self._parse_dict_response(response_dict, goods_code)
                except Exception as e:
                    _logger.warning("No se pudo convertir respuesta a dict: %s", e)
            
        except Exception as e:
            _logger.exception("Error parseando respuesta TARIC: %s", e)
            _logger.debug("Respuesta que causó error: %s", response)
        
        # Si no se encontraron documentos, loguear para debug
        if not documents:
            _logger.info("No se encontraron documentos específicos en TARIC para código %s. Estructura de respuesta: %s", goods_code, type(response))
            if hasattr(response, '__dict__'):
                _logger.debug("Atributos de respuesta vacía: %s", list(response.__dict__.keys()))
        
        return documents
    
    def _extract_document_info(self, measure, goods_code):
        """Extrae información de documento de una medida TARIC."""
        try:
            doc_code = None
            doc_name = None
            is_mandatory = True  # Por defecto asumimos obligatorio
            
            # Intentar extraer código de documento
            if hasattr(measure, 'documentCode'):
                doc_code = str(measure.documentCode)
            elif hasattr(measure, 'code'):
                doc_code = str(measure.code)
            
            # Intentar extraer nombre/descripción
            if hasattr(measure, 'description'):
                doc_name = str(measure.description)
            elif hasattr(measure, 'name'):
                doc_name = str(measure.name)
            
            # Intentar determinar si es obligatorio
            if hasattr(measure, 'mandatory'):
                is_mandatory = bool(measure.mandatory)
            elif hasattr(measure, 'required'):
                is_mandatory = bool(measure.required)
            
            if doc_code or doc_name:
                return {
                    'code': doc_code or goods_code,
                    'name': doc_name or _("Documento requerido para partida %s") % goods_code,
                    'mandatory': is_mandatory,
                    'description': doc_name or '',
                }
        except Exception as e:
            _logger.warning("Error extrayendo información de medida: %s", e)
        
        return None
    
    def _extract_document_info_from_requirement(self, req, goods_code):
        """Extrae información de documento de un requerimiento TARIC."""
        try:
            doc_code = getattr(req, 'documentCode', None) or getattr(req, 'code', None)
            doc_name = getattr(req, 'description', None) or getattr(req, 'name', None)
            is_mandatory = getattr(req, 'mandatory', True)
            
            if doc_code or doc_name:
                return {
                    'code': str(doc_code) if doc_code else goods_code,
                    'name': str(doc_name) if doc_name else _("Documento requerido para partida %s") % goods_code,
                    'mandatory': bool(is_mandatory),
                    'description': str(doc_name) if doc_name else '',
                }
        except Exception as e:
            _logger.warning("Error extrayendo información de requerimiento: %s", e)
        
        return None
    
    def _parse_dict_response(self, response_dict, goods_code):
        """Parsea una respuesta en formato diccionario."""
        documents = []
        try:
            # Buscar diferentes estructuras posibles
            if 'measures' in response_dict:
                for measure in response_dict['measures']:
                    doc_info = self._extract_document_info(measure, goods_code)
                    if doc_info:
                        documents.append(doc_info)
            elif 'documentRequirements' in response_dict:
                for req in response_dict['documentRequirements']:
                    doc_info = self._extract_document_info_from_requirement(req, goods_code)
                    if doc_info:
                        documents.append(doc_info)
        except Exception as e:
            _logger.warning("Error parseando respuesta dict: %s", e)
        
        return documents
    
    def test_connection(self, goods_code="12345678", country_code="ES"):
        """
        Método de prueba para verificar la conexión con TARIC.
        Útil para debugging y verificar la estructura de la respuesta.
        
        :param goods_code: Código de prueba (por defecto 12345678)
        :param country_code: Código del país
        :return: Diccionario con información de la prueba
        """
        result = {
            'success': False,
            'error': None,
            'response_structure': None,
            'documents_found': 0,
        }
        
        try:
            try:
                from zeep import Client
                from zeep.exceptions import Fault
            except ImportError:
                result['error'] = "zeep no está instalado"
                return result
            
            _logger.info("=== PRUEBA DE CONEXIÓN TARIC ===")
            _logger.info("Código: %s, País: %s", goods_code, country_code)
            
            # Limpiar código
            goods_code = ''.join(filter(str.isdigit, str(goods_code)))[:10]
            if len(goods_code) < 8:
                result['error'] = "Código debe tener al menos 8 dígitos"
                return result
            
            # Crear cliente
            client = Client(self.TARIC_WSDL_URL)
            _logger.info("Cliente SOAP creado correctamente")
            
            # Probar goodsDescrForWs primero (más simple)
            try:
                _logger.info("Probando goodsDescrForWs...")
                desc_response = client.service.goodsDescrForWs(
                    goodsCode=goods_code,
                    languageCode="ES"
                )
                _logger.info("goodsDescrForWs respuesta: %s", desc_response)
                result['description_response'] = str(desc_response)[:500]  # Limitar tamaño
            except Exception as e:
                _logger.warning("Error en goodsDescrForWs: %s", e)
                result['description_error'] = str(e)
            
            # Probar goodsMeasForWs
            try:
                _logger.info("Probando goodsMeasForWs...")
                params = {
                    'goodsCode': goods_code,
                    'countryCode': country_code,
                }
                
                response = client.service.goodsMeasForWs(**params)
                _logger.info("goodsMeasForWs respuesta recibida")
                
                # Inspeccionar estructura
                result['response_type'] = str(type(response))
                if hasattr(response, '__dict__'):
                    result['response_attributes'] = list(response.__dict__.keys())
                    result['response_dict'] = {k: str(v)[:200] for k, v in response.__dict__.items()}
                
                # Intentar parsear
                documents = self._parse_taric_response(response, goods_code)
                result['documents_found'] = len(documents)
                result['documents'] = documents
                result['success'] = True
                
            except Fault as e:
                _logger.error("Fault SOAP en goodsMeasForWs: %s", e)
                result['error'] = f"Fault SOAP: {str(e)}"
            except Exception as e:
                _logger.exception("Error en goodsMeasForWs: %s", e)
                result['error'] = str(e)
                result['error_type'] = type(e).__name__
            
        except Exception as e:
            _logger.exception("Error general en prueba de conexión: %s", e)
            result['error'] = str(e)
        
        _logger.info("=== FIN PRUEBA TARIC ===")
        return result

