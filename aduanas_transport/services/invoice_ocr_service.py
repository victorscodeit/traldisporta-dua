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
            
            # Intentar interpretar el texto con GPT-4o para estructurarlo
            try:
                structured_data = self._interpret_text_with_gpt(api_key, full_text)
                if structured_data:
                    # Agregar el texto extraído al resultado
                    structured_data["texto_extraido"] = full_text
                    _logger.info("Datos estructurados extraídos con GPT-4o")
                    return structured_data
            except Exception as gpt_error:
                _logger.warning("Error al interpretar texto con GPT-4o: %s. Usando parsing con regex...", gpt_error)
            
            # Fallback: Parsear datos de la factura con regex
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

    def _interpret_text_with_gpt(self, api_key, text):
        """
        Usa GPT-4o para interpretar el texto extraído y estructurarlo en formato JSON.
        
        :param api_key: API key de OpenAI
        :param text: Texto extraído de la factura
        :return: Diccionario con datos estructurados o None si falla
        """
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=api_key)
            
            # Prompt detallado para extraer información estructurada
            prompt = """Eres un experto en procesamiento de facturas comerciales para documentos aduaneros.

Analiza el siguiente texto extraído de una factura y extrae TODA la información relevante en formato JSON estricto.

FORMATO DE RESPUESTA REQUERIDO (JSON válido, sin markdown, sin código, solo JSON):
{
  "numero_factura": "número o null",
  "fecha_factura": "DD.MM.YYYY o DD/MM/YYYY o null",
  "remitente_nombre": "nombre completo de la empresa emisora o null",
  "remitente_nif": "NIF/CIF español (formato A12345678) o NIF andorrano (L123456H) o null",
  "remitente_direccion": "dirección completa o null",
  "consignatario_nombre": "nombre completo del destinatario o null",
  "consignatario_nif": "NIF/CIF o null",
  "consignatario_direccion": "dirección completa o null",
  "valor_total": número decimal o null,
  "moneda": "EUR" o "USD" o null,
  "incoterm": "EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP" o null (si encuentras CIF, FOB, CFR, mapea a CIP, FCA, CPT respectivamente),
  "pais_origen": "código ISO de 2 letras (ES, AD, FR, etc.) o null",
  "pais_destino": "código ISO de 2 letras o null",
  "direction": "export" o "import" o null (export = España → Andorra, import = Andorra → España),
  "transportista": "nombre del transportista o null",
  "matricula": "matrícula del vehículo o null",
  "referencia_transporte": "referencia o número de transporte o null",
  "remolque": "matrícula del remolque o null",
  "codigo_transporte": "código del transporte o null",
  "lineas": [
    {
      "articulo": "código del artículo o null",
      "descripcion": "descripción completa del producto",
      "cantidad": número decimal,
      "unidades": número decimal (igual que cantidad),
      "precio_unitario": número decimal o null,
      "total": número decimal o null,
      "descuento": número decimal (porcentaje de descuento) o null,
      "partida": "código H.S. (8-10 dígitos) o null",
      "bultos": número entero o null,
      "peso_bruto": número decimal en KG o null,
      "peso_neto": número decimal en KG o null
    }
  ]
}

INSTRUCCIONES IMPORTANTES:
1. Extrae SOLO los artículos/productos de la factura ACTUAL. IGNORA completamente cualquier sección que diga "Pedido pendiente", "Pedidos pendientes", "Pendiente" o similar. Esos productos NO deben aparecer en las líneas.
2. Para el código H.S. (partida arancelaria), busca "H.S.", "HS", "Partida arancelaria" seguido de números de 8-10 dígitos. Es OBLIGATORIO incluirlo en cada línea de producto.
3. Para incoterms, busca DAP, CIF, FOB, EXW, etc. en el texto
4. Para países, identifica por contexto: España/Spain/Barcelona → ES, Andorra → AD
5. Para direction (sentido), determina basándote en los países:
   - Si pais_origen = "ES" y pais_destino = "AD" → direction = "export" (España → Andorra, Exportación)
   - Si pais_origen = "AD" y pais_destino = "ES" → direction = "import" (Andorra → España, Importación)
   - Si no puedes determinarlo con certeza, usa null
6. Para NIFs, busca patrones como A12345678 (español) o L123456H (andorrano)
7. Para valores monetarios, usa el formato español (2.195,42 → 2195.42)
8. Para transporte, busca:
   - Transportista: nombre de la empresa transportista
   - Matrícula: número de matrícula del vehículo (formato como 5728-KXF)
   - Referencia Transporte: número de referencia del transporte o albarán
   - Remolque: matrícula del remolque si aparece
   - Código Transporte: código alfanumérico del transporte (como TXT, TX5X)
9. Para descuentos, busca porcentajes de descuento asociados a cada línea o descuento general. Si hay "Descuento Principal 64,00%" o similar, inclúyelo en las líneas correspondientes.
10. Si un campo no se encuentra, usa null (no uses cadenas vacías)
11. Devuelve SOLO el JSON, sin explicaciones, sin markdown, sin ```json
12. CRÍTICO: Si ves una sección que dice "Pedido pendiente" o "Pedidos pendientes", esos productos NO son de esta factura. Solo extrae productos que estén claramente asociados a la factura actual.

TEXTO DE LA FACTURA:
""" + text[:15000]  # Limitar a 15000 caracteres para evitar exceder límites
            
            _logger.info("Enviando texto a GPT-4o para interpretación estructurada...")
            
            # Intentar usar response_format si está disponible (GPT-4o y modelos recientes)
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "Eres un experto en extracción de datos de facturas comerciales. Siempre devuelves JSON válido y estructurado. Responde ÚNICAMENTE con JSON, sin explicaciones ni texto adicional."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,  # Baja temperatura para respuestas más consistentes
                    max_tokens=4000,
                    response_format={"type": "json_object"}  # Forzar formato JSON (GPT-4o)
                )
            except TypeError:
                # Si response_format no está disponible, usar sin él
                _logger.warning("response_format no disponible, usando prompt sin formato forzado")
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "Eres un experto en extracción de datos de facturas comerciales. Siempre devuelves JSON válido y estructurado. Responde ÚNICAMENTE con JSON, sin explicaciones ni texto adicional."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
            
            response_text = response.choices[0].message.content
            _logger.info("Respuesta de GPT-4o recibida: %d caracteres", len(response_text))
            
            # Limpiar la respuesta (quitar markdown si existe)
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parsear JSON
            try:
                data = json.loads(response_text)
                
                # Validar y normalizar datos
                if not isinstance(data, dict):
                    raise ValueError("La respuesta no es un diccionario")
                
                # Asegurar que lineas es una lista
                if "lineas" in data and not isinstance(data["lineas"], list):
                    data["lineas"] = []
                
                # Validar y normalizar direction (sentido)
                if data.get("direction"):
                    direction = data["direction"].lower()
                    if direction not in ["export", "import"]:
                        # Intentar determinar basándose en países
                        pais_origen = data.get("pais_origen", "").upper()
                        pais_destino = data.get("pais_destino", "").upper()
                        if pais_origen == "ES" and pais_destino == "AD":
                            data["direction"] = "export"
                        elif pais_origen == "AD" and pais_destino == "ES":
                            data["direction"] = "import"
                        else:
                            data["direction"] = None
                    else:
                        data["direction"] = direction
                else:
                    # Si no hay direction pero hay países, intentar determinarlo
                    pais_origen = data.get("pais_origen", "").upper()
                    pais_destino = data.get("pais_destino", "").upper()
                    if pais_origen == "ES" and pais_destino == "AD":
                        data["direction"] = "export"
                    elif pais_origen == "AD" and pais_destino == "ES":
                        data["direction"] = "import"
                
                # Validar incoterm
                if data.get("incoterm"):
                    incoterm = data["incoterm"].upper()
                    incoterm_map = {
                        "FOB": "FCA",
                        "CIF": "CIP",
                        "CFR": "CPT",
                    }
                    valid_incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"]
                    
                    if incoterm in incoterm_map:
                        data["incoterm"] = incoterm_map[incoterm]
                    elif incoterm not in valid_incoterms:
                        data["incoterm"] = "DAP"  # Valor por defecto
                    else:
                        data["incoterm"] = incoterm
                
                # Normalizar valores numéricos
                if data.get("valor_total"):
                    try:
                        if isinstance(data["valor_total"], str):
                            # Convertir formato español a decimal
                            data["valor_total"] = float(data["valor_total"].replace('.', '').replace(',', '.'))
                        else:
                            data["valor_total"] = float(data["valor_total"])
                    except:
                        data["valor_total"] = None
                
                # Normalizar líneas y filtrar productos de pedidos pendientes
                lineas_validas = []
                for linea in data.get("lineas", []):
                    # Filtrar productos que puedan ser de pedidos pendientes
                    descripcion = linea.get("descripcion", "").lower()
                    # Si la descripción contiene indicadores de pedido pendiente, saltar
                    if any(palabra in descripcion for palabra in ["pedido pendiente", "pendiente", "pending order"]):
                        _logger.info("Ignorando línea con descripción de pedido pendiente: %s", linea.get("descripcion"))
                        continue
                    # Normalizar cantidad y unidades
                    if linea.get("cantidad"):
                        try:
                            if isinstance(linea["cantidad"], str):
                                linea["cantidad"] = float(linea["cantidad"].replace(',', '.'))
                            else:
                                linea["cantidad"] = float(linea["cantidad"])
                            if not linea.get("unidades"):
                                linea["unidades"] = linea["cantidad"]
                        except:
                            pass
                    
                    # Normalizar precios
                    for campo_precio in ["precio_unitario", "total"]:
                        if linea.get(campo_precio):
                            try:
                                if isinstance(linea[campo_precio], str):
                                    linea[campo_precio] = float(linea[campo_precio].replace('.', '').replace(',', '.'))
                                else:
                                    linea[campo_precio] = float(linea[campo_precio])
                            except:
                                linea[campo_precio] = None
                    
                    # Normalizar descuento
                    if linea.get("descuento"):
                        try:
                            if isinstance(linea["descuento"], str):
                                # Puede venir como "64,00%" o "64.00" o "64"
                                descuento_str = linea["descuento"].replace('%', '').replace(',', '.')
                                linea["descuento"] = float(descuento_str)
                            else:
                                linea["descuento"] = float(linea["descuento"])
                        except:
                            linea["descuento"] = None
                    
                    # Normalizar pesos
                    for campo_peso in ["peso_bruto", "peso_neto"]:
                        if linea.get(campo_peso):
                            try:
                                if isinstance(linea[campo_peso], str):
                                    linea[campo_peso] = float(linea[campo_peso].replace(',', '.'))
                                else:
                                    linea[campo_peso] = float(linea[campo_peso])
                            except:
                                linea[campo_peso] = None
                    
                    # Normalizar bultos
                    if linea.get("bultos"):
                        try:
                            if isinstance(linea["bultos"], str):
                                linea["bultos"] = int(float(linea["bultos"].replace(',', '.')))
                            else:
                                linea["bultos"] = int(linea["bultos"])
                        except:
                            linea["bultos"] = None
                    
                    # Normalizar partida arancelaria (asegurar formato correcto)
                    if linea.get("partida"):
                        partida = str(linea["partida"]).strip()
                        # Limpiar espacios y caracteres no numéricos
                        partida = ''.join(filter(str.isdigit, partida))
                        if partida:
                            # Asegurar que tenga al menos 8 dígitos
                            if len(partida) < 8:
                                partida = partida.zfill(8)
                            # Truncar si tiene más de 10
                            if len(partida) > 10:
                                partida = partida[:10]
                            linea["partida"] = partida
                        else:
                            linea["partida"] = None
                    else:
                        _logger.warning("Línea sin partida arancelaria: %s", linea.get("descripcion"))
                    
                    lineas_validas.append(linea)
                
                # Reemplazar lineas con las válidas
                data["lineas"] = lineas_validas
                
                _logger.info("Datos estructurados validados: %d líneas extraídas", len(data.get("lineas", [])))
                return data
                
            except json.JSONDecodeError as json_err:
                _logger.error("Error parseando JSON de GPT-4o: %s. Respuesta: %s", json_err, response_text[:500])
                return None
            except Exception as parse_err:
                _logger.error("Error procesando respuesta de GPT-4o: %s", parse_err)
                return None
                
        except ImportError:
            _logger.warning("OpenAI no disponible para interpretación de texto")
            return None
        except Exception as e:
            _logger.exception("Error al interpretar texto con GPT-4o: %s", e)
            return None

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
            "direction": None,
        }
        
        # Buscar número de factura
        factura_patterns = [
            r'(?:FACTURA|Invoice|Factura)\s*(?:n[º°]?|N[º°]?|Número|No\.?|#)\s*:?\s*(\d+)',
            r'N[º°]?\s*FACTURA\s*:?\s*(\d+)',
            r'Factura\s+n[º°]?\s*:?\s*(\d+)',
            r'Factura\s+([A-Z0-9\-/]+)',
        ]
        for pattern in factura_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["numero_factura"] = match.group(1).strip()
                break
        
        # Buscar fecha (priorizar fechas después de "Factura" o "de")
        fecha_patterns = [
            r'(?:Factura\s+n[º°]?:\s*\d+\s+de\s+|Fecha|Date)\s*:?\s*(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})',
            r'(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})',
        ]
        for pattern in fecha_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["fecha_factura"] = match.group(1).strip()
                break
        
        # Buscar NIF/CIF (formato español y andorrano)
        # Patrón mejorado para NIF español (A12345678) y andorrano (L123456H)
        nif_patterns = [
            r'\b([A-Z]\d{8}[A-Z]?)\b',  # NIF español: A12345678 o A12345678Z
            r'\b(L\d{6,7}[A-Z]?)\b',    # NIF andorrano: L714949H
            r'\bNIF[:\s]+([A-Z]?\d{6,8}[A-Z]?)\b',  # NIF: A12345678
            r'\bC\.I\.F\.?[:\s]+([A-Z]?\d{6,8}[A-Z]?)\b',  # C.I.F.: A12345678
            r'\bNRT[:\s]+([A-Z]?\d{6,8}[A-Z]?)\b',  # NRT: L714949H
        ]
        nifs = []
        for pattern in nif_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                nif = match.group(1).strip().upper()
                if nif not in nifs:
                    nifs.append(nif)
        
        if nifs:
            # Buscar contexto para identificar remitente y consignatario
            # Remitente suele aparecer primero, cerca de "Motul" o "Propietario"
            # Consignatario suele aparecer después, cerca de "Destinatario" o "Cliente"
            text_lower = text.lower()
            for nif in nifs:
                # Buscar contexto alrededor del NIF
                nif_pos = text.upper().find(nif.upper())
                if nif_pos > 0:
                    context = text[max(0, nif_pos-100):nif_pos+100].lower()
                    if any(word in context for word in ['propietario', 'motul', 'remitente', 'emisor']):
                        if not data["remitente_nif"]:
                            data["remitente_nif"] = nif
                    elif any(word in context for word in ['destinatario', 'consignatario', 'cliente', 'multi retail']):
                        if not data["consignatario_nif"]:
                            data["consignatario_nif"] = nif
            
            # Si no se identificaron por contexto, usar orden de aparición
            if not data["remitente_nif"] and len(nifs) >= 1:
                data["remitente_nif"] = nifs[0]
            if not data["consignatario_nif"] and len(nifs) >= 2:
                data["consignatario_nif"] = nifs[1]
            elif not data["consignatario_nif"] and len(nifs) >= 1:
                # Si solo hay un NIF y no se identificó remitente, puede ser consignatario
                if not data["remitente_nif"]:
                    data["remitente_nif"] = nifs[0]
        
        # Buscar importe total (priorizar "Total Factura" o "Importe Neto")
        total_patterns = [
            r'(?:TOTAL\s+FACTURA|Total\s+Factura|Importe\s+Neto\s+2)\s*:?\s*([\d.,]+)',
            r'(?:TOTAL|Total|Importe Total|Amount)\s*:?\s*([\d.,]+)\s*([A-Z]{3})?',
            r'([\d.,]+)\s*(?:EUR|€|USD|\$)',
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                valor_str = match.group(1).replace('.', '').replace(',', '.')  # Formato español: 2.195,42
                try:
                    data["valor_total"] = float(valor_str)
                except:
                    pass
                if match.lastindex >= 2 and match.group(2):
                    data["moneda"] = match.group(2).upper()
                break
        
        # Buscar nombres de empresas (patrones mejorados)
        # Remitente: buscar después de "Propietario:", "Motul", o al inicio del documento
        remitente_patterns = [
            r'Propietario:\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]+?)(?:\n|C/|CIF|Tel\.)',
            r'(Motul\s+Ibérica\s+SA?[A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]*?)(?:\n|C/|CIF|Tel\.)',
        ]
        for pattern in remitente_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                nombre = match.group(1).strip()
                # Limpiar nombre (quitar espacios múltiples, saltos de línea)
                nombre = re.sub(r'\s+', ' ', nombre).strip()
                data["remitente_nombre"] = nombre[:100]
                break
        
        # Consignatario: buscar después de "Destinatario:", "DIRECCION ENTREGA", "Cliente N°"
        consignatario_patterns = [
            r'Destinatario:\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]+?)(?:\n|NIF|NRT|Tel\.)',
            r'DIRECCION\s+ENTREGA\s+[0-9]+:\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]+?)(?:\n|NRT|NIF)',
            r'(?:Cliente\s+N[º°]?|Cliente:)\s*[0-9]+\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]+?)(?:\n|NRT|NIF)',
            r'(MULTI\s+RETAIL\s+TRADE[,\s]+S\.L\.U\.[A-ZÁÉÍÓÚÑa-záéíóúñ\s,\.]*?)(?:\n|NRT|NIF)',
        ]
        for pattern in consignatario_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                nombre = match.group(1).strip()
                # Limpiar nombre
                nombre = re.sub(r'\s+', ' ', nombre).strip()
                data["consignatario_nombre"] = nombre[:100]
                break
        
        # Buscar Incoterm
        incoterm_pattern = r'\b(EXW|FCA|CPT|CIP|DAP|DPU|DDP|FOB|CFR|CIF)\b'
        match = re.search(incoterm_pattern, text, re.IGNORECASE)
        if match:
            data["incoterm"] = match.group(1).upper()
        
        # Buscar países (códigos ISO comunes y nombres de países)
        # Buscar por contexto: "España" o "Spain" -> ES, "Andorra" -> AD
        pais_origen_patterns = [
            r'(?:Origen|Origin|From|España|Spain|Español)\s*:?\s*([A-Z]{2})',
            r'\b(ES|ESPAÑA|SPAIN)\b',
        ]
        for pattern in pais_origen_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pais = match.group(1).upper()[:2]
                if pais == 'ES' or 'ESPAÑA' in pais or 'SPAIN' in pais:
                    data["pais_origen"] = "ES"
                    break
        
        pais_destino_patterns = [
            r'(?:Destino|Destination|To|Andorra)\s*:?\s*([A-Z]{2})',
            r'\b(AD|ANDORRA)\b',
        ]
        for pattern in pais_destino_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pais = match.group(1).upper()[:2]
                if pais == 'AD' or 'ANDORRA' in pais:
                    data["pais_destino"] = "AD"
                    break
        
        # Si no se encontraron por contexto, buscar códigos ISO en el texto
        if not data["pais_origen"] or not data["pais_destino"]:
            pais_pattern = r'\b(ES|AD|FR|PT|DE|IT|GB|US)\b'
            paises = re.findall(pais_pattern, text)
            if paises:
                # Filtrar paises que aparecen en direcciones (códigos postales)
                paises_validos = []
                for pais in paises:
                    # Evitar falsos positivos (códigos que aparecen en otros contextos)
                    if pais in ['ES', 'AD', 'FR', 'PT', 'DE', 'IT', 'GB', 'US']:
                        paises_validos.append(pais)
                
                if paises_validos:
                    # Si hay "ANDORRA" en el texto, el destino es AD
                    if 'ANDORRA' in text.upper() or 'AD500' in text.upper():
                        data["pais_destino"] = "AD"
                    # Si hay "Barcelona" o "España" en el texto, el origen es ES
                    if 'BARCELONA' in text.upper() or 'ESPAÑA' in text.upper() or 'SPAIN' in text.upper():
                        data["pais_origen"] = "ES"
                    
                    # Valores por defecto si no se encontraron
                    if not data["pais_origen"]:
                        data["pais_origen"] = paises_validos[0] if len(paises_validos) > 0 else "ES"
                    if not data["pais_destino"]:
                        data["pais_destino"] = paises_validos[1] if len(paises_validos) > 1 else "AD"
        
        # Determinar direction (sentido) basándose en países
        pais_origen = data.get("pais_origen", "").upper()
        pais_destino = data.get("pais_destino", "").upper()
        if pais_origen == "ES" and pais_destino == "AD":
            data["direction"] = "export"
        elif pais_origen == "AD" and pais_destino == "ES":
            data["direction"] = "import"
        else:
            data["direction"] = None
        
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
        
        # Método 1: Buscar formato estructurado con etiquetas **Artículo:**, **Descripción:**, etc.
        # Este formato es común en facturas procesadas por OCR/IA
        # Patrones flexibles que aceptan asteriscos o sin ellos
        articulo_pattern = r'(?:\*\*)?Artículo(?:\*\*)?\s*:?\s*(\d+)'
        descripcion_pattern = r'(?:\*\*)?Descripción(?:\*\*)?\s*:?\s*([^\n]+?)(?=\n(?:\*\*)?[A-Z]|\n\n|$)'
        cantidad_pattern = r'(?:\*\*)?Cantidad\s+Expedición(?:\*\*)?\s*:?\s*(\d+[.,]?\d*)\s*([A-Z/]+)?'
        importe_pattern = r'(?:\*\*)?Importe\s+\(EUR\)(?:\*\*)?\s*:?\s*([\d.,]+)'
        importe_neto_pattern = r'(?:\*\*)?Importe\s+Neto\s+2(?:\*\*)?\s*:?\s*([\d.,]+)'
        hs_pattern = r'(?:\*\*)?H\.S\.(?:\*\*)?\s*:?\s*(\d+)'
        
        # Buscar todas las ocurrencias de artículos
        articulos = list(re.finditer(articulo_pattern, text, re.IGNORECASE))
        
        for articulo_match in articulos:
            articulo_pos = articulo_match.start()
            # Buscar descripción, cantidad e importe después de este artículo
            texto_desde_articulo = text[articulo_pos:articulo_pos+2000]  # Buscar en los siguientes 2000 caracteres
            
            linea = {
                "articulo": articulo_match.group(1).strip(),
                "descripcion": None,
                "cantidad": None,
                "unidades": None,
                "precio_unitario": None,
                "total": None,
                "partida": None,
            }
            
            # Buscar descripción
            desc_match = re.search(descripcion_pattern, texto_desde_articulo, re.IGNORECASE)
            if desc_match:
                linea["descripcion"] = desc_match.group(1).strip()
            
            # Buscar cantidad
            cant_match = re.search(cantidad_pattern, texto_desde_articulo, re.IGNORECASE)
            if cant_match:
                try:
                    cantidad_str = cant_match.group(1).replace(',', '.')
                    cantidad = float(cantidad_str)
                    linea["cantidad"] = cantidad
                    linea["unidades"] = cantidad
                except:
                    pass
            
            # Buscar importe total
            importe_match = re.search(importe_pattern, texto_desde_articulo, re.IGNORECASE)
            if importe_match:
                try:
                    importe_str = importe_match.group(1).replace('.', '').replace(',', '.')
                    importe = float(importe_str)
                    linea["total"] = importe
                    # Calcular precio unitario si hay cantidad
                    if linea.get("cantidad") and linea["cantidad"] > 0:
                        linea["precio_unitario"] = importe / linea["cantidad"]
                except:
                    pass
            
            # Si no hay importe total, buscar importe neto
            if not linea.get("total"):
                importe_neto_match = re.search(importe_neto_pattern, texto_desde_articulo, re.IGNORECASE)
                if importe_neto_match:
                    try:
                        importe_str = importe_neto_match.group(1).replace('.', '').replace(',', '.')
                        importe = float(importe_str)
                        linea["total"] = importe
                        if linea.get("cantidad") and linea["cantidad"] > 0:
                            linea["precio_unitario"] = importe / linea["cantidad"]
                    except:
                        pass
            
            # Buscar partida arancelaria (H.S.)
            hs_match = re.search(hs_pattern, texto_desde_articulo, re.IGNORECASE)
            if hs_match:
                linea["partida"] = hs_match.group(1).strip()
            
            # Solo agregar si tiene al menos descripción y cantidad
            if linea.get("descripcion") and linea.get("cantidad"):
                lineas.append(linea)
        
        # Método 2: Buscar formato tabla (ARTICULO DESCRIPCION BULTOS PESO)
        if not lineas:
            tabla_pattern = r'ARTICULO\s+DESCRIPCION\s+BULTOS\s+PESO\s+BRUTO\s+PESO\s+NETO\s*\n\s*(\d+)\s+([^\n]+?)\s+(\d+)\s+C/U\s+(\d+)\s+KG\s+(\d+)\s+KG'
            tabla_match = re.search(tabla_pattern, text, re.IGNORECASE | re.MULTILINE)
            if tabla_match:
                linea = {
                    "articulo": tabla_match.group(1).strip(),
                    "descripcion": tabla_match.group(2).strip(),
                    "cantidad": None,
                    "unidades": None,
                    "precio_unitario": None,
                    "total": None,
                    "bultos": None,
                    "peso_bruto": None,
                    "peso_neto": None,
                }
                
                try:
                    cantidad = int(tabla_match.group(3))
                    linea["cantidad"] = cantidad
                    linea["unidades"] = cantidad
                    linea["bultos"] = cantidad
                except:
                    pass
                
                try:
                    peso_bruto = float(tabla_match.group(4))
                    linea["peso_bruto"] = peso_bruto
                except:
                    pass
                
                try:
                    peso_neto = float(tabla_match.group(5))
                    linea["peso_neto"] = peso_neto
                except:
                    pass
                
                if linea.get("descripcion") and linea.get("cantidad"):
                    lineas.append(linea)
        
        # Método 3: Buscar formato genérico (fallback)
        if not lineas:
            # Buscar números seguidos de descripciones y precios
            line_patterns = [
                # Formato: cantidad descripción precio total
                r'(\d+[.,]?\d*)\s+([A-ZÁÉÍÓÚÑ][^0-9€$]{10,100}?)\s+([\d.,]+)\s*([€$]?)\s+([\d.,]+)\s*([€$]?)',
                # Formato: descripción cantidad precio
                r'([A-ZÁÉÍÓÚÑ][^0-9€$]{10,100}?)\s+(\d+[.,]?\d*)\s+([\d.,]+)\s*([€$]?)',
            ]
            
            for pattern in line_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
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
                            lineas.append(linea)
                            break  # Solo tomar la primera coincidencia válida
        
        # Limitar a máximo 20 líneas para evitar ruido
        return lineas[:20]

    def fill_expediente_from_invoice(self, expediente, invoice_data):
        """
        Rellena los campos de un expediente con los datos extraídos de la factura.
        
        :param expediente: Recordset de aduana.expediente
        :param invoice_data: Diccionario con datos extraídos
        """
        expediente.ensure_one()
        
        # Preparar valores para actualización masiva sin tracking
        vals = {}
        
        # Actualizar número de factura
        if invoice_data.get("numero_factura"):
            vals["numero_factura"] = invoice_data["numero_factura"]
        
        # Actualizar valor de factura
        if invoice_data.get("valor_total"):
            vals["valor_factura"] = invoice_data["valor_total"]
        
        # Actualizar moneda
        if invoice_data.get("moneda"):
            vals["moneda"] = invoice_data["moneda"]
        
        # Actualizar direction (sentido) - PRIORITARIO
        if invoice_data.get("direction"):
            direction = invoice_data.get("direction").lower()
            if direction in ["export", "import"]:
                vals["direction"] = direction
        else:
            # Si no hay direction explícito, intentar determinarlo por países
            pais_origen = invoice_data.get("pais_origen", "").upper()
            pais_destino = invoice_data.get("pais_destino", "").upper()
            if pais_origen == "ES" and pais_destino == "AD":
                vals["direction"] = "export"
            elif pais_origen == "AD" and pais_destino == "ES":
                vals["direction"] = "import"
        
        # Actualizar incoterm
        if invoice_data.get("incoterm"):
            vals["incoterm"] = invoice_data["incoterm"]
        
        # Actualizar países
        if invoice_data.get("pais_origen"):
            vals["pais_origen"] = invoice_data["pais_origen"]
        if invoice_data.get("pais_destino"):
            vals["pais_destino"] = invoice_data["pais_destino"]
        
        # Actualizar campos de transporte
        if invoice_data.get("transportista"):
            vals["transportista"] = invoice_data["transportista"]
        
        if invoice_data.get("matricula"):
            vals["matricula"] = invoice_data["matricula"]
        
        if invoice_data.get("referencia_transporte"):
            vals["referencia_transporte"] = invoice_data["referencia_transporte"]
        
        if invoice_data.get("remolque"):
            vals["remolque"] = invoice_data["remolque"]
        
        if invoice_data.get("codigo_transporte"):
            vals["codigo_transporte"] = invoice_data["codigo_transporte"]
        
        # Buscar o crear remitente
        if invoice_data.get("remitente_nif") or invoice_data.get("remitente_nombre"):
            remitente = self._find_or_create_partner(
                name=invoice_data.get("remitente_nombre"),
                vat=invoice_data.get("remitente_nif"),
                street=invoice_data.get("remitente_direccion")
            )
            if remitente:
                vals["remitente"] = remitente.id
        
        # Buscar o crear consignatario
        if invoice_data.get("consignatario_nif") or invoice_data.get("consignatario_nombre"):
            consignatario = self._find_or_create_partner(
                name=invoice_data.get("consignatario_nombre"),
                vat=invoice_data.get("consignatario_nif"),
                street=invoice_data.get("consignatario_direccion")
            )
            if consignatario:
                vals["consignatario"] = consignatario.id
        
        # Actualizar todos los campos de una vez sin tracking
        if vals:
            expediente.with_context(mail_notrack=True, tracking_disable=True).write(vals)
        
        # Crear líneas de productos si se extrajeron
        if invoice_data.get("lineas"):
            # Limpiar líneas existentes si las hay
            expediente.line_ids.unlink()
            
            # Crear nuevas líneas
            LineModel = self.env["aduana.expediente.line"]
            for idx, linea_data in enumerate(invoice_data["lineas"], start=1):
                # Calcular unidades
                unidades = linea_data.get("unidades") or linea_data.get("cantidad") or 1.0
                
                # Determinar precio unitario (valor_linea debe ser el precio unitario sin descuento)
                precio_unitario_ia = linea_data.get("precio_unitario")
                total_ia = linea_data.get("total")
                
                if precio_unitario_ia:
                    # Si la IA extrajo precio_unitario, usarlo directamente
                    valor_linea = precio_unitario_ia
                elif total_ia and unidades and unidades > 0:
                    # Si solo hay total, calcular precio unitario
                    valor_linea = total_ia / unidades
                else:
                    valor_linea = 0.0
                
                line_vals = {
                    "expediente_id": expediente.id,
                    "item_number": idx,
                    "descripcion": linea_data.get("descripcion", ""),
                    "unidades": unidades,
                    "valor_linea": valor_linea,
                    "pais_origen": expediente.pais_origen or "ES",
                }
                
                # Agregar descuento si está disponible
                if linea_data.get("descuento"):
                    try:
                        descuento = linea_data.get("descuento")
                        if isinstance(descuento, str):
                            descuento = float(descuento.replace('%', '').replace(',', '.'))
                        else:
                            descuento = float(descuento)
                        line_vals["descuento"] = descuento
                    except:
                        pass
                
                # Agregar partida arancelaria si está disponible (OBLIGATORIO)
                if linea_data.get("partida"):
                    # Limpiar y validar partida (debe ser 8-10 dígitos)
                    partida = str(linea_data.get("partida")).strip()
                    # Si tiene menos de 8 dígitos, rellenar con ceros a la izquierda
                    if partida.isdigit() and len(partida) < 8:
                        partida = partida.zfill(8)
                    # Si tiene más de 10 dígitos, truncar
                    if len(partida) > 10:
                        partida = partida[:10]
                    line_vals["partida"] = partida
                else:
                    # Si no hay partida, intentar buscarla en el texto completo
                    _logger.warning("Línea %d: No se encontró partida arancelaria", idx)
                
                # Agregar bultos si está disponible
                if linea_data.get("bultos"):
                    line_vals["bultos"] = int(linea_data.get("bultos"))
                elif linea_data.get("cantidad"):
                    # Si no hay bultos explícitos, usar cantidad como bultos
                    try:
                        line_vals["bultos"] = int(linea_data.get("cantidad"))
                    except:
                        pass
                
                # Agregar pesos si están disponibles directamente
                if linea_data.get("peso_bruto"):
                    line_vals["peso_bruto"] = float(linea_data.get("peso_bruto"))
                if linea_data.get("peso_neto"):
                    line_vals["peso_neto"] = float(linea_data.get("peso_neto"))
                
                # Si no hay peso directo, intentar extraerlo de la descripción
                if not line_vals.get("peso_bruto") and not line_vals.get("peso_neto"):
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
        
        # Guardar datos extraídos como texto para referencia técnica (sin tracking)
        expediente.with_context(mail_notrack=True, tracking_disable=True).write({
            'factura_datos_extraidos': json.dumps(invoice_data, indent=2, ensure_ascii=False),
            'factura_procesada': True
        })
        
        # Agregar información técnica al chatter
        metodo_usado = invoice_data.get("metodo_usado", "Desconocido")
        num_lineas = len(invoice_data.get("lineas", []))
        texto_extraido_len = len(invoice_data.get("texto_extraido", ""))
        
        # Crear mensaje técnico para el chatter
        mensaje_tecnico = _("""
<b>📋 Información Técnica de Extracción de Factura</b>

<b>Método usado:</b> %s
<b>Líneas extraídas:</b> %d
<b>Tamaño del texto extraído:</b> %d caracteres

<b>Datos técnicos completos (JSON):</b>
<pre style="background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px; overflow-x: auto; font-size: 10px; white-space: pre-wrap; word-wrap: break-word;">%s</pre>

<i>Nota: Los datos técnicos completos también están disponibles en la pestaña "Datos Técnicos Factura" del expediente.</i>
        """) % (
            metodo_usado,
            num_lineas,
            texto_extraido_len,
            json.dumps(invoice_data, indent=2, ensure_ascii=False)
        )
        
        expediente.with_context(mail_notrack=True).message_post(
            body=mensaje_tecnico,
            subtype_xmlid='mail.mt_note',
            author_id=False,  # Sistema
        )
        
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

