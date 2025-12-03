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
        Extrae datos de una factura PDF usando OpenAI GPT-4o Vision o OCR alternativo.
        
        :param pdf_data: Datos binarios del PDF (base64 o bytes)
        :param api_key: API key de OpenAI (opcional, se obtiene de configuración si no se proporciona)
        :return: Diccionario con datos extraídos (incluye campo 'error' si hay problemas)
        """
        if not pdf_data:
            return {
                "error": _("No se proporcionó ningún archivo PDF"),
                "texto_extraido": ""
            }
        
        # Simplificar: solo decodificar base64 si es necesario, sin validaciones complejas
        # Google Vision se encargará de validar el PDF
        try:
            # En Odoo, los campos Binary siempre vienen como string base64
            if isinstance(pdf_data, str):
                try:
                    # Decodificar base64
                    pdf_bytes = base64.b64decode(pdf_data)
                    # Verificar si está doblemente codificado (empieza con JVBER después de decodificar)
                    if len(pdf_bytes) > 0:
                        try:
                            first_chars = pdf_bytes[:10].decode('utf-8', errors='ignore')
                            if first_chars.startswith('JVBER') or first_chars.startswith('JVBERi'):
                                _logger.info("Doble encoding detectado, decodificando de nuevo...")
                                pdf_bytes = base64.b64decode(pdf_bytes)
                        except:
                            pass
                except Exception as decode_error:
                    _logger.error("Error al decodificar base64: %s", decode_error)
                    return {
                        "error": _("Error al decodificar el archivo PDF."),
                        "texto_extraido": "",
                        "metodo_usado": "Error de decodificación"
                    }
            else:
                pdf_bytes = pdf_data
            
            # Validación mínima: solo verificar que no esté vacío
            if not pdf_bytes or len(pdf_bytes) < 10:
                return {
                    "error": _("El archivo PDF está vacío o es demasiado pequeño."),
                    "texto_extraido": "",
                    "metodo_usado": "Error de validación"
                }
            
            _logger.info("PDF preparado para procesamiento. Tamaño: %d bytes", len(pdf_bytes))
            
        except Exception as e:
            _logger.exception("Error al procesar el archivo PDF: %s", e)
            return {
                "error": _("Error al procesar el archivo PDF: %s") % str(e),
                "texto_extraido": "",
                "metodo_usado": "Error de procesamiento"
            }
        
        # Obtener API key de configuración si no se proporciona
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('aduanas_transport.openai_api_key')
        
        resultado = None
        metodo_usado = None
        
        # PRIORIDAD: Intentar OpenAI GPT-4o Vision primero (si hay API key)
        if api_key:
            try:
                _logger.info("Enviando PDF a OpenAI GPT-4o Vision con splitting por páginas...")
                resultado = self._extract_with_openai_vision(api_key, pdf_bytes)
                metodo_usado = "OpenAI GPT-4o Vision"
                _logger.info("OpenAI GPT-4o Vision procesó el PDF exitosamente")
            except Exception as e:
                _logger.warning("Error con OpenAI GPT-4o Vision: %s. Intentando OCR alternativo...", e)
                try:
                    resultado = self._extract_with_fallback_ocr(pdf_bytes)
                    metodo_usado = "OCR Alternativo (fallback)"
                except Exception as e2:
                    _logger.exception("Error también con OCR alternativo: %s", e2)
                    return {
                        "error": _("Error al procesar PDF:\n- OpenAI GPT-4o Vision: %s\n- OCR Alternativo: %s") % (str(e), str(e2)),
                        "texto_extraido": "",
                        "metodo_usado": "Error en ambos"
                    }
        else:
            # Si no hay API key, usar OCR alternativo
            _logger.info("No hay API key de OpenAI configurada, usando OCR alternativo...")
            try:
                resultado = self._extract_with_fallback_ocr(pdf_bytes)
                metodo_usado = "OCR Alternativo (pdfplumber/PyPDF2)"
            except Exception as e:
                _logger.exception("Error con OCR alternativo: %s", e)
                return {
                    "error": _("Error al procesar PDF: %s\n\nConfigura OpenAI API Key para mejor soporte de PDFs escaneados.") % str(e),
                    "texto_extraido": "",
                    "metodo_usado": "Error"
                }
        
        # Agregar información del método usado
        if resultado:
            resultado["metodo_usado"] = metodo_usado
            
            # Validar que se extrajo texto
            if not resultado.get("texto_extraido") or len(resultado.get("texto_extraido", "").strip()) < 10:
                if not resultado.get("error"):
                    resultado["error"] = _("No se pudo extraer texto del PDF. Posibles causas:\n- El PDF es una imagen escaneada (necesitas OpenAI API Key)\n- El PDF está protegido o encriptado\n- El PDF está corrupto\n- La calidad del escaneado es muy baja")
        
        return resultado

    def _extract_with_openai_vision(self, api_key, pdf_bytes):
        """
        Extrae datos usando OpenAI GPT-4o Vision convirtiendo PDF a imágenes.
        Requiere: pip install openai PyMuPDF
        
        OpenAI solo acepta imágenes (no PDFs directamente), por lo que necesitamos
        convertir cada página del PDF a imagen antes de enviarla.
        
        :param api_key: API key de OpenAI
        :param pdf_bytes: Datos binarios del PDF (bytes)
        :return: Diccionario con datos extraídos
        """
        try:
            from openai import OpenAI
            import fitz  # PyMuPDF
            
            if not api_key:
                raise ValueError("API key de OpenAI no proporcionada")
            
            # Inicializar cliente de OpenAI
            client = OpenAI(api_key=api_key)
            
            # Abrir PDF y convertir a imágenes
            _logger.info("Convirtiendo PDF a imágenes por páginas...")
            try:
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
                num_pages = len(pdf_document)
                _logger.info("PDF abierto: %d página(s)", num_pages)
                
                if num_pages == 0:
                    raise Exception(_("El PDF no tiene páginas"))
                
            except Exception as pdf_error:
                _logger.error("Error al abrir PDF: %s", pdf_error)
                raise Exception(_("Error al abrir el PDF. Verifica que el archivo sea un PDF válido."))
            
            # Procesar cada página con GPT-4o Vision
            all_texts = []
            for page_num in range(num_pages):
                _logger.info("Procesando página %d/%d con GPT-4o Vision...", page_num + 1, num_pages)
                
                try:
                    # Obtener página y convertir a imagen PNG
                    page = pdf_document[page_num]
                    mat = fitz.Matrix(200/72, 200/72)  # 200 DPI para buena calidad
                    pix = page.get_pixmap(matrix=mat)
                    
                    # Convertir a base64
                    img_bytes = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    # Llamar a OpenAI Vision API con prompt específico para contexto legal/administrativo
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Eres un asistente de procesamiento documental para una empresa de logística y aduanas.\n\n"
                                                "El documento proporcionado es una factura comercial utilizada exclusivamente para generar un documento aduanero (DUA).\n\n"
                                                "La extracción que vas a hacer es para un proceso legal obligatorio.\n\n"
                                                "No devuelvas la imagen completa ni reproduzcas el documento.\n"
                                                "Simplemente transcribe el texto visible, incluyendo: números de factura, fechas, direcciones, detalles de mercancía, bultos y totales.\n\n"
                                                "La extracción es estrictamente con fines administrativos y está permitida.\n"
                                                "Devuelve únicamente el texto, sin notas adicionales."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{img_base64}"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=4096
                    )
                    
                    page_text = response.choices[0].message.content
                    if page_text:
                        all_texts.append(page_text)
                        _logger.info("Texto extraído de página %d: %d caracteres", page_num + 1, len(page_text))
                    
                    # Limpiar memoria
                    pix = None
                    
                except Exception as api_error:
                    _logger.error("Error al procesar página %d con OpenAI: %s", page_num + 1, api_error)
                    # Continuar con las siguientes páginas
                    continue
            
            # Cerrar documento
            pdf_document.close()
            
            if not all_texts:
                raise Exception(_("No se pudo extraer texto de ninguna página del PDF"))
            
            # Combinar texto de todas las páginas
            full_text = "\n\n".join(all_texts)
            _logger.info("Texto total extraído: %d caracteres de %d página(s)", len(full_text), num_pages)
            
            # Parsear datos de la factura
            return self._parse_invoice_text(full_text)
            
        except ImportError as import_err:
            _logger.error("Error de importación: %s", import_err)
            raise Exception(_(
                "Faltan dependencias para OpenAI Vision. Instala con:\n"
                "pip install openai PyMuPDF\n\n"
                "PyMuPDF no requiere dependencias externas del sistema."
            ))
        except Exception as e:
            _logger.exception("Error con OpenAI GPT-4o Vision: %s", e)
            raise

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
            return self._extract_with_rest_api(api_key, pdf_bytes)
        
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
            
            # Manejar errores HTTP con mensajes más descriptivos
            if response.status_code == 403:
                try:
                    error_detail = response.json().get('error', {})
                    error_message = error_detail.get('message', 'Forbidden')
                except:
                    error_message = 'Forbidden'
                _logger.error("Error 403 de Google Vision API. Detalle: %s", error_message)
                raise Exception(_(
                    "Error 403: Acceso denegado a Google Vision API.\n\n"
                    "Posibles causas:\n"
                    "1. La API key no tiene permisos para usar Vision API\n"
                    "2. La API 'Cloud Vision API' no está habilitada en tu proyecto de Google Cloud\n"
                    "3. La API key tiene restricciones que bloquean el acceso\n"
                    "4. Se han excedido las cuotas de la API\n\n"
                    "Solución:\n"
                    "1. Ve a Google Cloud Console → APIs & Services → Library\n"
                    "2. Busca 'Cloud Vision API' y habilítala\n"
                    "3. Verifica que la API key tenga permisos para Vision API\n"
                    "4. Revisa las restricciones de la API key\n\n"
                    "Detalle del error: %s"
                ) % error_message)
            elif response.status_code == 401:
                _logger.error("Error 401 de Google Vision API: API key inválida")
                raise Exception(_(
                    "Error 401: API key inválida o no autorizada.\n\n"
                    "Verifica que la API key sea correcta y que tenga permisos para usar Vision API."
                ))
            
            response.raise_for_status()
            
            result = response.json()
            
            # Verificar si hay errores en la respuesta
            if "error" in result:
                error_info = result["error"]
                error_msg = error_info.get("message", "Error desconocido")
                _logger.error("Error en respuesta de Google Vision: %s", error_msg)
                raise Exception(_("Error de Google Vision API: %s") % error_msg)
            
            # Extraer texto de la respuesta
            full_text = ""
            if "responses" in result and len(result["responses"]) > 0:
                if "fullTextAnnotation" in result["responses"][0]:
                    full_text = result["responses"][0]["fullTextAnnotation"].get("text", "")
                elif "textAnnotations" in result["responses"][0] and len(result["responses"][0]["textAnnotations"]) > 0:
                    # Fallback: usar primera anotación de texto
                    full_text = result["responses"][0]["textAnnotations"][0].get("description", "")
            
            if not full_text:
                _logger.warning("Google Vision REST API no extrajo texto.")
                raise Exception(_("Google Vision no extrajo texto. Se intentará con OCR alternativo."))
            
            # Parsear datos de la factura
            return self._parse_invoice_text(full_text)
            
        except requests.exceptions.HTTPError as e:
            # Ya manejamos 401 y 403 arriba, esto es para otros códigos HTTP
            if e.response and e.response.status_code not in [401, 403]:
                _logger.exception("Error HTTP en petición REST a Google Vision: %s", e)
                if e.response.status_code == 400:
                    try:
                        error_detail = e.response.json().get('error', {})
                        error_message = error_detail.get('message', str(e))
                    except:
                        error_message = str(e)
                    raise Exception(_("Error 400: Solicitud inválida a Google Vision API.\n\nDetalle: %s") % error_message)
                raise Exception(_("Error HTTP %d al conectar con Google Vision API: %s") % (e.response.status_code, str(e)))
            raise
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
        
        :param pdf_data: Bytes del PDF (ya decodificado)
        """
        try:
            import pdfplumber
            
            # pdf_data ya viene como bytes decodificado
            pdf_bytes = pdf_data
            
            # Validación mínima: solo verificar que no esté vacío
            if not pdf_bytes or len(pdf_bytes) < 10:
                raise ValueError(_("El archivo PDF está vacío o es demasiado pequeño"))
            
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
                
                # pdf_data ya viene como bytes decodificado
                pdf_bytes = pdf_data
                
                # Validación mínima: solo verificar que no esté vacío
                if not pdf_bytes or len(pdf_bytes) < 10:
                    raise ValueError(_("El archivo PDF está vacío o es demasiado pequeño"))
                
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

