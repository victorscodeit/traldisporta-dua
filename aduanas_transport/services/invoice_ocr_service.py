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
        :return: Diccionario con datos extraídos
        """
        if not pdf_data:
            raise UserError(_("No se proporcionó ningún archivo PDF"))
        
        # Obtener API key de configuración si no se proporciona
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('aduanas_transport.google_vision_api_key')
        
        if api_key:
            try:
                return self._extract_with_google_vision(pdf_data, api_key)
            except Exception as e:
                _logger.warning("Error con Google Vision, intentando OCR alternativo: %s", e)
                return self._extract_with_fallback_ocr(pdf_data)
        else:
            # Usar OCR alternativo si no hay API key
            return self._extract_with_fallback_ocr(pdf_data)

    def _extract_with_google_vision(self, pdf_data, api_key):
        """
        Extrae datos usando Google Cloud Vision API.
        Requiere: pip install google-cloud-vision
        
        La API key puede ser:
        1. Ruta a un archivo JSON de Service Account (ej: /path/to/credentials.json)
        2. Una API Key directa (para usar con REST API)
        
        Nota: Para PDFs, Google Vision funciona mejor con Service Account JSON.
        Para API keys directas, se usa la API REST.
        """
        try:
            from google.cloud import vision
            from google.oauth2 import service_account
            import os
            import json
            
            # Convertir base64 a bytes si es necesario
            if isinstance(pdf_data, str):
                pdf_bytes = base64.b64decode(pdf_data)
            else:
                pdf_bytes = pdf_data
            
            # Determinar si api_key es una ruta a archivo JSON o una API key directa
            client = None
            if api_key:
                # Verificar si es una ruta a archivo JSON
                if os.path.exists(api_key) and api_key.endswith('.json'):
                    # Es un archivo de Service Account JSON
                    try:
                        credentials = service_account.Credentials.from_service_account_file(api_key)
                        client = vision.ImageAnnotatorClient(credentials=credentials)
                        _logger.info("Usando Google Vision con Service Account JSON")
                    except Exception as cred_error:
                        _logger.warning("Error cargando Service Account JSON: %s. Intentando variable de entorno.", cred_error)
                        # Intentar con variable de entorno si existe
                        if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
                            client = vision.ImageAnnotatorClient()
                        else:
                            raise
                elif api_key.startswith('{') or api_key.startswith('['):
                    # Es un JSON string (credenciales como texto)
                    try:
                        creds_dict = json.loads(api_key)
                        credentials = service_account.Credentials.from_service_account_info(creds_dict)
                        client = vision.ImageAnnotatorClient(credentials=credentials)
                        _logger.info("Usando Google Vision con Service Account JSON (string)")
                    except Exception as cred_error:
                        _logger.warning("Error parseando JSON de credenciales: %s", cred_error)
                        raise
                else:
                    # Asumir que es una ruta a archivo o variable de entorno
                    if os.path.exists(api_key):
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_key
                    else:
                        # Intentar usar como variable de entorno directamente
                        if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
                            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_key
                    client = vision.ImageAnnotatorClient()
            
            if not client:
                # Intentar sin credenciales explícitas (usará variable de entorno o credenciales por defecto)
                try:
                    client = vision.ImageAnnotatorClient()
                except Exception as cred_error:
                    _logger.warning("Error al inicializar Google Vision client: %s. Usando OCR alternativo.", cred_error)
                    return self._extract_with_fallback_ocr(pdf_data)
            
            # Para PDFs, Google Vision requiere usar async_annotate_file o convertir a imágenes
            # Intentamos primero con document_text_detection (puede funcionar con algunos PDFs)
            try:
                # Intentar procesar como imagen (primera página del PDF)
                # Nota: Para PDFs completos, usar pdfplumber es más adecuado
                image = vision.Image(content=pdf_bytes)
                response = client.document_text_detection(image=image)
                
                if response.error.message:
                    raise Exception(f"Error de Google Vision: {response.error.message}")
                
                # Extraer texto completo
                full_text = response.full_text_annotation.text if response.full_text_annotation else ""
                
                # Si no hay texto, usar OCR alternativo
                if not full_text:
                    _logger.info("Google Vision no extrajo texto del PDF, usando OCR alternativo.")
                    return self._extract_with_fallback_ocr(pdf_data)
                
                # Parsear datos de la factura
                return self._parse_invoice_text(full_text)
            except Exception as proc_error:
                _logger.warning("Error procesando con Google Vision: %s. Usando OCR alternativo.", proc_error)
                return self._extract_with_fallback_ocr(pdf_data)
            
        except ImportError:
            _logger.warning("google-cloud-vision no está instalado. Usando OCR alternativo.")
            return self._extract_with_fallback_ocr(pdf_data)
        except Exception as e:
            _logger.exception("Error con Google Vision API: %s", e)
            # En caso de error, intentar con OCR alternativo
            return self._extract_with_fallback_ocr(pdf_data)

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
                
                full_text = ""
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                for page in pdf_reader.pages:
                    full_text += page.extract_text() + "\n"
                
                return self._parse_invoice_text(full_text)
                
            except ImportError:
                raise UserError(_("Se requiere instalar pdfplumber o PyPDF2 para procesar PDFs. Ejecute: pip install pdfplumber"))
        except Exception as e:
            _logger.exception("Error al extraer texto del PDF: %s", e)
            raise UserError(_("Error al procesar el PDF: %s") % str(e))

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
        
        # Intentar extraer líneas de productos (más complejo, requiere análisis de tablas)
        # Por ahora, dejamos esto para una implementación más avanzada con IA
        
        return data

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

