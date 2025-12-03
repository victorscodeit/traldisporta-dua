import logging
import base64
import json
import re
import io
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class InvoiceOCRService(models.AbstractModel):
    _name = "aduanas.invoice.ocr.service"
    _description = "Servicio OCR/IA para procesar facturas PDF"

    def extract_invoice_data(self, pdf_data, api_key=None):
        """
        Extrae datos de una factura PDF usando Google Vision API o OCR alternativo.
        
        :param pdf_data: Datos binarios del PDF (base64 o bytes)
        :param api_key: API key de Google Vision (opcional, se obtiene de configuración si no se proporciona)
        :return: Diccionario con datos extraídos (incluye campo 'error' si hay problemas)
        """
        if not pdf_data:
            return {
                "error": _("No se proporcionó ningún archivo PDF"),
                "texto_extraido": ""
            }
        
        # Validar que el PDF no esté vacío o corrupto
        try:
            # En Odoo, los campos Binary pueden venir como string base64 o ya decodificados
            if isinstance(pdf_data, str):
                try:
                    # Intentar decodificar base64
                    pdf_bytes = base64.b64decode(pdf_data)
                    # Verificar si después de decodificar sigue siendo base64 (doble encoding)
                    # Los PDFs válidos empiezan con %PDF, pero si está doblemente codificado,
                    # después de la primera decodificación tendremos algo que empieza con JVBERi...
                    if isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 0:
                        # Verificar si los primeros bytes son base64 válido (empiezan con JVBER)
                        try:
                            first_chars = pdf_bytes[:10].decode('utf-8', errors='ignore')
                            # JVBERi es el inicio de un PDF cuando está codificado en base64
                            if first_chars.startswith('JVBER') or first_chars.startswith('JVBERi'):
                                # Es base64 doblemente codificado, decodificar de nuevo
                                _logger.info("Detectado doble encoding base64 (empieza con %s), decodificando de nuevo...", first_chars[:10])
                                pdf_bytes = base64.b64decode(pdf_bytes)
                                _logger.info("Doble decodificación exitosa. Primeros bytes ahora: %s", pdf_bytes[:20].hex() if len(pdf_bytes) >= 20 else pdf_bytes.hex())
                        except Exception as double_decode_error:
                            _logger.debug("No es doble encoding o error al verificar: %s", double_decode_error)
                            # Continuar con pdf_bytes tal cual
                except Exception as decode_error:
                    _logger.error("Error al decodificar base64: %s. Primeros 100 caracteres: %s", decode_error, pdf_data[:100] if pdf_data else "None")
                    return {
                        "error": _("Error al decodificar el archivo PDF. El formato puede ser incorrecto."),
                        "texto_extraido": "",
                        "metodo_usado": "Error de validación"
                    }
            else:
                pdf_bytes = pdf_data
            
            # Validar que no esté vacío
            if not pdf_bytes or len(pdf_bytes) < 4:
                _logger.warning("PDF vacío o muy pequeño. Tamaño: %d bytes", len(pdf_bytes) if pdf_bytes else 0)
                return {
                    "error": _("El archivo PDF está vacío o es demasiado pequeño."),
                    "texto_extraido": "",
                    "metodo_usado": "Error de validación"
                }
            
            # Validar que es un PDF válido (debe empezar con %PDF)
            # Algunos PDFs pueden tener espacios en blanco al inicio, así que los eliminamos
            pdf_start = pdf_bytes[:10].strip()
            pdf_valid = False
            pdf_offset = 0
            
            # Verificar si empieza directamente con %PDF
            if pdf_bytes[:4] == b'%PDF':
                pdf_valid = True
                _logger.info("PDF válido: empieza directamente con %%PDF")
            else:
                # Intentar buscar %PDF en los primeros 2048 bytes (algunos PDFs tienen headers adicionales)
                search_range = min(2048, len(pdf_bytes) - 4)
                for i in range(search_range):
                    if pdf_bytes[i:i+4] == b'%PDF':
                        pdf_valid = True
                        pdf_offset = i
                        _logger.info("PDF válido encontrado en posición %d (después de %d bytes de header)", i, i)
                        # Si hay offset, recortar el header
                        if i > 0:
                            pdf_bytes = pdf_bytes[i:]
                        break
                
                # Si aún no se encuentra, intentar buscar en todo el archivo (más lento pero más permisivo)
                if not pdf_valid and len(pdf_bytes) > 4:
                    _logger.warning("No se encontró %%PDF en los primeros %d bytes. Buscando en todo el archivo...", search_range)
                    # Buscar en bloques más grandes
                    for i in range(0, min(len(pdf_bytes) - 4, 10000), 100):  # Buscar cada 100 bytes hasta 10KB
                        if pdf_bytes[i:i+4] == b'%PDF':
                            pdf_valid = True
                            pdf_offset = i
                            _logger.info("PDF válido encontrado en posición %d después de búsqueda extendida", i)
                            if i > 0:
                                pdf_bytes = pdf_bytes[i:]
                            break
            
            if not pdf_valid:
                # Log detallado para diagnóstico
                _logger.error("PDF no válido detectado. Tamaño: %d bytes", len(pdf_bytes))
                _logger.error("Primeros 100 bytes (hex): %s", pdf_bytes[:100].hex() if len(pdf_bytes) >= 100 else pdf_bytes.hex())
                _logger.error("Primeros 100 bytes (repr): %s", repr(pdf_bytes[:100]) if len(pdf_bytes) >= 100 else repr(pdf_bytes))
                # Intentar procesar de todas formas si el tamaño es razonable (puede ser un PDF con formato no estándar)
                if len(pdf_bytes) > 100:  # Si tiene un tamaño razonable, intentar procesarlo de todas formas
                    _logger.warning("Archivo no tiene header %%PDF estándar pero tiene tamaño razonable (%d bytes). Intentando procesar de todas formas...", len(pdf_bytes))
                    # No retornar error, continuar con el procesamiento
                else:
                    return {
                        "error": _("El archivo no parece ser un PDF válido. Verifica que el archivo esté correcto.\n\nSi es una imagen escaneada, asegúrate de que esté en formato PDF, no JPG/PNG."),
                        "texto_extraido": "",
                        "metodo_usado": "Error de validación"
                    }
        except Exception as e:
            _logger.exception("Error al procesar el archivo PDF: %s", e)
            return {
                "error": _("Error al procesar el archivo PDF: %s\n\nVerifica que el archivo no esté corrupto.") % str(e),
                "texto_extraido": "",
                "metodo_usado": "Error de validación"
            }
        
        # Guardar pdf_bytes para usar en los métodos de extracción
        # (necesitamos pasar tanto pdf_data original como pdf_bytes procesado)
        pdf_data_for_methods = pdf_data if isinstance(pdf_data, str) else base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Obtener API key de configuración si no se proporciona
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('aduanas_transport.google_vision_api_key')
        
        resultado = None
        metodo_usado = None
        
        if api_key:
            try:
                # Pasar pdf_data original (base64) para que pueda ser usado en fallbacks
                resultado = self._extract_with_google_vision(api_key, pdf_data_for_methods)
                metodo_usado = "Google Vision"
            except Exception as e:
                _logger.warning("Error con Google Vision, intentando OCR alternativo: %s", e)
                try:
                    resultado = self._extract_with_fallback_ocr(pdf_data)
                    metodo_usado = "OCR Alternativo (fallback)"
                except Exception as e2:
                    _logger.exception("Error también con OCR alternativo: %s", e2)
                    return {
                        "error": _("Error al procesar PDF con ambos métodos:\n- Google Vision: %s\n- OCR Alternativo: %s") % (str(e), str(e2)),
                        "texto_extraido": "",
                        "metodo_usado": "Error en ambos"
                    }
        else:
            # Usar OCR alternativo si no hay API key
            try:
                resultado = self._extract_with_fallback_ocr(pdf_data)
                metodo_usado = "OCR Alternativo (pdfplumber/PyPDF2)"
            except Exception as e:
                _logger.exception("Error con OCR alternativo: %s", e)
                return {
                    "error": _("Error al procesar PDF: %s\n\nPosibles soluciones:\n- Verifica que el PDF no esté corrupto\n- Si es una imagen escaneada, configura Google Vision API\n- Instala pdfplumber: pip install pdfplumber") % str(e),
                    "texto_extraido": "",
                    "metodo_usado": "Error"
                }
        
        # Agregar información del método usado
        if resultado:
            resultado["metodo_usado"] = metodo_usado
            
            # Validar que se extrajo texto
            if not resultado.get("texto_extraido") or len(resultado.get("texto_extraido", "").strip()) < 10:
                if not resultado.get("error"):
                    resultado["error"] = _("No se pudo extraer texto del PDF. Posibles causas:\n- El PDF es una imagen escaneada (necesitas Google Vision API)\n- El PDF está protegido o encriptado\n- El PDF está corrupto\n- La calidad del escaneado es muy baja")
        
        return resultado

    def _extract_with_google_vision(self, api_key_or_path, pdf_data):
        """
        Extrae datos usando Google Cloud Vision API.
        Requiere: pip install google-cloud-vision
        
        La configuración puede ser:
        1. Ruta a un archivo JSON de Service Account (ej: /path/to/credentials.json)
        2. Contenido JSON de Service Account como texto
        3. API Key directa de Google Cloud (ej: AIzaSy...)
        
        Para API keys directas, se usa la API REST de Google Vision.
        Para Service Account JSON, se usa el cliente de Python.
        
        :param api_key_or_path: API key o ruta a archivo JSON
        :param pdf_data: Datos binarios del PDF (base64 o bytes)
        """
        import os
        import json
        import requests
        
        if not pdf_data:
            raise ValueError("pdf_data no puede estar vacío")
        
        # Convertir base64 a bytes si es necesario
        if isinstance(pdf_data, str):
            pdf_bytes = base64.b64decode(pdf_data)
        else:
            pdf_bytes = pdf_data
        
        # Determinar el tipo de credencial
        api_key = None
        is_service_account = False
        
        if not api_key_or_path:
            raise ValueError("No se proporcionó API key ni archivo de credenciales")
        
        # Verificar si es una ruta a archivo JSON
        if os.path.exists(api_key_or_path) and api_key_or_path.endswith('.json'):
            # Es un archivo de Service Account JSON
            is_service_account = True
            try:
                from google.cloud import vision
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(api_key_or_path)
                client = vision.ImageAnnotatorClient(credentials=credentials)
                _logger.info("Usando Google Vision con Service Account JSON")
                return self._extract_with_vision_client(client, pdf_bytes, pdf_data)
            except Exception as cred_error:
                _logger.warning("Error con Service Account JSON: %s. Intentando como API key.", cred_error)
                # Intentar como API key si falla
                is_service_account = False
        
        # Verificar si es un JSON string
        if api_key_or_path.startswith('{') or api_key_or_path.startswith('['):
            try:
                creds_dict = json.loads(api_key_or_path)
                # Si tiene 'type' y es 'service_account', es Service Account
                if creds_dict.get('type') == 'service_account':
                    is_service_account = True
                    from google.cloud import vision
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_info(creds_dict)
                    client = vision.ImageAnnotatorClient(credentials=credentials)
                    _logger.info("Usando Google Vision con Service Account JSON (string)")
                    return self._extract_with_vision_client(client, pdf_bytes, pdf_data)
                else:
                    # Intentar extraer API key del JSON
                    api_key = creds_dict.get('api_key') or creds_dict.get('key')
            except json.JSONDecodeError:
                # No es JSON válido, tratar como API key
                api_key = api_key_or_path
        
        # Si no es Service Account, usar como API key directa
        if not is_service_account:
            api_key = api_key or api_key_or_path
            
            # Validar formato de API key (empieza con AIza)
            if not api_key.startswith('AIza'):
                _logger.warning("La API key no tiene el formato esperado (debe empezar con AIza). Intentando de todas formas...")
            
            # Usar API REST de Google Vision con API key
            _logger.info("Usando Google Vision con API key directa (REST API)")
            # Guardar pdf_data original para posibles fallbacks
            pdf_data_original = pdf_data if isinstance(pdf_data, str) else base64.b64encode(pdf_data).decode('utf-8')
            return self._extract_with_rest_api(api_key, pdf_bytes, pdf_data_original)
        
        # Si llegamos aquí y no hay client, intentar sin credenciales explícitas
        try:
            from google.cloud import vision
            client = vision.ImageAnnotatorClient()
            return self._extract_with_vision_client(client, pdf_bytes, pdf_data)
        except Exception as cred_error:
            _logger.warning("Error al inicializar Google Vision client: %s", cred_error)
            # Re-lanzar para que el método padre maneje el fallback
            raise
    
    def _extract_with_rest_api(self, api_key, pdf_bytes):
        """
        Extrae texto usando la API REST de Google Vision con API key directa.
        """
        import requests
        
        # Convertir PDF a base64 para la API REST
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # URL de la API REST de Google Vision
        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        
        # Preparar la petición
        payload = {
            "requests": [{
                "image": {
                    "content": pdf_base64
                },
                "features": [{
                    "type": "DOCUMENT_TEXT_DETECTION",
                    "maxResults": 1
                }]
            }]
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Extraer texto de la respuesta
            full_text = ""
            if "responses" in result and len(result["responses"]) > 0:
                if "fullTextAnnotation" in result["responses"][0]:
                    full_text = result["responses"][0]["fullTextAnnotation"].get("text", "")
                elif "textAnnotations" in result["responses"][0] and len(result["responses"][0]["textAnnotations"]) > 0:
                    # Fallback: usar primera anotación de texto
                    full_text = result["responses"][0]["textAnnotations"][0].get("description", "")
            
            if not full_text:
                _logger.warning("Google Vision REST API no extrajo texto. Usando OCR alternativo.")
                # Necesitamos pasar pdf_data original, no pdf_bytes
                # Recuperar desde el contexto de llamada
                raise Exception(_("Google Vision no extrajo texto. Se intentará con OCR alternativo."))
            
            # Parsear datos de la factura
            return self._parse_invoice_text(full_text)
            
        except requests.exceptions.RequestException as e:
            _logger.exception("Error en petición REST a Google Vision: %s", e)
            raise Exception(_("Error al conectar con Google Vision API: %s") % str(e))
        except Exception as e:
            _logger.exception("Error procesando respuesta de Google Vision: %s", e)
            raise
    
    def _extract_with_vision_client(self, client, pdf_bytes, pdf_data_original=None):
        """
        Extrae texto usando el cliente de Python de Google Vision (para Service Account).
        
        :param client: Cliente de Google Vision
        :param pdf_bytes: Datos binarios del PDF (bytes)
        :param pdf_data_original: Datos originales del PDF (para fallback si es necesario)
        """
        from google.cloud import vision
        
        try:
            # Intentar procesar como imagen (primera página del PDF)
            image = vision.Image(content=pdf_bytes)
            response = client.document_text_detection(image=image)
            
            if response.error.message:
                raise Exception(f"Error de Google Vision: {response.error.message}")
            
            # Extraer texto completo
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            # Si no hay texto, lanzar excepción para que se use OCR alternativo
            if not full_text:
                _logger.info("Google Vision no extrajo texto del PDF.")
                raise Exception(_("Google Vision no extrajo texto. Se intentará con OCR alternativo."))
            
            # Parsear datos de la factura
            return self._parse_invoice_text(full_text)
        except Exception as proc_error:
            _logger.warning("Error procesando con Google Vision: %s", proc_error)
            # Re-lanzar para que el método padre maneje el fallback
            raise

    def _extract_with_fallback_ocr(self, pdf_data):
        """
        Método alternativo usando PyPDF2 o pdfplumber para extraer texto.
        Requiere: pip install pdfplumber o PyPDF2
        """
        try:
            import pdfplumber
            
            # Convertir base64 a bytes si es necesario
            if isinstance(pdf_data, str):
                pdf_bytes = base64.b64decode(pdf_data)
            else:
                pdf_bytes = pdf_data
            
            # Validar que es un PDF válido antes de procesar
            if not pdf_bytes[:4].startswith(b'%PDF'):
                raise ValueError(_("El archivo no es un PDF válido"))
            
            # Extraer texto del PDF
            full_text = ""
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
            
            # Parsear datos
            return self._parse_invoice_text(full_text)
            
        except ImportError:
            try:
                import PyPDF2
                
                if isinstance(pdf_data, str):
                    pdf_bytes = base64.b64decode(pdf_data)
                else:
                    pdf_bytes = pdf_data
                
                # Validar que es un PDF válido
                if not pdf_bytes[:4].startswith(b'%PDF'):
                    raise ValueError(_("El archivo no es un PDF válido"))
                
                full_text = ""
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                for page in pdf_reader.pages:
                    full_text += page.extract_text() + "\n"
                
                return self._parse_invoice_text(full_text)
                
            except ImportError:
                raise UserError(_("Se requiere instalar pdfplumber o PyPDF2 para procesar PDFs. Ejecute: pip install pdfplumber"))
            except Exception as pdf_error:
                _logger.exception("Error con PyPDF2: %s", pdf_error)
                raise UserError(_("Error al procesar el PDF con PyPDF2: %s\n\nEl archivo puede estar corrupto o no ser un PDF válido.") % str(pdf_error))
        except ValueError as ve:
            # Error de validación de PDF
            _logger.exception("Error de validación de PDF: %s", ve)
            raise UserError(str(ve))
        except Exception as e:
            _logger.exception("Error al extraer texto del PDF: %s", e)
            error_msg = str(e)
            if "No /Root object" in error_msg or "not a PDF" in error_msg.lower():
                raise UserError(_("El archivo no es un PDF válido o está corrupto. Por favor, verifica el archivo e intenta de nuevo."))
            raise UserError(_("Error al procesar el PDF: %s\n\nPosibles causas:\n- El PDF está corrupto\n- El PDF está protegido o encriptado\n- El formato no es compatible") % error_msg)

    def _parse_invoice_text(self, text):
        """
        Parsea el texto extraído de la factura y extrae información estructurada.
        Usa expresiones regulares y patrones comunes de facturas.
        """
        if not text:
            return {
                "error": "No se pudo extraer texto del PDF",
                "texto_extraido": ""
            }
        
        data = {
            "texto_extraido": text,
            "numero_factura": None,
            "fecha_factura": None,
            "remitente_nombre": None,
            "remitente_nif": None,
            "remitente_direccion": None,
            "consignatario_nombre": None,
            "consignatario_nif": None,
            "consignatario_direccion": None,
            "valor_total": None,
            "moneda": "EUR",
            "lineas": [],
            "incoterm": None,
            "pais_origen": None,
            "pais_destino": None,
        }
        
        # Buscar número de factura
        factura_patterns = [
            r'(?:FACTURA|Invoice|Factura)\s*(?:N[º°]?|Número|No\.?|#)\s*:?\s*([A-Z0-9\-/]+)',
            r'N[º°]?\s*FACTURA\s*:?\s*([A-Z0-9\-/]+)',
            r'Factura\s+([A-Z0-9\-/]+)',
        ]
        for pattern in factura_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["numero_factura"] = match.group(1).strip()
                break
        
        # Buscar fecha
        fecha_patterns = [
            r'(?:Fecha|Date)\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        ]
        for pattern in fecha_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["fecha_factura"] = match.group(1).strip()
                break
        
        # Buscar NIF/CIF (formato español)
        nif_pattern = r'[A-Z]?\d{8}[A-Z]?'
        nifs = re.findall(nif_pattern, text)
        if nifs:
            # El primer NIF suele ser el emisor, el segundo el receptor
            if len(nifs) >= 1:
                data["remitente_nif"] = nifs[0]
            if len(nifs) >= 2:
                data["consignatario_nif"] = nifs[1]
        
        # Buscar importe total
        total_patterns = [
            r'(?:TOTAL|Total|Importe Total|Amount)\s*:?\s*([\d.,]+)\s*([A-Z]{3})?',
            r'([\d.,]+)\s*(?:EUR|€|USD|\$)',
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                valor_str = match.group(1).replace(',', '.')
                try:
                    data["valor_total"] = float(valor_str)
                except:
                    pass
                if match.lastindex >= 2 and match.group(2):
                    data["moneda"] = match.group(2).upper()
                break
        
        # Buscar nombres de empresas (patrones comunes)
        # Buscar después de palabras clave como "De:", "From:", "Cliente:", etc.
        nombre_patterns = [
            r'(?:De|From|Emisor|Cliente|Customer)\s*:?\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]+)',
        ]
        for pattern in nombre_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for i, match in enumerate(matches):
                if i == 0:
                    data["remitente_nombre"] = match.group(1).strip()[:100]
                elif i == 1:
                    data["consignatario_nombre"] = match.group(1).strip()[:100]
        
        # Buscar Incoterm
        incoterm_pattern = r'\b(EXW|FCA|CPT|CIP|DAP|DPU|DDP|FOB|CFR|CIF)\b'
        match = re.search(incoterm_pattern, text, re.IGNORECASE)
        if match:
            data["incoterm"] = match.group(1).upper()
        
        # Buscar países (códigos ISO comunes)
        pais_pattern = r'\b(ES|AD|FR|PT|DE|IT|GB|US)\b'
        paises = re.findall(pais_pattern, text)
        if paises:
            data["pais_origen"] = paises[0] if len(paises) > 0 else "ES"
            data["pais_destino"] = paises[1] if len(paises) > 1 else "AD"
        
        # Intentar extraer líneas de productos
        # Buscar patrones comunes de tablas de factura
        lineas = self._extract_invoice_lines(text)
        if lineas:
            data["lineas"] = lineas
        
        return data
    
    def _extract_invoice_lines(self, text):
        """
        Intenta extraer líneas de productos de la factura.
        Busca patrones comunes en tablas de facturas.
        """
        lineas = []
        
        # Patrón para líneas de factura típicas:
        # Cantidad | Descripción | Precio unitario | Total
        # O: Descripción | Cantidad | Precio | Total
        
        # Buscar números seguidos de descripciones y precios
        # Patrón mejorado para líneas de factura
        line_patterns = [
            # Formato: cantidad descripción precio total
            r'(\d+[.,]?\d*)\s+([A-ZÁÉÍÓÚÑ][^0-9€$]{10,100}?)\s+([\d.,]+)\s*([€$]?)\s+([\d.,]+)\s*([€$]?)',
            # Formato: descripción cantidad precio
            r'([A-ZÁÉÍÓÚÑ][^0-9€$]{10,100}?)\s+(\d+[.,]?\d*)\s+([\d.,]+)\s*([€$]?)',
        ]
        
        lines_found = []
        for pattern in line_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                # Intentar identificar qué es cada grupo
                groups = match.groups()
                if len(groups) >= 3:
                    linea = {
                        "descripcion": None,
                        "cantidad": None,
                        "precio_unitario": None,
                        "total": None,
                    }
                    
                    # El primer número suele ser cantidad
                    try:
                        cantidad = float(groups[0].replace(',', '.'))
                        if cantidad > 0 and cantidad < 10000:  # Rango razonable
                            linea["cantidad"] = cantidad
                            linea["unidades"] = cantidad
                    except:
                        pass
                    
                    # Buscar descripción (texto largo)
                    for i, group in enumerate(groups):
                        if isinstance(group, str) and len(group) > 10 and not re.match(r'^[\d.,€$]+$', group):
                            if not linea["descripcion"]:
                                linea["descripcion"] = group.strip()[:200]
                    
                    # Buscar precios (números con decimales)
                    for i, group in enumerate(groups):
                        if isinstance(group, str) and re.match(r'^[\d.,]+$', group):
                            try:
                                precio = float(group.replace(',', '.'))
                                if precio > 0:
                                    if not linea["precio_unitario"]:
                                        linea["precio_unitario"] = precio
                                    else:
                                        linea["total"] = precio
                            except:
                                pass
                    
                    # Solo agregar si tiene al menos descripción y cantidad
                    if linea["descripcion"] and linea["cantidad"]:
                        lines_found.append(linea)
        
        # Limitar a máximo 20 líneas para evitar ruido
        return lines_found[:20]

    def fill_expediente_from_invoice(self, expediente, invoice_data):
        """
        Rellena los campos de un expediente con los datos extraídos de la factura.
        
        :param expediente: Recordset de aduana.expediente
        :param invoice_data: Diccionario con datos extraídos
        """
        expediente.ensure_one()
        
        # Actualizar número de factura
        if invoice_data.get("numero_factura"):
            expediente.numero_factura = invoice_data["numero_factura"]
        
        # Actualizar valor de factura
        if invoice_data.get("valor_total"):
            expediente.valor_factura = invoice_data["valor_total"]
        
        # Actualizar moneda
        if invoice_data.get("moneda"):
            expediente.moneda = invoice_data["moneda"]
        
        # Actualizar incoterm
        if invoice_data.get("incoterm"):
            expediente.incoterm = invoice_data["incoterm"]
        
        # Actualizar países
        if invoice_data.get("pais_origen"):
            expediente.pais_origen = invoice_data["pais_origen"]
        if invoice_data.get("pais_destino"):
            expediente.pais_destino = invoice_data["pais_destino"]
        
        # Buscar o crear remitente
        if invoice_data.get("remitente_nif") or invoice_data.get("remitente_nombre"):
            remitente = self._find_or_create_partner(
                name=invoice_data.get("remitente_nombre"),
                vat=invoice_data.get("remitente_nif"),
                street=invoice_data.get("remitente_direccion")
            )
            if remitente:
                expediente.remitente = remitente
        
        # Buscar o crear consignatario
        if invoice_data.get("consignatario_nif") or invoice_data.get("consignatario_nombre"):
            consignatario = self._find_or_create_partner(
                name=invoice_data.get("consignatario_nombre"),
                vat=invoice_data.get("consignatario_nif"),
                street=invoice_data.get("consignatario_direccion")
            )
            if consignatario:
                expediente.consignatario = consignatario
        
        # Crear líneas de productos si se extrajeron
        if invoice_data.get("lineas"):
            # Limpiar líneas existentes si las hay
            expediente.line_ids.unlink()
            
            # Crear nuevas líneas
            LineModel = self.env["aduana.expediente.line"]
            for idx, linea_data in enumerate(invoice_data["lineas"], start=1):
                line_vals = {
                    "expediente_id": expediente.id,
                    "item_number": idx,
                    "descripcion": linea_data.get("descripcion", ""),
                    "unidades": linea_data.get("unidades") or linea_data.get("cantidad") or 1.0,
                    "valor_linea": linea_data.get("total") or linea_data.get("precio_unitario") or 0.0,
                    "pais_origen": expediente.pais_origen or "ES",
                }
                # Si hay peso en la descripción, intentar extraerlo
                desc = linea_data.get("descripcion", "")
                peso_match = re.search(r'(\d+[.,]?\d*)\s*(kg|KG|Kg|kilogramos?)', desc)
                if peso_match:
                    try:
                        peso = float(peso_match.group(1).replace(',', '.'))
                        line_vals["peso_bruto"] = peso
                        line_vals["peso_neto"] = peso * 0.95  # Aproximación
                    except:
                        pass
                
                LineModel.create(line_vals)
        
        # Guardar datos extraídos como texto para referencia
        expediente.factura_datos_extraidos = json.dumps(invoice_data, indent=2, ensure_ascii=False)
        expediente.factura_procesada = True
        
        return True

    def _find_or_create_partner(self, name=None, vat=None, street=None):
        """
        Busca un partner existente o crea uno nuevo basado en NIF o nombre.
        """
        Partner = self.env['res.partner']
        
        # Buscar por NIF primero
        if vat:
            vat_clean = vat.replace(' ', '').replace('-', '').upper()
            partner = Partner.search([('vat', '=', vat_clean)], limit=1)
            if partner:
                return partner
        
        # Buscar por nombre
        if name:
            partner = Partner.search([('name', 'ilike', name)], limit=1)
            if partner:
                return partner
        
        # Crear nuevo partner si no existe
        if name or vat:
            partner_vals = {
                'name': name or 'Sin nombre',
                'is_company': True,
            }
            if vat:
                partner_vals['vat'] = vat.replace(' ', '').replace('-', '').upper()
            if street:
                partner_vals['street'] = street
            
            return Partner.create(partner_vals)
        
        return None

