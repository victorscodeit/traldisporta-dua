import logging
import base64
import json
import re
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from odoo import models, fields, _
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
        
        # Obtener API key de configuración del módulo si no se proporciona
        if not api_key:
            # Leer desde la configuración del módulo usando el método helper
            config_settings = self.env['res.config.settings']
            api_key = config_settings.get_openai_api_key()
            if api_key:
                _logger.info("API key obtenida de configuración del módulo Aduanas (longitud: %d caracteres)", len(api_key) if api_key else 0)
            else:
                _logger.warning("No se encontró API key de OpenAI en la configuración del módulo Aduanas. Verifica en Aduanas > Configuración")
        
        resultado = None
        metodo_usado = None
        
        # PRIORIDAD: Intentar OpenAI GPT-4o Vision primero (si hay API key)
        if api_key:
            _logger.info("API key disponible. Iniciando procesamiento con GPT-4o Vision...")
            try:
                _logger.info("Enviando PDF a OpenAI GPT-4o Vision con splitting por páginas...")
                resultado = self._extract_with_openai_vision(api_key, pdf_bytes)
                metodo_usado = resultado.get("metodo_usado") or "OpenAI GPT-4o Vision (estructurado)"
                _logger.info("OpenAI GPT-4o Vision procesó el PDF exitosamente (%s)", metodo_usado)
            except Exception as e:
                error_gpt = str(e)
                _logger.warning("Error con OpenAI GPT-4o Vision: %s. Intentando OCR alternativo...", error_gpt)
                
                # Si el error es que no se pudo extraer texto, puede ser una imagen escaneada
                # En ese caso, el OCR alternativo tampoco funcionará, así que mejor informar claramente
                if "No se pudo extraer texto" in error_gpt or "ninguna página" in error_gpt.lower():
                    _logger.warning("GPT Vision no pudo extraer texto. El PDF puede ser una imagen escaneada de baja calidad o tener problemas.")
                    # Intentar OCR alternativo de todas formas por si acaso
                    try:
                        resultado = self._extract_with_fallback_ocr(pdf_bytes)
                        texto_extraido = resultado.get("texto_extraido", "").strip() if resultado else ""
                        if not texto_extraido or len(texto_extraido) < 10:
                            # OCR alternativo tampoco funcionó, es definitivamente una imagen escaneada
                            return {
                                "error": _("El PDF parece ser una imagen escaneada y no se pudo extraer texto.\n\n"
                                          "Error GPT Vision: %s\n\n"
                                          "Sugerencias:\n"
                                          "- Verifica que la API key de OpenAI sea válida\n"
                                          "- Asegúrate de que el PDF tenga buena calidad\n"
                                          "- Verifica tu conexión a internet\n"
                                          "- Revisa los logs del servidor para más detalles") % error_gpt,
                                "texto_extraido": "",
                                "metodo_usado": "Error - PDF escaneado"
                            }
                        else:
                            metodo_usado = "OCR Alternativo (fallback - GPT Vision falló)"
                    except Exception as e2:
                        _logger.exception("Error también con OCR alternativo: %s", e2)
                        return {
                            "error": _("No se pudo extraer texto del PDF (parece ser una imagen escaneada).\n\n"
                                      "Error GPT Vision: %s\n"
                                      "Error OCR Alternativo: %s\n\n"
                                      "Sugerencias:\n"
                                      "- Verifica que la API key de OpenAI sea válida\n"
                                      "- El PDF puede estar corrupto o ser de muy baja calidad\n"
                                      "- Revisa los logs del servidor para más detalles") % (error_gpt, str(e2)),
                            "texto_extraido": "",
                            "metodo_usado": "Error en ambos"
                        }
                else:
                    # Otro tipo de error (API, conexión, etc.), intentar OCR alternativo
                    try:
                        resultado = self._extract_with_fallback_ocr(pdf_bytes)
                        metodo_usado = "OCR Alternativo (fallback)"
                    except Exception as e2:
                        _logger.exception("Error también con OCR alternativo: %s", e2)
                        return {
                            "error": _("Error al procesar PDF:\n\n"
                                      "GPT Vision: %s\n"
                                      "OCR Alternativo: %s\n\n"
                                      "Revisa los logs del servidor para más detalles.") % (error_gpt, str(e2)),
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
        Extrae datos con GPT-4o Vision en una sola pasada por página (imagen → JSON).
        Páginas en paralelo; reintento dirigido si falla la coherencia.
        Requiere: pip install openai PyMuPDF
        """
        try:
            from openai import OpenAI
            import fitz  # PyMuPDF

            if not api_key:
                raise ValueError("API key de OpenAI no proporcionada")

            client = OpenAI(api_key=api_key)

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

            page_images = []
            mat = fitz.Matrix(250 / 72, 250 / 72)  # 250 DPI: mejor lectura de dígitos en tablas
            for page_num in range(num_pages):
                page = pdf_document[page_num]
                pix = page.get_pixmap(matrix=mat)
                img_base64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                page_images.append(img_base64)
                pix = None
            pdf_document.close()

            max_workers = min(4, max(1, num_pages))
            _logger.info(
                "Extracción estructurada Vision→JSON en paralelo (%d página(s), max_workers=%d)...",
                num_pages,
                max_workers,
            )

            page_results = [None] * num_pages
            errores_paginas = []

            def _process_page(page_idx):
                return page_idx, self._extract_page_structured_json(
                    client, page_images[page_idx], page_idx + 1, num_pages
                )

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_page, i): i for i in range(num_pages)}
                for future in as_completed(futures):
                    page_idx = futures[future]
                    try:
                        idx, page_data = future.result()
                        if page_data:
                            page_results[idx] = page_data
                            n_lines = len(page_data.get("lineas") or [])
                            _logger.info(
                                "Página %d/%d estructurada: %d línea(s), texto=%d chars",
                                idx + 1,
                                num_pages,
                                n_lines,
                                len(page_data.get("texto_pagina") or ""),
                            )
                        else:
                            errores_paginas.append(f"Página {page_idx + 1}: respuesta vacía")
                    except Exception as page_err:
                        _logger.error("Error página %d: %s", page_idx + 1, page_err)
                        errores_paginas.append(f"Página {page_idx + 1}: {page_err}")

            successful_pages = [p for p in page_results if p]
            if not successful_pages:
                if errores_paginas:
                    error_detalle = "\n".join(errores_paginas[:3])
                    if len(errores_paginas) > 3:
                        error_detalle += f"\n... y {len(errores_paginas) - 3} error(es) más"
                    raise Exception(_(
                        "No se pudo extraer texto de ninguna página del PDF.\n\n"
                        "Errores encontrados:\n%s\n\n"
                        "Posibles causas:\n"
                        "- Problemas de conexión con OpenAI API\n"
                        "- La API key no es válida o ha expirado\n"
                        "- El PDF está corrupto o protegido\n"
                        "- Límites de rate limit de OpenAI alcanzados"
                    ) % error_detalle)
                raise Exception(_(
                    "No se pudo extraer texto de ninguna página del PDF. "
                    "El PDF puede estar vacío, ser solo imágenes sin texto, o estar corrupto."
                ))

            structured_data = self._merge_page_extractions(page_results)
            structured_data = self._normalize_structured_invoice_data(structured_data)

            full_text = structured_data.get("texto_extraido") or ""
            _logger.info(
                "Merge Vision→JSON: %d chars, %d líneas de %d/%d página(s)",
                len(full_text),
                len(structured_data.get("lineas") or []),
                len(successful_pages),
                num_pages,
            )

            issues = self._detect_extraction_issues(structured_data)
            if issues:
                _logger.warning("Inconsistencias tras extracción: %s. Reintento dirigido...", issues)
                try:
                    fixed = self._retry_fix_structured_data(
                        api_key, full_text, structured_data, issues
                    )
                    if fixed:
                        fixed["texto_extraido"] = full_text
                        structured_data = self._normalize_structured_invoice_data(fixed)
                        issues_after = self._detect_extraction_issues(structured_data)
                        if issues_after:
                            _logger.warning("Tras reintento siguen issues: %s", issues_after)
                        else:
                            _logger.info("Reintento dirigido corrigió las inconsistencias")
                except Exception as retry_err:
                    _logger.warning("Reintento dirigido falló: %s", retry_err)

            # Si faltan datos críticos, fallback al interpretador texto→JSON (mismo esquema)
            if not structured_data.get("lineas") and full_text.strip():
                _logger.warning("Sin líneas tras Vision→JSON; fallback interpret_text_with_gpt...")
                try:
                    fallback = self._interpret_text_with_gpt(api_key, full_text)
                    if fallback and fallback.get("lineas"):
                        fallback["texto_extraido"] = full_text
                        structured_data = fallback
                except Exception as fb_err:
                    _logger.warning("Fallback interpret_text falló: %s", fb_err)

            if not structured_data.get("lineas") and not structured_data.get("numero_factura"):
                _logger.warning("Usando parsing regex como último recurso")
                parsed = self._parse_invoice_text(full_text)
                if parsed.get("lineas") or parsed.get("numero_factura"):
                    parsed["metodo_usado"] = "OpenAI GPT-4o Vision (regex fallback)"
                    return parsed

            structured_data["metodo_usado"] = "OpenAI GPT-4o Vision (estructurado)"
            if errores_paginas:
                structured_data["_avisos_paginas"] = errores_paginas
            return structured_data

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

    def _invoice_structured_json_schema_text(self):
        """Esquema JSON canónico (mismo contrato que el interpretador texto→JSON)."""
        return """{
  "numero_factura": "número o null",
  "fecha_factura": "DD.MM.YYYY o DD/MM/YYYY o null",
  "remitente_nombre": "nombre completo de la empresa emisora o null",
  "remitente_nif": "NIF/CIF español (formato A12345678) o NIF andorrano (L123456H) o null",
  "remitente_direccion": "dirección completa o null",
  "consignatario_nombre": "nombre completo del destinatario o null",
  "consignatario_nif": "NIF/CIF o null",
  "consignatario_direccion": "dirección completa o null",
  "valor_total": "número decimal o null (TOTAL FACTURA; suele estar en la última página)",
  "moneda": "EUR o USD o null",
  "incoterm": "EXW, FCA, CPT, CIP, DAP, DPU, DDP o null (CIF→CIP, FOB→FCA, CFR→CPT)",
  "pais_origen": "código ISO de 2 letras o null",
  "pais_destino": "código ISO de 2 letras o null",
  "direction": "export o import o null",
  "transportista": "nombre del transportista o null",
  "matricula": "matrícula del vehículo o null",
  "referencia_transporte": "referencia o número de transporte o null",
  "remolque": "matrícula del remolque o null",
  "codigo_transporte": "código del transporte o null",
  "lineas": [
    {
      "articulo": "código del artículo o null",
      "descripcion": "descripción completa del producto",
      "cantidad": "número decimal (= Cant. / columna unidades)",
      "unidades": "número decimal (igual que cantidad)",
      "precio_lista": "precio lista/bruto unitario o null",
      "precio_unitario": "precio NETO unitario (columna tras la cantidad), NO el importe/cantidad",
      "total": "Importe de línea (última columna)",
      "subtotal": "número decimal o null",
      "descuento": "porcentaje de descuento (ej. 5.00) o null",
      "partida": "código H.S. 8-10 dígitos o null",
      "bultos": "número entero o null",
      "peso_bruto": "número decimal en KG o null",
      "peso_neto": "número decimal en KG o null"
    }
  ],
  "texto_pagina": "transcripción COMPLETA de TODO el texto visible de ESTA página"
}"""

    def _extract_page_structured_json(self, client, img_base64, page_num, num_pages):
        """Una página: Vision → JSON estructurado (+ texto_pagina para texto_extraido)."""
        schema = self._invoice_structured_json_schema_text()
        prompt = (
            "Eres un experto en facturas comerciales para documentos aduaneros (DUA).\n\n"
            f"Esta es la página {page_num} de {num_pages} de UNA factura comercial.\n"
            "Extrae en UNA sola respuesta JSON estricto:\n"
            "1) Todos los campos de cabecera visibles en ESTA página (null si no aparecen aquí).\n"
            "2) TODAS las líneas de producto de ESTA página (ninguna omitida).\n"
            "3) texto_pagina: transcripción literal COMPLETA de todo el texto visible.\n\n"
            "IMPORTANTE IMPORTES POR LÍNEA (lee dígito a dígito; no inventes):\n"
            "- Columnas típicas: Precio lista | Cantidad | Precio neto | %Dto | Importe.\n"
            "- También aparece 'Cant. N' bajo la descripción: DEBE coincidir con la columna Cantidad.\n"
            "- Ejemplo real: Cant. 12 | 2,30 | 12 | 1,57 | 5,00 | 17,90\n"
            "  → cantidad=12, precio_lista=2.30, precio_unitario=1.57, descuento=5, total=17.90\n"
            "- VALIDACIÓN OBLIGATORIA: precio_unitario × cantidad × (1 − descuento/100) ≈ total\n"
            "  (1.57×12×0.95 = 17.90). Si no cuadra, relee las columnas de ESA línea.\n"
            "- 'precio_unitario' = precio NETO impreso (1.57), NO Importe/Cantidad ni precio lista.\n"
            "- 'total' = Importe (17.90). Decimales con punto. Lee 3,40 como 3.40 y 25,84 como 25.84.\n"
            "- NUNCA multipliques ni dividas importes por 100 u otro factor; copia el valor de la factura.\n\n"
            "IGNORA secciones 'Pedido pendiente' / 'Pedidos pendientes' / Pending order.\n"
            "Si es página de continuación (solo tabla), cabecera en null y líneas sí.\n"
            "valor_total solo si el TOTAL de factura aparece en ESTA página.\n"
            "Responde ÚNICAMENTE con JSON válido (sin markdown).\n\n"
            f"FORMATO:\n{schema}"
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un experto en extracción de datos de facturas. "
                        "Responde ÚNICAMENTE con JSON válido, sin markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=16000,
            response_format={"type": "json_object"},
            timeout=90.0,
        )
        if not response or not response.choices:
            return None
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return None
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        data = json.loads(content.strip())
        if not isinstance(data, dict):
            return None
        if "lineas" in data and not isinstance(data["lineas"], list):
            data["lineas"] = []
        return data

    def _merge_page_extractions(self, page_results):
        """Combina extracciones por página preservando el mismo contrato de campos."""
        header_keys = [
            "numero_factura", "fecha_factura",
            "remitente_nombre", "remitente_nif", "remitente_direccion",
            "consignatario_nombre", "consignatario_nif", "consignatario_direccion",
            "moneda", "incoterm", "pais_origen", "pais_destino", "direction",
            "transportista", "matricula", "referencia_transporte", "remolque", "codigo_transporte",
        ]
        merged = {k: None for k in header_keys}
        merged["valor_total"] = None
        merged["lineas"] = []
        textos = []

        for page_data in page_results:
            if not page_data:
                continue
            for key in header_keys:
                if merged.get(key) in (None, "", []) and page_data.get(key) not in (None, "", []):
                    merged[key] = page_data.get(key)
            # Preferir el último valor_total no nulo (suele ir al final)
            if page_data.get("valor_total") not in (None, "", []):
                merged["valor_total"] = page_data.get("valor_total")
            for linea in page_data.get("lineas") or []:
                if isinstance(linea, dict):
                    merged["lineas"].append(linea)
            texto = page_data.get("texto_pagina") or ""
            if texto.strip():
                textos.append(texto.strip())

        merged["texto_extraido"] = "\n\n".join(textos)
        return merged

    def _detect_extraction_issues(self, data):
        """Detecta inconsistencias que justifican un reintento dirigido."""
        issues = []
        if not data:
            return ["sin_datos"]
        lineas = data.get("lineas") or []
        if not lineas:
            issues.append("sin_lineas")
        for idx, lin in enumerate(lineas, 1):
            try:
                if not self._line_discount_math_ok(lin):
                    cantidad = float(lin.get("cantidad") or lin.get("unidades") or 0)
                    total = lin.get("total")
                    if total in (None, ""):
                        total = lin.get("subtotal")
                    precio = lin.get("precio_unitario")
                    dto = lin.get("descuento")
                    issues.append(
                        f"linea_{idx}_precio_incoherente: precio={precio} cant={cantidad} "
                        f"dto={dto} total={total} "
                        "(debe cumplir precio×cant×(1-dto/100)≈total)"
                    )
                    if len([i for i in issues if i.startswith("linea_")]) >= 5:
                        break
            except (TypeError, ValueError):
                continue
        valor_total = data.get("valor_total")
        if valor_total not in (None, "") and lineas:
            try:
                total = float(valor_total)
                suma = 0.0
                for lin in lineas:
                    val = lin.get("total")
                    if val in (None, ""):
                        val = lin.get("subtotal")
                    if val not in (None, ""):
                        suma += float(val)
                if suma > 0 and abs(suma - total) > max(0.5, total * 0.02):
                    issues.append(
                        f"totales_incoherentes: suma_lineas={suma:.2f} vs valor_total={total:.2f}"
                    )
            except (TypeError, ValueError):
                issues.append("valor_total_no_numerico")
        if not data.get("numero_factura") and not data.get("remitente_nombre") and not data.get("remitente_nif"):
            issues.append("cabecera_incompleta")
        if not (data.get("texto_extraido") or "").strip():
            issues.append("sin_texto_extraido")
        return issues

    def _retry_fix_structured_data(self, api_key, full_text, current_data, issues):
        """
        Segunda pasada SOLO con el error concreto (texto ya extraído + JSON previo).
        No re-envía imágenes: corrige el JSON manteniendo o mejorando la información.
        """
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        schema = self._invoice_structured_json_schema_text()
        # No reenviar texto_pagina en el resultado final esperado
        current_clean = {k: v for k, v in (current_data or {}).items() if k != "texto_pagina"}
        prompt = (
            "Eres un experto en facturas comerciales para DUA.\n"
            "Corrige el JSON de extracción de factura según los problemas detectados.\n"
            "Debes devolver el MISMO esquema (o superior en completitud): no elimines campos ni líneas correctas.\n"
            "Si faltan líneas, recupéralas del texto. Si el total no cuadra, revisa líneas y valor_total.\n"
            "Si precio_unitario * cantidad * (1-descuento/100) != total, relee las columnas del texto.\n"
            "Ejemplo: 1.57 * 12 * 0.95 = 17.90 → cantidad=12, precio_unitario=1.57, descuento=5, total=17.90.\n"
            "Lee los decimales tal cual (3,40 → 3.40; 25,84 → 25.84). No multipliques ni dividas importes.\n"
            "En tablas Precio|Cant|Neto|%Dto|Importe: precio_unitario=Neto, total=Importe.\n"
            "IGNORA 'Pedido pendiente'. Responde ÚNICAMENTE JSON válido.\n\n"
            f"PROBLEMAS DETECTADOS:\n- " + "\n- ".join(issues) + "\n\n"
            f"ESQUEMA OBJETIVO:\n{schema}\n\n"
            f"JSON ACTUAL (a corregir):\n{json.dumps(current_clean, ensure_ascii=False)[:80000]}\n\n"
            f"TEXTO COMPLETO DE LA FACTURA:\n{(full_text or '')[:120000]}"
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Responde ÚNICAMENTE con JSON válido de factura, sin markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=16000,
            response_format={"type": "json_object"},
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return None
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        if "lineas" in data and not isinstance(data["lineas"], list):
            data["lineas"] = []
        return data

    def _parse_invoice_number(self, value):
        """
        Parsea importes/cantidades de factura.
        Soporta: 9.97 | 9,97 | 1.234,56 | 1,234.56 | ya float.
        Evita el bug de tratar '1.65' como miles → 165.
        """
        if value in (None, "", False):
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        s = str(value).strip().replace("€", "").replace("EUR", "").replace("%", "").strip()
        if not s:
            return None
        s = s.replace(" ", "").replace("\u00a0", "")
        try:
            if "," in s and "." in s:
                if s.rfind(",") > s.rfind("."):
                    # 1.234,56
                    s = s.replace(".", "").replace(",", ".")
                else:
                    # 1,234.56
                    s = s.replace(",", "")
            elif "," in s:
                # 9,97 o 1.234 mal escrito como 1234,56
                s = s.replace(".", "").replace(",", ".")
            elif "." in s:
                parts = s.split(".")
                # Solo punto decimal (1.65 / 9.97) vs miles (1.234)
                if len(parts) == 2 and len(parts[-1]) <= 2:
                    pass  # decimal point
                elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                    s = s.replace(".", "")
                # si no, dejar el float natural
            return float(s)
        except (TypeError, ValueError):
            return None

    def _reconcile_line_amounts(self, linea):
        """
        Prioriza importe de línea y precio NETO impreso.
        Con descuento: precio_neto × cantidad × (1 − dto/100) ≈ total
        (ej. 1.57 × 12 × 0.95 = 17.90).
        """
        if not isinstance(linea, dict):
            return linea

        cantidad = self._parse_invoice_number(linea.get("cantidad") or linea.get("unidades"))
        total = self._parse_invoice_number(linea.get("total"))
        if total is None:
            total = self._parse_invoice_number(linea.get("subtotal"))
        precio = self._parse_invoice_number(linea.get("precio_unitario"))
        if precio is None:
            precio = self._parse_invoice_number(linea.get("precio_neto"))
        precio_lista = self._parse_invoice_number(linea.get("precio_lista"))
        descuento = self._parse_invoice_number(linea.get("descuento"))

        if cantidad is not None and cantidad > 0:
            linea["cantidad"] = cantidad
            linea["unidades"] = cantidad

        if total is not None:
            linea["total"] = total
        if linea.get("subtotal") not in (None, ""):
            sub = self._parse_invoice_number(linea.get("subtotal"))
            if sub is not None:
                linea["subtotal"] = sub
        if descuento is not None:
            linea["descuento"] = descuento
        if precio_lista is not None:
            linea["precio_lista"] = precio_lista

        def _almost(a, b):
            return abs(a - b) <= max(0.05, abs(b) * 0.015)

        # Caso preferido: precio neto + dto cuadran con el importe
        if (
            total is not None
            and cantidad
            and cantidad > 0
            and precio is not None
            and descuento is not None
            and 0 <= descuento < 100
        ):
            esperado = precio * cantidad * (1.0 - (descuento / 100.0))
            if _almost(esperado, total):
                linea["precio_unitario"] = precio
                return linea
            # Si el precio no cuadra pero el importe sí, deducir neto desde importe
            factor = 1.0 - (descuento / 100.0)
            if factor > 0:
                neto_desde_total = total / (cantidad * factor)
                # Preferir neto deducido si el precio leído parece otra columna (lista)
                if precio_lista is not None and _almost(precio, precio_lista):
                    linea["precio_unitario"] = round(neto_desde_total, 6)
                    return linea
                if not _almost(esperado, total):
                    linea["precio_unitario"] = round(neto_desde_total, 6)
                    return linea

        if total is not None and cantidad and cantidad > 0:
            if precio is not None and _almost(precio * cantidad, total):
                linea["precio_unitario"] = precio
            elif precio is None or not _almost(precio * cantidad, total):
                # Sin dto coherente: precio efectivo = total/cantidad
                if precio is not None:
                    _logger.info(
                        "Corrigiendo precio_unitario de línea '%s': %s → %.4f "
                        "(total=%.2f, cantidad=%s)",
                        (linea.get("descripcion") or linea.get("articulo") or "")[:60],
                        precio,
                        total / cantidad,
                        total,
                        cantidad,
                    )
                linea["precio_unitario"] = round(total / cantidad, 6)
            else:
                linea["precio_unitario"] = precio
        elif precio is not None:
            linea["precio_unitario"] = precio
            if total is None and cantidad and cantidad > 0:
                if descuento is not None and 0 <= descuento < 100:
                    linea["total"] = round(
                        precio * cantidad * (1.0 - descuento / 100.0), 2
                    )
                else:
                    linea["total"] = round(precio * cantidad, 2)

        return linea

    def _line_discount_math_ok(self, lin):
        """True si precio×cant×(1-dto/100)≈total o precio×cant≈total."""
        cantidad = self._parse_invoice_number(lin.get("cantidad") or lin.get("unidades"))
        total = self._parse_invoice_number(lin.get("total"))
        if total is None:
            total = self._parse_invoice_number(lin.get("subtotal"))
        precio = self._parse_invoice_number(lin.get("precio_unitario"))
        descuento = self._parse_invoice_number(lin.get("descuento"))
        if not cantidad or cantidad <= 0 or total is None or precio is None:
            return False
        if descuento is not None and 0 <= descuento < 100:
            esperado = precio * cantidad * (1.0 - descuento / 100.0)
            if abs(esperado - total) <= max(0.05, abs(total) * 0.015):
                return True
        return abs((precio * cantidad) - total) <= max(0.05, abs(total) * 0.015)

    def _parse_solnatural_style_lines_from_texto(self, texto):
        """
        Parsea líneas tipo:
        990505 DESC No Lote: ... Cant. 6 1,66 6 1,60 5,00 9,97
        → articulo, cantidad, precio_lista, precio_neto, descuento%, importe
        """
        if not texto:
            return []
        pattern = re.compile(
            r"(?P<art>\d{5,8})\s+"
            r"(?P<desc>.+?)\s+"
            r"(?:No\s*Lote:\s*\S+\s+Cad\.\s*\S+\s+)?"
            r"Cant\.\s*(?P<cant>\d+[.,]?\d*)\s+"
            r"(?P<p_lista>\d+[.,]\d+)\s+"
            r"(?P<cant2>\d+[.,]?\d*)\s+"
            r"(?P<p_neto>\d+[.,]\d+)\s+"
            r"(?P<dto>\d+[.,]\d+)\s+"
            r"(?P<importe>\d+[.,]\d+)",
            re.IGNORECASE | re.DOTALL,
        )
        parsed = []
        for match in pattern.finditer(texto):
            art = match.group("art")
            cant = self._parse_invoice_number(match.group("cant"))
            cant2 = self._parse_invoice_number(match.group("cant2"))
            p_lista = self._parse_invoice_number(match.group("p_lista"))
            p_neto = self._parse_invoice_number(match.group("p_neto"))
            dto = self._parse_invoice_number(match.group("dto"))
            importe = self._parse_invoice_number(match.group("importe"))
            if not cant or cant <= 0 or importe is None or p_neto is None:
                continue
            # La cantidad de columna debe coincidir con Cant. (tolerancia OCR)
            if cant2 is not None and abs(cant2 - cant) > 0.01:
                cant = cant2 if abs(cant2) >= 1 else cant
            desc = re.sub(r"\s+", " ", (match.group("desc") or "").strip())
            # Solo aceptar si la matemática de la factura cuadra
            # precio_neto × cant × (1 − dto/100) ≈ importe
            ok = False
            if dto is not None and 0 <= dto < 100:
                esperado = p_neto * cant * (1.0 - dto / 100.0)
                if abs(esperado - importe) <= max(0.06, abs(importe) * 0.02):
                    ok = True
            if not ok and abs((p_neto * cant) - importe) <= max(0.06, abs(importe) * 0.02):
                ok = True
            if not ok:
                # Texto OCR incoherente (dígitos mal leídos): descartar
                continue
            parsed.append({
                "articulo": art,
                "descripcion": desc,
                "cantidad": cant,
                "unidades": cant,
                "precio_lista": p_lista,
                "precio_neto": p_neto,
                "descuento": dto,
                "total": importe,
                # Precio unitario = neto impreso (1.57), no importe/cantidad
                "precio_unitario": p_neto,
            })
        return parsed

    def _repair_line_amounts_from_texto(self, data):
        """
        Si el texto OCR trae el patrón Cant./Importe, corrige cantidad/total/precio
        de las líneas Vision que no cuadren con el texto (columna o dígito mal leído).
        """
        texto = data.get("texto_extraido") or ""
        parsed = self._parse_solnatural_style_lines_from_texto(texto)
        if not parsed:
            return data

        by_art = {p["articulo"]: p for p in parsed if p.get("articulo")}
        repaired = 0
        for lin in data.get("lineas") or []:
            if not isinstance(lin, dict):
                continue
            art = str(lin.get("articulo") or "").strip()
            src = by_art.get(art) if art else None
            if not src:
                desc = (lin.get("descripcion") or "").upper()
                for p in parsed:
                    if p["descripcion"].upper()[:40] in desc or desc[:40] in p["descripcion"].upper():
                        src = p
                        break
            if not src:
                continue

            old_total = self._parse_invoice_number(lin.get("total"))
            old_precio = self._parse_invoice_number(lin.get("precio_unitario"))
            old_cant = self._parse_invoice_number(lin.get("cantidad") or lin.get("unidades"))
            new_total = src["total"]
            new_precio = src["precio_unitario"]
            # Reparar si cantidad/importe/precio no coinciden con el texto o no cuadra la matemática
            needs_fix = False
            if old_cant is not None and abs(old_cant - src["cantidad"]) > 0.01:
                needs_fix = True
            elif old_total is not None and new_total and abs(old_total - new_total) > 0.05:
                needs_fix = True
            elif old_precio is not None and new_precio and abs(old_precio - new_precio) > 0.02:
                needs_fix = True
            elif not self._line_discount_math_ok(lin):
                needs_fix = True

            if needs_fix:
                lin["cantidad"] = src["cantidad"]
                lin["unidades"] = src["cantidad"]
                lin["total"] = new_total
                lin["precio_unitario"] = new_precio
                if src.get("precio_lista") is not None:
                    lin["precio_lista"] = src["precio_lista"]
                if src.get("precio_neto") is not None:
                    lin["precio_neto"] = src["precio_neto"]
                if src.get("descuento") is not None:
                    lin["descuento"] = src["descuento"]
                if not lin.get("articulo"):
                    lin["articulo"] = src["articulo"]
                repaired += 1

        if repaired:
            _logger.info(
                "Reparadas %d líneas de importes desde patrón Cant./Importe del texto OCR",
                repaired,
            )
            # Si el valor_total no cuadra con la suma de importes del texto, usar esa suma
            if len(parsed) >= 5:
                suma = sum(p["total"] for p in parsed if p.get("total") is not None)
                vt = self._parse_invoice_number(data.get("valor_total"))
                if suma > 0 and (vt is None or abs(vt - suma) > max(1.0, suma * 0.05)):
                    data["valor_total"] = round(suma, 2)
        return data

    def _normalize_structured_invoice_data(self, data):
        """Normaliza el JSON de factura al contrato consumido por apply_invoice_data."""
        if not data or not isinstance(data, dict):
            return data

        if "lineas" in data and not isinstance(data["lineas"], list):
            data["lineas"] = []

        if data.get("direction"):
            direction = str(data["direction"]).lower() if data["direction"] else None
            if direction and direction not in ["export", "import"]:
                pais_origen = (data.get("pais_origen") or "").upper() if data.get("pais_origen") else ""
                pais_destino = (data.get("pais_destino") or "").upper() if data.get("pais_destino") else ""
                if pais_origen == "ES" and pais_destino and pais_destino != "ES":
                    data["direction"] = "export"
                elif pais_origen and pais_origen != "ES" and pais_destino == "ES":
                    data["direction"] = "import"
                else:
                    data["direction"] = None
            elif direction:
                data["direction"] = direction
            else:
                data["direction"] = None
        else:
            pais_origen = (data.get("pais_origen") or "").upper() if data.get("pais_origen") else ""
            pais_destino = (data.get("pais_destino") or "").upper() if data.get("pais_destino") else ""
            if pais_origen == "ES" and pais_destino and pais_destino != "ES":
                data["direction"] = "export"
            elif pais_origen and pais_origen != "ES" and pais_destino == "ES":
                data["direction"] = "import"

        if data.get("incoterm"):
            try:
                incoterm = str(data["incoterm"]).upper().strip() if data["incoterm"] else None
                if incoterm:
                    incoterm_map = {"FOB": "FCA", "CIF": "CIP", "CFR": "CPT"}
                    valid_incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"]
                    if incoterm in incoterm_map:
                        data["incoterm"] = incoterm_map[incoterm]
                    elif incoterm not in valid_incoterms:
                        _logger.warning(
                            "Incoterm '%s' no es válido y no se puede mapear. No se asignará.",
                            incoterm,
                        )
                        data["incoterm"] = None
                    else:
                        data["incoterm"] = incoterm
                else:
                    data["incoterm"] = None
            except (AttributeError, TypeError) as e:
                _logger.warning("Error procesando incoterm '%s': %s", data.get("incoterm"), e)
                data["incoterm"] = None

        if data.get("valor_total") not in (None, ""):
            data["valor_total"] = self._parse_invoice_number(data.get("valor_total"))

        lineas_validas = []
        for linea in data.get("lineas", []):
            if not isinstance(linea, dict):
                continue
            descripcion = (linea.get("descripcion") or "").lower()
            if any(p in descripcion for p in ["pedido pendiente", "pendiente", "pending order"]):
                _logger.info(
                    "Ignorando línea con descripción de pedido pendiente: %s",
                    linea.get("descripcion"),
                )
                continue

            for campo in ("cantidad", "unidades", "precio_unitario", "total", "subtotal"):
                if linea.get(campo) not in (None, ""):
                    parsed = self._parse_invoice_number(linea.get(campo))
                    if parsed is not None:
                        linea[campo] = parsed

            if linea.get("descuento") not in (None, ""):
                linea["descuento"] = self._parse_invoice_number(linea.get("descuento"))

            for campo_peso in ["peso_bruto", "peso_neto"]:
                if linea.get(campo_peso) not in (None, ""):
                    linea[campo_peso] = self._parse_invoice_number(linea.get(campo_peso))

            if linea.get("bultos") not in (None, ""):
                try:
                    bultos = self._parse_invoice_number(linea.get("bultos"))
                    linea["bultos"] = int(bultos) if bultos is not None else None
                except Exception:
                    linea["bultos"] = None

            if linea.get("partida"):
                partida = str(linea["partida"]).strip()
                partida = "".join(filter(str.isdigit, partida))
                if partida:
                    if len(partida) < 8:
                        partida = partida.zfill(8)
                    if len(partida) > 10:
                        partida = partida[:10]
                    linea["partida"] = partida
                else:
                    linea["partida"] = None
            else:
                _logger.warning("Línea sin partida arancelaria: %s", linea.get("descripcion"))

            lineas_validas.append(linea)

        data["lineas"] = lineas_validas

        # Preferir importes del patrón Cant./Importe del texto OCR cuando la matemática cuadra
        data = self._repair_line_amounts_from_texto(data)

        # Reconciliar neto/descuento/importe
        for linea in data.get("lineas") or []:
            self._reconcile_line_amounts(linea)

        _logger.info("Datos estructurados validados: %d líneas extraídas", len(data.get("lineas") or []))
        return data

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

    def validate_invoice_consistency(self, expediente):
        """
        Realiza una verificación asistida por IA:
        - Compara totales de líneas vs. total de factura.
        - Revisa partidas arancelarias de cada línea y propone correcciones/sugerencias.
        Devuelve un diccionario estructurado con los resultados o error.
        """
        api_key = self.env['res.config.settings'].get_openai_api_key()
        if not api_key:
            return {"error": _("No hay API Key configurada para OpenAI")}
        try:
            from openai import OpenAI
        except ImportError:
            return {"error": _("El paquete 'openai' no está instalado en el servidor")}
        
        # Filtrar líneas por factura si se especifica en el contexto
        factura_id = self.env.context.get('factura_id')
        if factura_id:
            factura = self.env['aduana.expediente.factura'].browse(factura_id)
            if factura.exists():
                lines_to_validate = expediente.line_ids.filtered(lambda l: l.factura_id == factura)
            else:
                lines_to_validate = expediente.line_ids
        else:
            lines_to_validate = expediente.line_ids
        
        lines_sorted = lines_to_validate.sorted(lambda l: l.item_number or l.id)
        lineas_payload = []
        for idx, line in enumerate(lines_sorted, 1):
            lineas_payload.append({
                "index": idx,
                "item_number": line.item_number,
                "partida": line.partida,
                "descripcion": line.descripcion,
                "unidades": line.unidades,
                "valor_linea": line.valor_linea,
                "precio_unitario": line.precio_unitario,
                "peso_neto": line.peso_neto,
                "peso_bruto": line.peso_bruto,
            })
        suma_lineas = sum([l.get("valor_linea") or 0 for l in lineas_payload])
        
        # Obtener contexto adicional del expediente para mejor sugerencia de partidas
        contexto_expediente = {
            "pais_origen": expediente.pais_origen or "ES",
            "pais_destino": expediente.pais_destino or "",
            "direction": expediente.direction or "export",
            "incoterm": expediente.incoterm or "",
        }
        if expediente.remitente:
            contexto_expediente["remitente_nombre"] = expediente.remitente.name or ""
        if expediente.consignatario:
            contexto_expediente["consignatario_nombre"] = expediente.consignatario.name or ""
        
        prompt = """Eres un experto en clasificación arancelaria y auditoría aduanera. Tu tarea es validar y sugerir códigos HS (Sistema Armonizado) para las líneas de una factura comercial.

IMPORTANTE: 
1. Cuando el estado sea "sugerido" o "corregido", SIEMPRE debes proporcionar un código HS válido de EXACTAMENTE 10 DÍGITOS en partida_validada. NUNCA devuelvas null cuando el estado es "sugerido" o "corregido".
2. TODOS los códigos arancelarios (partida_validada) DEBEN tener EXACTAMENTE 10 DÍGITOS. Si el código tiene menos dígitos, rellénalo con ceros a la izquierda hasta llegar a 10 dígitos.

Debes devolver JSON ESTRICTO (sin texto extra) con esta forma:
{
  "totales": {
    "es_coherente": true/false,
    "detalle": "explicación corta en español",
    "diferencia": número (total_factura - suma_lineas)
  },
  "lineas": [
    {
      "index": número de línea (1..n según orden recibido),
      "estado": "correcto" | "corregido" | "sugerido",
      "partida_validada": "código HS de EXACTAMENTE 10 DÍGITOS (OBLIGATORIO si estado es 'sugerido' o 'corregido')",
      "detalle": "explica por qué es correcta o la corrección/sugerencia"
    }
  ],
  "resumen": "2-3 frases en español con hallazgos clave (totales y partidas)"
}

REGLAS DE CLASIFICACIÓN:
- Usa estado "correcto" si la partida existe, es válida (10 dígitos) y es coherente con la descripción del producto.
- Usa estado "corregido" si la partida actual existe pero es incorrecta; debes proporcionar la partida correcta en partida_validada (EXACTAMENTE 10 DÍGITOS).
- Usa estado "sugerido" si NO hay partida o la actual es claramente incorrecta. EN ESTE CASO, SIEMPRE debes sugerir una partida válida de EXACTAMENTE 10 DÍGITOS basándote en:
  * La descripción detallada del producto
  * El tipo de mercancía (textil, electrónica, alimentaria, química, etc.)
  * El país de origen y destino del expediente
  * El contexto general de la factura
  * Tu conocimiento del Sistema Armonizado (HS Code)

CLASIFICACIÓN ARANCELARIA:
- Los códigos HS tienen 6 dígitos base (capítulo, partida, subpartida) y se extienden a 10 dígitos para la Nomenclatura Combinada (NC) de la UE.
- Para operaciones España ↔ país tercero, usa códigos de EXACTAMENTE 10 DÍGITOS (Nomenclatura Combinada - NC).
- Si el código tiene menos de 10 dígitos, rellénalo con ceros a la izquierda. Ejemplo: "12345678" → "1234567800", "123456" → "1234560000".
- Analiza cuidadosamente la descripción del producto para determinar la partida más apropiada.
- Si la descripción es ambigua, elige la partida más probable basándote en el contexto (país origen, tipo de operación, etc.).

EJEMPLOS DE CLASIFICACIÓN (siempre 10 dígitos):
- Ropa/textiles: Capítulos 50-63 (ej: "6109100000" para camisetas)
- Electrónica: Capítulos 84-85 (ej: "8517120000" para teléfonos)
- Alimentos: Capítulos 1-24 (ej: "0901110000" para café)
- Químicos: Capítulos 28-38 (ej: "3004900000" para medicamentos)
- Vehículos: Capítulos 86-87 (ej: "8703210000" para coches)

FORMATO DE CÓDIGOS:
- SIEMPRE devuelve códigos de EXACTAMENTE 10 DÍGITOS.
- Si el código original tiene 8 dígitos, añade "00" al final: "12345678" → "1234567800".
- Si el código original tiene 6 dígitos, añade "0000" al final: "123456" → "1234560000".
- NUNCA devuelvas códigos con menos de 10 dígitos.

Recuerda: Si estado = "sugerido" o "corregido", partida_validada DEBE ser un código HS válido de EXACTAMENTE 10 DÍGITOS, nunca null ni con menos dígitos."""
        user_payload = {
            "factura": {
                "valor_factura": expediente.valor_factura,
                "moneda": expediente.moneda,
                "suma_lineas": suma_lineas,
            },
            "contexto_expediente": contexto_expediente,
            "lineas": lineas_payload,
        }
        
        client = OpenAI(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Responde ÚNICAMENTE con JSON válido, sin código, sin markdown."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                temperature=0.1,
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            _logger.warning("Validación IA de factura falló: %s", e)
            return {"error": str(e)}

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
            # Calcular longitud del texto para informar a GPT
            text_length = len(text)
            num_pages_estimated = text_length // 2000  # Estimación aproximada de páginas
            
            prompt = f"""Eres un experto en procesamiento de facturas comerciales para documentos aduaneros.

⚠️⚠️⚠️ CRÍTICO - FACTURAS MULTI-PÁGINA ⚠️⚠️⚠️
El texto que recibes proviene de una factura que puede tener MÚLTIPLES PÁGINAS (hasta 100+ páginas).
El texto tiene aproximadamente {text_length} caracteres, lo que sugiere {num_pages_estimated} o más páginas.

DEBES analizar TODO el texto de TODAS las páginas de principio a fin. NO te detengas en la primera página.
- Extrae TODAS las líneas de productos de TODAS las páginas - no solo las de la primera página
- El valor total de la factura (valor_total) suele estar en la ÚLTIMA página - busca términos como "TOTAL", "TOTAL FACTURA", "IMPORTE TOTAL", "TOTAL A PAGAR"
- Las líneas de productos pueden continuar en páginas siguientes - busca tablas o listas que se extiendan por múltiples páginas
- Recorre TODO el texto completo antes de generar la respuesta

Analiza TODO el texto de principio a fin y extrae TODA la información relevante en formato JSON estricto.

FORMATO DE RESPUESTA REQUERIDO (JSON válido, sin markdown, sin código, solo JSON):
{{
  "numero_factura": "número o null",
  "fecha_factura": "DD.MM.YYYY o DD/MM/YYYY o null",
  "remitente_nombre": "nombre completo de la empresa emisora o null",
  "remitente_nif": "NIF/CIF español (formato A12345678) o NIF andorrano (L123456H) o null",
  "remitente_direccion": "dirección completa o null",
  "consignatario_nombre": "nombre completo del destinatario o null",
  "consignatario_nif": "NIF/CIF o null",
  "consignatario_direccion": "dirección completa o null",
  "valor_total": número decimal o null (BUSCA en TODAS las páginas, especialmente al final),
  "moneda": "EUR" o "USD" o null,
  "incoterm": "EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP" o null (si encuentras CIF, FOB, CFR, mapea a CIP, FCA, CPT respectivamente),
  "pais_origen": "código ISO de 2 letras (ES, AD, FR, etc.) o null",
  "pais_destino": "código ISO de 2 letras o null",
  "direction": "export" o "import" o null (export = España → país tercero, import = país tercero → España),
  "transportista": "nombre del transportista o null",
  "matricula": "matrícula del vehículo o null",
  "referencia_transporte": "referencia o número de transporte o null",
  "remolque": "matrícula del remolque o null",
  "codigo_transporte": "código del transporte o null",
  "lineas": [
    {{
      "articulo": "código del artículo o null",
      "descripcion": "descripción completa del producto",
      "cantidad": número decimal,
      "unidades": número decimal (igual que cantidad),
      "precio_unitario": número decimal o null,
      "total": número decimal o null,
      "subtotal": número decimal o null (subtotal de la línea con descuento aplicado),
      "descuento": número decimal (porcentaje de descuento) o null,
      "partida": "código H.S. (8-10 dígitos) o null",
      "bultos": número entero o null,
      "peso_bruto": número decimal en KG o null,
      "peso_neto": número decimal en KG o null
    }}
  ]
}}

INSTRUCCIONES CRÍTICAS PARA FACTURAS MULTI-PÁGINA:
1. ⚠️ LEE TODO EL TEXTO DE PRINCIPIO A FIN - NO te detengas en la primera página. Recorre TODO el documento completo.
2. ⚠️ Extrae TODAS las líneas de productos de TODAS las páginas - no solo las de la primera página. Las facturas pueden tener 50+ páginas con líneas en todas ellas.
3. ⚠️ El valor total (valor_total) suele estar en la ÚLTIMA página - busca términos como "TOTAL", "TOTAL FACTURA", "IMPORTE TOTAL", "TOTAL A PAGAR", "TOTAL NETO", "TOTAL BRUTO". Recorre hasta el final del texto.
4. ⚠️ Las líneas de productos pueden continuar en páginas siguientes - busca tablas o listas que se extiendan por múltiples páginas. Identifica patrones de tablas que continúan entre páginas.
5. Extrae SOLO los artículos/productos de la factura ACTUAL. IGNORA completamente cualquier sección que diga "Pedido pendiente", "Pedidos pendientes", "Pendiente" o similar. Esos productos NO deben aparecer en las líneas.
6. Para el código H.S. (partida arancelaria), busca "H.S.", "HS", "Partida arancelaria" seguido de números de 8-10 dígitos. Es OBLIGATORIO incluirlo en cada línea de producto.
7. Para incoterms, busca DAP, CIF, FOB, EXW, etc. en el texto (puede estar en cualquier página)
8. Para países, identifica por contexto: España/Spain/Barcelona → ES, Andorra → AD, Suiza/Switzerland → CH, Reino Unido/United Kingdom → GB, Marruecos/Morocco → MA, etc.
9. Para direction (sentido), determina basándote en los países:
   - Si pais_origen = "ES" y pais_destino es distinto de "ES" → direction = "export" (España → país tercero)
   - Si pais_origen es distinto de "ES" y pais_destino = "ES" → direction = "import" (país tercero → España)
   - Si no puedes determinarlo con certeza, usa null
10. Para NIFs, busca patrones como A12345678 (español) o L123456H (andorrano)
11. Para valores monetarios, usa el formato español (2.195,42 → 2195.42)
12. Para transporte, busca en todas las páginas:
    - Transportista: nombre de la empresa transportista
    - Matrícula: número de matrícula del vehículo (formato como 5728-KXF)
    - Referencia Transporte: número de referencia del transporte o albarán
    - Remolque: matrícula del remolque si aparece
    - Código Transporte: código alfanumérico del transporte (como TXT, TX5X)
13. Para descuentos, busca porcentajes de descuento asociados a cada línea o descuento general. Si hay "Descuento Principal 64,00%" o similar, inclúyelo en las líneas correspondientes.
14. Si un campo no se encuentra, usa null (no uses cadenas vacías)
15. Devuelve SOLO el JSON, sin explicaciones, sin markdown, sin ```json
16. CRÍTICO: Si ves una sección que dice "Pedido pendiente" o "Pedidos pendientes", esos productos NO son de esta factura. Solo extrae productos que estén claramente asociados a la factura actual.
17. ⚠️⚠️⚠️ CRÍTICO: Asegúrate de incluir TODAS las líneas de productos de TODAS las páginas, no solo las de la primera página. Recorre TODO el texto completo antes de generar la respuesta. Una factura puede tener cientos de líneas distribuidas en múltiples páginas.

TEXTO COMPLETO DE LA FACTURA (todas las páginas):
""" + text[:200000]  # Aumentado a 200000 caracteres para facturas muy grandes (50+ páginas)
            
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
                    max_tokens=16000,  # Aumentado significativamente para facturas con muchas líneas (50+ páginas)
                    response_format={"type": "json_object"},  # Forzar formato JSON (GPT-4o)
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
                    max_tokens=16000  # Aumentado significativamente para facturas con muchas líneas (50+ páginas)
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
                if not isinstance(data, dict):
                    raise ValueError("La respuesta no es un diccionario")
                return self._normalize_structured_invoice_data(data)
                
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
        # Buscar por contexto: España como lado UE y cualquier país tercero frecuente.
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
            r'(?:Destino|Destination|To)\s*:?\s*([A-Z]{2})',
            r'\b(AD|ANDORRA|CH|SWITZERLAND|SUIZA|GB|UNITED KINGDOM|UK|MA|MOROCCO|MARRUECOS)\b',
        ]
        for pattern in pais_destino_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pais = match.group(1).upper()
                if pais in ("ANDORRA", "AD"):
                    data["pais_destino"] = "AD"
                    break
                if pais in ("SWITZERLAND", "SUIZA", "CH"):
                    data["pais_destino"] = "CH"
                    break
                if pais in ("UNITED KINGDOM", "UK", "GB"):
                    data["pais_destino"] = "GB"
                    break
                if pais in ("MOROCCO", "MARRUECOS", "MA"):
                    data["pais_destino"] = "MA"
                    break
        
        # Si no se encontraron por contexto, buscar códigos ISO en el texto
        if not data["pais_origen"] or not data["pais_destino"]:
            pais_pattern = r'\b(ES|AD|FR|PT|DE|IT|GB|US|CH|MA)\b'
            paises = re.findall(pais_pattern, text)
            if paises:
                # Filtrar paises que aparecen en direcciones (códigos postales)
                paises_validos = []
                for pais in paises:
                    # Evitar falsos positivos (códigos que aparecen en otros contextos)
                    if pais in ['ES', 'AD', 'FR', 'PT', 'DE', 'IT', 'GB', 'US', 'CH', 'MA']:
                        paises_validos.append(pais)
                
                if paises_validos:
                    # Si hay "ANDORRA" en el texto, el destino es AD
                    if 'ANDORRA' in text.upper() or 'AD500' in text.upper():
                        data["pais_destino"] = "AD"
                    # Si hay "Barcelona" o "España" en el texto, el origen es ES
                    if 'BARCELONA' in text.upper() or 'ESPAÑA' in text.upper() or 'SPAIN' in text.upper():
                        data["pais_origen"] = "ES"
                    
                    # Valores por defecto si no se encontraron, sin asumir Andorra.
                    if not data["pais_origen"]:
                        data["pais_origen"] = paises_validos[0] if len(paises_validos) > 0 else "ES"
                    if not data["pais_destino"]:
                        data["pais_destino"] = paises_validos[1] if len(paises_validos) > 1 else None
        
        # Determinar direction (sentido) basándose en países
        pais_origen = (data.get("pais_origen") or "").upper() if data.get("pais_origen") else ""
        pais_destino = (data.get("pais_destino") or "").upper() if data.get("pais_destino") else ""
        if pais_origen == "ES" and pais_destino and pais_destino != "ES":
            data["direction"] = "export"
        elif pais_origen and pais_origen != "ES" and pais_destino == "ES":
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
        # Buscar todas las ocurrencias en todo el texto, no solo la primera
        tabla_pattern = r'ARTICULO\s+DESCRIPCION\s+BULTOS\s+PESO\s+BRUTO\s+PESO\s+NETO\s*\n\s*(\d+)\s+([^\n]+?)\s+(\d+)\s+C/U\s+(\d+)\s+KG\s+(\d+)\s+KG'
        tabla_matches = list(re.finditer(tabla_pattern, text, re.IGNORECASE | re.MULTILINE))
        if tabla_matches:
            for tabla_match in tabla_matches:
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
                            # No hacer break - continuar buscando todas las líneas en todo el texto
        
        # No limitar líneas - devolver todas las encontradas (pueden ser cientos en facturas grandes)
        return lineas

    def _parse_invoice_date(self, date_str):
        """Convierte fecha de factura (DD/MM/YYYY, DD.MM.YYYY, etc.) a datetime Odoo."""
        if not date_str:
            return False
        text = str(date_str).strip()
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                from datetime import datetime
                dt = datetime.strptime(text[:10], fmt)
                return fields.Datetime.to_datetime(dt)
            except ValueError:
                continue
        return False

    def fill_expediente_from_invoice(self, expediente, invoice_data, factura=None):
        """
        Rellena los campos de un expediente con los datos extraídos de la factura.
        
        :param expediente: Recordset de aduana.expediente
        :param invoice_data: Diccionario con datos extraídos
        :param factura: Recordset opcional de aduana.expediente (expediente hijo/factura). Si se proporciona,
                        las líneas se crean en expediente con factura_id=factura.
        """
        expediente.ensure_one()
        
        # Preparar valores para actualización masiva sin tracking
        vals = {}
        
        # Nº factura comercial (N380): en cabecera legacy o en cada factura del bloque Facturas
        numero = (invoice_data.get("numero_factura") or "").strip()
        if numero:
            if factura:
                factura.with_context(mail_notrack=True, tracking_disable=True).write(
                    {"numero_factura": numero[:64]}
                )
            else:
                vals["numero_factura"] = numero[:64]
        
        # valor_factura es campo computado (suma de line_ids.valor_linea); se actualiza al crear/actualizar líneas
        
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
            pais_origen = (invoice_data.get("pais_origen") or "").upper() if invoice_data.get("pais_origen") else ""
            pais_destino = (invoice_data.get("pais_destino") or "").upper() if invoice_data.get("pais_destino") else ""
            if pais_origen == "ES" and pais_destino and pais_destino != "ES":
                vals["direction"] = "export"
            elif pais_origen and pais_origen != "ES" and pais_destino == "ES":
                vals["direction"] = "import"
        
        # Actualizar incoterm (validar y mapear valores) - SIEMPRE validar antes de escribir
        # NUNCA escribir un incoterm inválido, solo advertencias
        incoterm_original = invoice_data.get("incoterm")
        if incoterm_original:
            try:
                # Convertir a string y normalizar
                incoterm = str(incoterm_original).upper().strip() if incoterm_original else None
                if incoterm:
                    # Mapeo de incoterms antiguos a los válidos
                    incoterm_map = {
                        "FOB": "FCA",
                        "CIF": "CIP",
                        "CFR": "CPT",
                    }
                    # Valores válidos
                    valid_incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"]
                    
                    # Aplicar mapeo si es necesario
                    incoterm_mapeado = incoterm_map.get(incoterm, incoterm)
                    
                    # Validar que sea un valor válido ANTES de agregar a vals
                    if incoterm_mapeado in valid_incoterms:
                        vals["incoterm"] = incoterm_mapeado
                        # Si se mapeó, guardar información para el resumen
                        if incoterm != incoterm_mapeado:
                            invoice_data["_incoterm_mapeado"] = {
                                "original": incoterm_original,
                                "mapeado": incoterm_mapeado
                            }
                    else:
                        # Si no es válido, NO escribir nada, solo registrar advertencia
                        _logger.warning("Incoterm '%s' no es válido y no se puede mapear. No se asignará. Se mostrará advertencia.", incoterm_original)
                        invoice_data["_incoterm_invalido"] = incoterm_original
                        # NO agregar a vals, el proceso continúa sin incoterm
                else:
                    # Si incoterm está vacío o es None, no asignar
                    _logger.warning("Incoterm vacío o None, no se asignará")
            except Exception as e:
                _logger.error("Error procesando incoterm '%s': %s. No se asignará incoterm.", incoterm_original, e)
                invoice_data["_incoterm_invalido"] = incoterm_original
                # NO agregar a vals en caso de error, el proceso continúa
        
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

        # Fecha prevista desde la fecha de la factura
        if invoice_data.get("fecha_factura") and not expediente.fecha_prevista:
            parsed_date = self._parse_invoice_date(invoice_data["fecha_factura"])
            if parsed_date:
                vals["fecha_prevista"] = parsed_date

        # Perfil Traldis: rellenar campos vacíos según sentido (oficina, tributos import, etc.)
        direction = vals.get("direction") or expediente.direction
        if direction:
            profile = expediente._get_expediente_profile_defaults(direction)
            for key, value in profile.items():
                current = vals.get(key)
                if current is None and key in expediente._fields:
                    current = expediente[key]
                if current in (False, None, "", 0.0) and value not in (False, None, ""):
                    vals[key] = value

        # LRN importación = referencia del expediente
        if (vals.get("direction") or expediente.direction) == "import":
            if not expediente.lrn and not vals.get("lrn") and expediente.name:
                vals["lrn"] = expediente.name
        
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
        
        # Validación final de incoterm antes de escribir (seguridad adicional)
        # Si hay problema, no escribir incoterm y solo registrar advertencia
        if "incoterm" in vals:
            incoterm_val = vals["incoterm"]
            valid_incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"]
            if incoterm_val not in valid_incoterms:
                # Mapeo de emergencia
                incoterm_map_emergency = {
                    "FOB": "FCA",
                    "CIF": "CIP",
                    "CFR": "CPT",
                }
                incoterm_upper = str(incoterm_val).upper().strip() if incoterm_val else None
                if incoterm_upper and incoterm_upper in incoterm_map_emergency:
                    vals["incoterm"] = incoterm_map_emergency[incoterm_upper]
                    invoice_data["_incoterm_mapeado"] = {
                        "original": incoterm_val,
                        "mapeado": incoterm_map_emergency[incoterm_upper]
                    }
                    _logger.warning("Incoterm '%s' mapeado en validación final a '%s'", incoterm_val, vals["incoterm"])
                else:
                    # Si no se puede mapear, no escribir incoterm y registrar advertencia
                    _logger.warning("Incoterm inválido '%s' detectado, no se asignará. Se mostrará advertencia en resumen.", incoterm_val)
                    del vals["incoterm"]  # Eliminar del diccionario para no escribir valor inválido
                    invoice_data["_incoterm_invalido"] = incoterm_val
        
        # Actualizar todos los campos de una vez sin tracking
        # Si hay error con algún campo (ej: incoterm), intentar sin ese campo
        if vals:
            try:
                expediente.with_context(mail_notrack=True, tracking_disable=True).write(vals)
            except ValueError as ve:
                # Si hay un error de validación (ej: incoterm inválido), intentar sin ese campo
                error_str = str(ve)
                if "incoterm" in error_str.lower():
                    _logger.warning("Error al escribir incoterm: %s. Eliminando incoterm del diccionario y reintentando.", error_str)
                    if "incoterm" in vals:
                        incoterm_problematico = vals.pop("incoterm")
                        invoice_data["_incoterm_invalido"] = incoterm_problematico
                    # Reintentar sin el incoterm
                    if vals:
                        expediente.with_context(mail_notrack=True, tracking_disable=True).write(vals)
                else:
                    # Si es otro error, re-lanzar
                    raise

        expediente._sync_delivery_partners()
        
        # Crear líneas de productos si se extrajeron
        if invoice_data.get("lineas"):
            # Si hay factura (expediente hijo), borrar solo las líneas de esa factura en el expediente principal
            if factura:
                expediente.line_ids.filtered(lambda l: l.factura_id == factura).unlink()
            else:
                expediente.line_ids.unlink()
            
            LineModel = self.env["aduana.expediente.line"]
            for idx, linea_data in enumerate(invoice_data["lineas"], start=1):
                # Reconciliar importes: total de línea manda sobre precio unitario de la IA
                linea_data = self._reconcile_line_amounts(dict(linea_data or {}))

                # Calcular unidades
                unidades = self._parse_invoice_number(
                    linea_data.get("unidades") or linea_data.get("cantidad")
                ) or 1.0
                
                # Determinar valor_linea (debe ser el TOTAL de la línea, no el precio unitario)
                total_ia = self._parse_invoice_number(linea_data.get("total"))
                subtotal_ia = self._parse_invoice_number(linea_data.get("subtotal"))
                precio_unitario_ia = self._parse_invoice_number(linea_data.get("precio_unitario"))
                
                # Prioridad: total > subtotal > (precio_unitario * unidades)
                if total_ia is not None:
                    valor_linea = total_ia
                elif subtotal_ia is not None:
                    valor_linea = subtotal_ia
                elif precio_unitario_ia is not None and unidades and unidades > 0:
                    valor_linea = precio_unitario_ia * unidades
                else:
                    valor_linea = 0.0
                
                line_vals = {
                    "expediente_id": expediente.id,
                    "factura_id": factura.id if factura else False,  # Expediente hijo (factura) al que pertenece la línea
                    "item_number": idx,
                    "descripcion": linea_data.get("descripcion", ""),
                    "unidades": unidades,
                    "valor_linea": valor_linea,  # Total de la línea
                    "pais_origen": expediente.pais_origen or "ES",
                }
                
                # Precio unitario: preferir neto impreso si cuadra con dto
                # (1.57×12×0.95=17.90). Si no, valor_linea/unidades.
                if precio_unitario_ia is not None and self._line_discount_math_ok(linea_data):
                    line_vals["precio_unitario"] = precio_unitario_ia
                elif valor_linea and unidades and unidades > 0:
                    line_vals["precio_unitario"] = valor_linea / unidades
                elif precio_unitario_ia is not None:
                    line_vals["precio_unitario"] = precio_unitario_ia
                
                # Agregar descuento si está disponible
                if linea_data.get("descuento") not in (None, ""):
                    try:
                        descuento = self._parse_invoice_number(linea_data.get("descuento"))
                        if descuento is not None:
                            line_vals["descuento"] = descuento
                    except Exception:
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
        if factura:
            # Guardar en la factura específica
            factura.with_context(mail_notrack=True, tracking_disable=True).write({
                'factura_datos_extraidos': json.dumps(invoice_data, indent=2, ensure_ascii=False),
                'factura_procesada': True,
                'fecha_procesamiento': fields.Datetime.now(),
            })
        else:
            # Modo legacy: guardar en el expediente
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
        
        # Crear mensaje técnico sin intentar enviar correos
        # Crear mensaje técnico directamente en mail.message sin pasar por el sistema de correo
        try:
            # Obtener el subtipo de mensaje
            subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
            if not subtype:
                subtype = self.env['mail.message.subtype'].search([('name', '=', 'Note')], limit=1)
            
            # Crear mensaje directamente en mail.message sin validaciones de correo
            self.env['mail.message'].sudo().create({
                'model': 'aduana.expediente',
                'res_id': expediente.id,
                'message_type': 'notification',
                'subtype_id': subtype.id if subtype else False,
                'body': mensaje_tecnico,
                'author_id': False,  # Sistema
                'email_from': False,  # No intentar enviar correo
            })
        except Exception as msg_error:
            # Si hay error al crear mensaje, solo loguear y continuar
            _logger.warning("No se pudo crear mensaje técnico en chatter (error ignorado): %s", msg_error)
            # El proceso continúa normalmente aunque no se pueda crear el mensaje
        
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

