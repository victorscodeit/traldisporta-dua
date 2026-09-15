# -*- coding: utf-8 -*-
"""
Consulta del Arancel Integrado AEAT (DD09) mediante certificado cliente (mTLS).

Flujo descubierto (Sede / www1):
  1) POST TtCodNomIntQuery (FCdnmc + FFecha) → lista nomenclaturas + SIDNMC
  2) POST TtCodNomAcc (SIDNMC + ageo + nomen + fecha) → medidas y documentos

URL pública de acceso:
  https://sede.agenciatributaria.gob.es/Sede/procedimientoini/DD09.shtml
  → https://www1.agenciatributaria.gob.es/wlpl/inwinvoc/es.aeat.dit.adu.adta.trans.bdm.TtCodNomIntQue

Nota: la UI de Sede puede cambiar; este scraper es frágil y requiere mantenimiento.
"""
import html as htmlmod
import logging
import os
import re
from datetime import date

import requests
from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://www1.agenciatributaria.gob.es"
DEFAULT_AGEO = "1011"  # ERGA OMNES / TODOS (probado en spike)


class AduanasAeatTaricScraper(models.AbstractModel):
    _name = "aduanas.aeat.taric.scraper"
    _description = "Scraper TARIC / Arancel Integrado AEAT (certificado)"

    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    def _base_url(self):
        return (
            self._icp().get_param("aduanas_transport.taric_aeat_base_url") or DEFAULT_BASE
        ).rstrip("/")

    def _ageo(self):
        return (self._icp().get_param("aduanas_transport.taric_aeat_ageo") or DEFAULT_AGEO).strip()

    def _timeout(self):
        try:
            return int(self._icp().get_param("aduanas_transport.taric_aeat_timeout") or 60)
        except (TypeError, ValueError):
            return 60

    def _session_with_cert(self):
        """Sesión requests con PEM del P12 del módulo. Retorna (session, cleanup_paths)."""
        client = self.env["aduanas.aeat.client"]
        err = client.check_certificate_ready()
        if err:
            raise UserError(err)
        cert_path, key_path = client._get_cert_tuple_for_requests()
        if not cert_path or not key_path:
            raise UserError(_(
                "No se pudo preparar el certificado AEAT (PEM) para consultar TARIC. "
                "Revise el P12 y la contraseña en Aduanas > Configuración."
            ))
        sess = requests.Session()
        sess.cert = (cert_path, key_path)
        sess.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; TraldisAduanas/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "es-ES,es;q=0.9",
        })
        return sess, [cert_path, key_path]

    @staticmethod
    def _cleanup_paths(paths):
        for path in paths or []:
            try:
                if path and os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _normalize_goods_code(goods_code):
        digits = "".join(ch for ch in str(goods_code or "") if ch.isdigit())
        return digits[:10]

    @staticmethod
    def _to_dotted(goods_code):
        g = AduanasAeatTaricScraper._normalize_goods_code(goods_code)
        if len(g) >= 10:
            return "%s.%s.%s.%s" % (g[:4], g[4:6], g[6:8], g[8:10])
        return g

    @staticmethod
    def _html_to_text(html_text):
        text = htmlmod.unescape(html_text or "")
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _search_sidnmc(self, session, goods_code, reference_date):
        """Busca SIDNMC de la nomenclatura exacta en TtCodNomIntQuery."""
        base = self._base_url()
        query_url = (
            base
            + "/wlpl/inwinvoc/es.aeat.dit.adu.adta.trans.bdm.TtCodNomIntQuery"
        )
        payload = {
            "FFecha": reference_date.strftime("%d-%m-%Y"),
            "FCdnmc": goods_code,
            "CLASGTE": "20/0/",
            "TOTALES": "",
            "QUE-MODO": "NORMAL",
            "QUE_MODO": "NORMAL",
            "ESTADO_COLS": "",
            "NUM_RESULTADOS_RS": "0",
            "VEZ": "",
            "Buscar": "Buscar",
        }
        resp = session.post(query_url, data=payload, timeout=self._timeout())
        if resp.status_code != 200:
            raise UserError(_(
                "AEAT TARIC: búsqueda falló (HTTP %s)."
            ) % resp.status_code)
        html = htmlmod.unescape(resp.text or "")
        sid_list = re.findall(
            r"TtCodNomAcc\?ACCION=DetalleInt[^\"']*SIDNMC=(\d+)",
            html,
        )
        if not sid_list:
            # Fallback: cualquier SIDNMC en la página
            sid_list = re.findall(r"SIDNMC=(\d+)", html)
        # Unique preserving order
        seen = set()
        ordered = []
        for sid in sid_list:
            if sid not in seen:
                seen.add(sid)
                ordered.append(sid)
        return ordered, html

    def _fetch_measures_html(self, session, goods_code, sidnmc, reference_date, ageo=None):
        base = self._base_url()
        action = base + "/wlpl/inwinvoc/es.aeat.dit.adu.adta.trans.bdm.TtCodNomAcc"
        ageo = ageo or self._ageo()
        payload = {
            "ACCION": "DetalleInt",
            "MENU": "",
            "CAMPOS": "",
            "SIDNMC": sidnmc,
            "SIDGUI": "",
            "SIDDSC": "",
            "ageo": ageo,
            "nomen": goods_code,
            "fecha": reference_date.strftime("%d-%m-%Y"),
            "accion": "Aranceles",
            "Aceptar": "Aceptar",
            "CONANO": "%04d" % reference_date.year,
            "CONDIA": "%02d" % reference_date.day,
            "CONMES": "%02d" % reference_date.month,
        }
        resp = session.post(action, data=payload, timeout=self._timeout())
        if resp.status_code != 200:
            raise UserError(_(
                "AEAT TARIC: detalle/medidas falló (HTTP %s)."
            ) % resp.status_code)
        return resp.text or ""

    def _detail_code_matches(self, html_text, goods_code):
        text = self._html_to_text(html_text)
        dotted = self._to_dotted(goods_code)
        compact = "".join(ch for ch in text if ch.isdigit())
        # Prefer dotted appearance
        if dotted and dotted in text:
            return True
        return goods_code and goods_code in compact

    def fetch_taric_raw(self, goods_code, direction=None, country_code=None, reference_date=None):
        """
        Devuelve dict con texto/HTML de medidas AEAT para una partida.
        :return: {goods_code, sidnmc, ageo, html, text, description}
        """
        goods_code = self._normalize_goods_code(goods_code)
        if len(goods_code) < 8:
            raise UserError(_("Código TARIC inválido: %s") % goods_code)
        if reference_date is None:
            reference_date = date.today()
        elif isinstance(reference_date, str):
            # YYYY-MM-DD or DD-MM-YYYY
            try:
                if "-" in reference_date and len(reference_date) == 10 and reference_date[4] == "-":
                    y, m, d = reference_date.split("-")
                    reference_date = date(int(y), int(m), int(d))
                else:
                    d, m, y = reference_date.replace("/", "-").split("-")
                    reference_date = date(int(y), int(m), int(d))
            except Exception as e:
                raise UserError(_("Fecha de consulta TARIC inválida: %s") % reference_date) from e

        session, temp_paths = self._session_with_cert()
        try:
            _logger.info(
                "AEAT TARIC scrape goods=%s date=%s ageo=%s",
                goods_code, reference_date.isoformat(), self._ageo(),
            )
            sid_list, _search_html = self._search_sidnmc(session, goods_code, reference_date)
            if not sid_list:
                raise UserError(_(
                    "AEAT TARIC: no se encontró nomenclatura para el código %s."
                ) % goods_code)

            chosen_sid = None
            measures_html = ""
            for sid in sid_list[:12]:
                html = self._fetch_measures_html(session, goods_code, sid, reference_date)
                if self._detail_code_matches(html, goods_code):
                    chosen_sid = sid
                    measures_html = html
                    break
            if not chosen_sid:
                # Usar el primero aunque no verifiquemos (mejor que nada)
                chosen_sid = sid_list[0]
                measures_html = self._fetch_measures_html(
                    session, goods_code, chosen_sid, reference_date
                )

            text = self._html_to_text(measures_html)
            # Descripción larga si aparece
            desc = ""
            m = re.search(
                r"Descripci[oó]n Larga:\s*(.+?)(?:Consulta de Aranceles|Medidas asociadas|$)",
                text,
                re.I,
            )
            if m:
                desc = m.group(1).strip()[:500]

            return {
                "goods_code": goods_code,
                "dotted_code": self._to_dotted(goods_code),
                "sidnmc": chosen_sid,
                "ageo": self._ageo(),
                "reference_date": reference_date.isoformat(),
                "direction": direction,
                "country_code": country_code,
                "html": measures_html,
                "text": text,
                "description": desc,
            }
        finally:
            self._cleanup_paths(temp_paths)

    # Etiquetas genéricas del bloque Condiciones (no son el documento real).
    _GENERIC_DOC_LABELS = (
        "aplicar el derecho mencionado",
        "presentación de un certificado/licencia/documento",
        "presentacion de un certificado/licencia/documento",
        "importación/exportación autorizada después de control",
        "importacion/exportacion autorizada despues de control",
        "importación/ exportación no autorizada después de control",
        "otras condiciones",
        "medida no aplicable",
    )

    def _is_generic_label(self, label):
        norm = re.sub(r"\s+", " ", (label or "").strip().lower())
        if not norm or len(norm) < 8:
            return True
        return any(g in norm for g in self._GENERIC_DOC_LABELS)

    def extract_documents_regex(self, raw):
        """
        Extrae códigos de documento/certificado del texto de medidas AEAT.

        Prioriza el bloque «Indicaciones especiales/Documentos presentados…»,
        donde AEAT pone la descripción útil (p.ej. C990 Autorización de destino final…).
        El bloque Condiciones solo aporta etiquetas genéricas y se usa como fallback.
        """
        text = (raw or {}).get("text") or ""
        by_code = {}

        # 1) Secciones de documentos reales
        section_re = re.compile(
            r"Indicaciones especiales/Documentos presentados/Certificados y autorizaciones:\s*(.+?)"
            r"(?=Indicaciones especiales/Documentos presentados/Certificados y autorizaciones:|"
            r"Condiciones:|Medidas asociadas|Consulta de Aranceles|$)",
            re.I | re.S,
        )
        code_in_section = re.compile(
            r"\b([BCUYELNPR]\d{3})\s+(.+?)(?=\s+[BCUYELNPR]\d{3}\b|\s+A\.GEO\.|\s+Reglamento:|$)",
            re.I | re.S,
        )
        for sec in section_re.finditer(text):
            chunk = re.sub(r"\s+", " ", sec.group(1)).strip()
            for match in code_in_section.finditer(chunk):
                code = match.group(1).upper()
                detail = re.sub(r"\s+", " ", match.group(2)).strip(" -–,;")
                # Cortar basura de contexto geográfico/medida
                detail = re.split(
                    r"\b(?:TM\s+\d+|705-TRIMP|Exclusiones:|Productos para)\b",
                    detail,
                    maxsplit=1,
                )[0].strip(" -–,;")
                if not detail or self._is_generic_label(detail):
                    continue
                prev = by_code.get(code)
                if not prev or len(detail) > len(prev.get("description") or ""):
                    by_code[code] = {
                        "code": code,
                        "name": detail[:180],
                        "description": detail[:2000],
                        "mandatory": code[0] in ("B", "C", "U", "E", "L", "N", "P", "R"),
                        "source": "aeat_regex_docs",
                    }

        # 2) Fallback condiciones: solo códigos aún no vistos (nombre genérico + aviso)
        for match in re.finditer(
            r"\b([BCUYELNPR]\d{3})\s+"
            r"(Presentaci[oó]n de un certificado(?:/licencia/documento)?|"
            r"Aplicar el derecho mencionado|Otras condiciones|"
            r"Importaci[oó]n/exportaci[oó]n autorizada(?: después de control)?)",
            text,
            re.I,
        ):
            code = match.group(1).upper()
            if code in by_code:
                continue
            label = re.sub(r"\s+", " ", match.group(2)).strip()
            # Sin detalle en Indicaciones: suele ser celda de matriz, no documento claro
            by_code[code] = {
                "code": code,
                "name": _("%s — condición / alternativa TARIC") % code,
                "description": _(
                    "El código %s aparece en el bloque Condiciones AEAT («%s») "
                    "sin ficha detallada de documento. Suele ser una alternativa "
                    "de la matriz (exención o presentación genérica). "
                    "Confirme en Sede si debe aportarse algo para esta partida."
                ) % (code, label),
                "mandatory": False,
                "source": "aeat_regex_cond",
            }

        return list(by_code.values())

    def _parse_measure_blocks(self, text):
        """Divide el texto AEAT en bloques de medida (103-APPL, SVI-SOVIM, …)."""
        text = text or ""
        # AEAT usa códigos numéricos (103-APPL) y alfanuméricos (SVI-SOVIM / SVX-SOVEX).
        measure_re = r"[A-Z0-9]{2,}-[A-Z0-9]+"
        parts = re.split(rf"(?={measure_re}\s+A\.GEO\.)", text, flags=re.I)
        blocks = []
        for part in parts:
            part = part.strip()
            m = re.match(rf"^({measure_re})\s+A\.GEO\.:\s*(.+)$", part, re.I | re.S)
            if not m:
                continue
            measure = m.group(1).upper()
            body = re.sub(r"\s+", " ", m.group(2)).strip()
            geo_m = re.match(r"^(.+?)\s+Reglamento:\s*(\S+)\s*(.*)$", body, re.I)
            if geo_m:
                geo = geo_m.group(1).strip()
                reglamento = geo_m.group(2).strip()
                rest = geo_m.group(3).strip()
            else:
                geo, reglamento, rest = body[:80], "", body
            # Título de medida: texto hasta Condiciones/Derechos/Indicaciones
            title_m = re.match(
                r"^(.*?)(?=\s+Derechos:|\s+Condiciones:|\s+Indicaciones especiales|$)",
                rest,
                re.I,
            )
            title = (title_m.group(1).strip() if title_m else rest[:200]).strip(" -–,;")
            derechos_m = re.search(
                rf"Derechos:\s*(.+?)(?=\s+Condiciones:|\s+Indicaciones especiales|\s+{measure_re}\b|$)",
                rest,
                re.I,
            )
            derechos = (derechos_m.group(1).strip() if derechos_m else "")[:80]
            cond_m = re.search(
                r"Condiciones:\s*(.+?)(?=\s+Indicaciones especiales|\s+Medida no aplicable|$)",
                rest,
                re.I,
            )
            condiciones = (cond_m.group(1).strip() if cond_m else "")[:1500]
            codes_in_cond = re.findall(r"\b([BCUYELNPR]\d{3})\b", condiciones, re.I)
            codes_in_cond = [c.upper() for c in codes_in_cond]
            ind_m = re.search(
                r"Indicaciones especiales/Documentos presentados/Certificados y autorizaciones:\s*(.+)$",
                rest,
                re.I,
            )
            indicaciones = (ind_m.group(1).strip() if ind_m else "")[:2000]
            codes_in_ind = re.findall(r"\b([BCUYELNPR]\d{3})\b", indicaciones, re.I)
            codes_in_ind = [c.upper() for c in codes_in_ind]
            blocks.append({
                "medida": measure,
                "ambito_geo": geo[:200],
                "reglamento": reglamento[:80],
                "titulo": title[:300],
                "derechos": derechos[:120],
                "condiciones": condiciones,
                "indicaciones": indicaciones,
                "codes_cond": codes_in_cond,
                "codes_ind": codes_in_ind,
            })
        return blocks

    def _build_resumen_arancelario(self, blocks):
        """Resumen de derechos/IVA a nivel partida (medidas arancelarias)."""
        lines = []
        for b in blocks or []:
            # Prefer duty-like measures
            if not (b.get("derechos") or re.search(r"Derecho|IVA|Suspensión|LVC", b.get("titulo") or "", re.I)):
                if not b.get("derechos"):
                    continue
            line = "%s — %s" % (b.get("medida") or "", b.get("titulo") or "")
            if b.get("derechos"):
                line += " | Derechos: %s" % b["derechos"]
            if b.get("reglamento"):
                line += " | Regl. %s" % b["reglamento"]
            if b.get("ambito_geo"):
                line += " | %s" % b["ambito_geo"]
            lines.append(line.strip(" —"))
        # unique preserve order
        seen = set()
        out = []
        for line in lines:
            if line not in seen:
                seen.add(line)
                out.append(line)
        return "\n".join(out[:20])

    def enrich_documents_with_context(self, raw, documents):
        """
        Añade a cada documento contexto TARIC AEAT:
        medida, reglamento, ámbito, matriz de condiciones, alternativas, fecha, resumen arancelario.
        """
        text = (raw or {}).get("text") or ""
        blocks = self._parse_measure_blocks(text)
        resumen = self._build_resumen_arancelario(blocks)
        fecha = (raw or {}).get("reference_date") or ""
        nomen_desc = (raw or {}).get("description") or ""
        ageo_default = (raw or {}).get("ageo") or self._ageo()

        enriched = []
        for doc in documents or []:
            item = dict(doc)
            code = (item.get("code") or "").strip().upper()
            # Prefer block where code appears in Indicaciones; else Condiciones
            chosen = None
            for b in blocks:
                if code in (b.get("codes_ind") or []):
                    chosen = b
                    break
            if not chosen:
                for b in blocks:
                    if code in (b.get("codes_cond") or []):
                        chosen = b
                        break
            if not chosen and blocks:
                # fallback: first block with any conditions mentioning docs
                for b in blocks:
                    if b.get("condiciones") or b.get("indicaciones"):
                        chosen = b
                        break

            alts = []
            matriz = ""
            if chosen:
                alts = [
                    c for c in (chosen.get("codes_cond") or [])
                    if c != code
                ]
                # unique
                seen = set()
                alts = [c for c in alts if not (c in seen or seen.add(c))]
                matriz = chosen.get("condiciones") or ""
                item["medida"] = chosen.get("medida") or ""
                item["medida_titulo"] = chosen.get("titulo") or ""
                item["reglamento"] = chosen.get("reglamento") or ""
                item["ambito_geo"] = chosen.get("ambito_geo") or ("ageo %s" % ageo_default)
                item["derechos"] = chosen.get("derechos") or ""
            else:
                item.setdefault("medida", "")
                item.setdefault("medida_titulo", "")
                item.setdefault("reglamento", "")
                item.setdefault("ambito_geo", "ageo %s" % ageo_default)
                item.setdefault("derechos", "")

            is_alt = bool(code and code[0] == "Y") or (
                item.get("source") == "aeat_regex_cond" and code[:1] in ("B", "Y")
            )
            # Also mark as alternative if appears alongside other codes in matrix
            if alts and code and code[0] in ("B", "Y", "C"):
                # C codes that apply duty after certificate are often matrix cells
                if code[0] in ("B", "Y") or "alternativa" in (item.get("name") or "").lower():
                    is_alt = True

            item["es_alternativa"] = is_alt
            item["matriz_condiciones"] = matriz[:2000]
            item["codigos_alternativos"] = ", ".join(alts[:20])
            item["fecha_consulta"] = fecha
            item["nomenclatura_desc"] = nomen_desc[:300]
            item["resumen_arancelario"] = resumen[:4000]
            enriched.append(item)
        return enriched

    # Perfiles lógicos conocidos (no inventan códigos; solo clasifican los ya presentes).
    _MEASURE_PROFILES = {
        "710-CITES": {
            "kind": "mandatory_control",
            "question": "¿La mercancía contiene especies/materiales sujetos a CITES?",
            "yes_pref": ("C400",),
            "no_pref": ("Y900",),
        },
        "705-TRIMP": {
            "kind": "mandatory_control",
            "question": (
                "¿Es un bien regulado por el régimen de productos para tortura "
                "(p.ej. silla de inmovilización con dispositivos de sujeción)?"
            ),
            "yes_pref": ("C064",),
            "no_pref": ("Y904",),
        },
        "117-SUSSH": {
            "kind": "optional_benefit",
            "question": (
                "¿Se acoge a la suspensión arancelaria para mercancías destinadas "
                "a determinados buques/plataformas?"
            ),
            "yes_pref": ("C990",),
            "no_pref": (),
        },
        "745-FURIM": {
            "kind": "declaration",
            "question": "¿La mercancía contiene piel de perro o de gato?",
            "yes_pref": (),
            "no_pref": ("Y922",),
        },
        # Control previo SOIVRE (AEAT: SVI-SOVIM importación / SVX-SOVEX exportación)
        "SVI-SOVIM": {
            "kind": "mandatory_control",
            "question": (
                "¿La mercancía está sujeta a control previo SOIVRE en importación? "
                "Compruebe si aplica el certificado/NRC de control."
            ),
            "yes_pref": (),
            "no_pref": (),
        },
        "SVX-SOVEX": {
            "kind": "mandatory_control",
            "question": (
                "¿La mercancía está sujeta a control previo SOIVRE en exportación? "
                "Compruebe si aplica el certificado/NRC de control."
            ),
            "yes_pref": (),
            "no_pref": (),
        },
    }

    def _role_for_code(self, code, label=""):
        code = (code or "").upper()
        if not code:
            return "other"
        if code[0] == "B":
            return "branch"
        if code[0] == "Y":
            low = (label or "").lower()
            if "no autoriz" in low or "prohib" in low:
                return "deny"
            return "declaration"
        if code[0] in ("C", "U", "E", "L", "N", "P", "R"):
            return "document"
        return "other"

    def _code_labels_from_block(self, block):
        """Map code -> best label from indicaciones then condiciones."""
        labels = {}
        for src_key in ("indicaciones", "condiciones"):
            chunk = block.get(src_key) or ""
            for match in re.finditer(
                r"\b([BCUYELNPR]\d{3})\s+(.+?)(?=\s+[BCUYELNPR]\d{3}\b|$)",
                chunk,
                re.I,
            ):
                code = match.group(1).upper()
                detail = re.sub(r"\s+", " ", match.group(2)).strip(" -–,;")
                detail = re.split(
                    r"\b(?:TM\s+\d+|705-TRIMP|Exclusiones:|A\.GEO\.)\b",
                    detail,
                    maxsplit=1,
                )[0].strip(" -–,;")
                if code not in labels and detail and not self._is_generic_label(detail):
                    labels[code] = detail[:300]
                elif code not in labels and detail:
                    labels[code] = detail[:120]
        return labels

    def build_taric_structure(self, raw, direction=None, country_code=None):
        """
        Estructura TARIC completa: medidas + condiciones + documentos derivados
        (sin convertir B001/B002 en documentos ni marcar todo obligatorio).
        """
        import json

        text = (raw or {}).get("text") or ""
        blocks = self._parse_measure_blocks(text)
        resumen = self._build_resumen_arancelario(blocks)
        fecha = (raw or {}).get("reference_date") or ""
        nomen_desc = (raw or {}).get("description") or ""
        goods = (raw or {}).get("goods_code") or ""

        # Nombres útiles desde extract_documents_regex / indicaciones
        name_by_code = {}
        for d in self.extract_documents_regex(raw):
            code = (d.get("code") or "").upper()
            if code and code[0] != "B":
                name_by_code[code] = d.get("name") or code

        medidas = []
        for block in blocks:
            measure = block.get("medida") or ""
            profile = self._MEASURE_PROFILES.get(measure, {})
            labels = self._code_labels_from_block(block)
            for code, lab in labels.items():
                name_by_code.setdefault(code, lab)

            # Condiciones ordenadas según aparición en texto Condiciones
            cond_text = block.get("condiciones") or ""
            ordered_codes = []
            for m in re.finditer(r"\b([BCUYELNPR]\d{3})\b", cond_text, re.I):
                c = m.group(1).upper()
                if c not in ordered_codes:
                    ordered_codes.append(c)
            # Añadir códigos solo en indicaciones
            for c in block.get("codes_ind") or []:
                if c not in ordered_codes:
                    ordered_codes.append(c)

            condiciones = []
            for idx, code in enumerate(ordered_codes, start=1):
                label = labels.get(code) or name_by_code.get(code) or code
                role = self._role_for_code(code, label)
                condiciones.append({
                    "sequence": idx * 10,
                    "condition_branch": code if role == "branch" else False,
                    "certificate_code": code if role != "branch" else False,
                    "name": label[:300],
                    "role": role,
                    "action_label": label[:200],
                })

            kind = profile.get("kind")
            if not kind:
                if measure.startswith(("SVI-", "SVX-")) or "SOIVRE" in (block.get("titulo") or "").upper():
                    kind = "mandatory_control"
                elif block.get("condiciones") or block.get("codes_ind"):
                    kind = "other"
                elif block.get("derechos"):
                    kind = "duty_info"
                else:
                    kind = "other"

            question = profile.get("question") or False
            if not question and kind == "mandatory_control" and measure.startswith(("SVI-", "SVX-")):
                question = _(
                    "Compruebe si esta mercancía requiere control previo SOIVRE "
                    "según la medida %s de AEAT."
                ) % measure
            if kind == "duty_info":
                decision_status = "info_only"
            elif kind in ("mandatory_control", "declaration", "optional_benefit"):
                decision_status = "requires_decision"
            else:
                # Si hay C+Y en la misma medida, forzar decisión
                roles = {c["role"] for c in condiciones}
                codes = [c.get("certificate_code") for c in condiciones if c.get("certificate_code")]
                has_c = any((x or "")[:1] == "C" for x in codes)
                has_y = any((x or "")[:1] == "Y" for x in codes)
                if has_c and has_y:
                    kind = "mandatory_control"
                    decision_status = "requires_decision"
                    question = question or _(
                        "Seleccione la alternativa aplicable de la matriz TARIC para %s"
                    ) % measure
                else:
                    decision_status = "info_only"

            # Documentos a crear (nunca ramas Bxxx; Y001/Y002/Y003 genéricos se omiten)
            skip_generic_y = {"Y001", "Y002", "Y003"}
            documentos = []
            cert_codes = [
                c.get("certificate_code")
                for c in condiciones
                if c.get("certificate_code") and c.get("role") in ("document", "declaration")
            ]
            cert_codes = [c for c in cert_codes if c not in skip_generic_y]
            # SOIVRE a veces no trae código C/Y estándar: usar códigos detectados o la propia medida
            if measure.startswith(("SVI-", "SVX-")) and not cert_codes:
                for c in (block.get("codes_ind") or []) + (block.get("codes_cond") or []):
                    if c not in skip_generic_y and c not in cert_codes:
                        cert_codes.append(c)
                if not cert_codes:
                    cert_codes = ["SOIVRE"]
                    name_by_code.setdefault(
                        "SOIVRE",
                        _("Control previo SOIVRE (%s)") % measure,
                    )
                    condiciones.append({
                        "sequence": (len(condiciones) + 1) * 10,
                        "condition_branch": False,
                        "certificate_code": "SOIVRE",
                        "name": name_by_code["SOIVRE"],
                        "role": "document",
                        "action_label": "Control previo",
                    })

            yes_prefs = set(profile.get("yes_pref") or ())
            no_prefs = set(profile.get("no_pref") or ())
            paired = bool(yes_prefs & set(cert_codes)) and bool(no_prefs & set(cert_codes))
            if not paired:
                cs = [c for c in cert_codes if c[:1] == "C"]
                ys = [c for c in cert_codes if c[:1] == "Y"]
                paired = bool(cs and ys)

            option_yes = next((c for c in cert_codes if c in yes_prefs), None)
            option_no = next((c for c in cert_codes if c in no_prefs), None)
            if not option_yes:
                option_yes = next((c for c in cert_codes if c[:1] == "C"), None)
            if not option_no:
                option_no = next((c for c in cert_codes if c[:1] == "Y"), None)
            if measure.startswith(("SVI-", "SVX-")) and not option_yes and cert_codes:
                option_yes = cert_codes[0]

            for code in cert_codes:
                name = name_by_code.get(code) or labels.get(code) or code
                if kind == "optional_benefit" and code in yes_prefs:
                    aplic = "optional_benefit"
                    mandatory = False
                    es_alt = True
                elif kind == "declaration" and code in no_prefs:
                    # Declaración habitual (p.ej. Y922): pendiente hasta confirmar
                    aplic = "pending_information"
                    mandatory = False
                    es_alt = False
                elif paired:
                    aplic = "pending_information"
                    mandatory = False
                    es_alt = True
                elif kind == "duty_info":
                    continue
                else:
                    aplic = "pending_information"
                    mandatory = False
                    es_alt = False

                documentos.append({
                    "code": code,
                    "name": name[:200],
                    "description": name[:2000],
                    "mandatory": mandatory,
                    "aplicabilidad": aplic,
                    "es_alternativa": es_alt,
                    "medida": measure,
                    "medida_titulo": block.get("titulo") or "",
                    "reglamento": block.get("reglamento") or "",
                    "ambito_geo": block.get("ambito_geo") or "",
                    "derechos": block.get("derechos") or "",
                    "matriz_condiciones": (block.get("condiciones") or "")[:2000],
                    "codigos_alternativos": ", ".join(
                        [x for x in cert_codes if x != code]
                    ),
                    "fecha_consulta": fecha,
                    "nomenclatura_desc": nomen_desc[:300],
                    "resumen_arancelario": resumen[:4000],
                    "source": "aeat_structure",
                })

            medidas.append({
                "medida": measure,
                "titulo": block.get("titulo") or "",
                "ambito_geo": block.get("ambito_geo") or "",
                "reglamento": block.get("reglamento") or "",
                "derechos": block.get("derechos") or "",
                "condiciones_raw": block.get("condiciones") or "",
                "indicaciones_raw": block.get("indicaciones") or "",
                "kind": kind,
                "decision_question": question,
                "decision_status": decision_status,
                "option_yes_code": option_yes or False,
                "option_no_code": option_no or False,
                "option_yes_label": (
                    name_by_code.get(option_yes) or labels.get(option_yes) or option_yes
                ) if option_yes else False,
                "option_no_label": (
                    name_by_code.get(option_no) or labels.get(option_no) or option_no
                ) if option_no else False,
                "condiciones": condiciones,
                "documentos": documentos,
                "raw": {
                    "measure": measure,
                    "geo": block.get("ambito_geo"),
                    "reglamento": block.get("reglamento"),
                    "condiciones": block.get("condiciones"),
                },
            })

        return {
            "goods_code": goods,
            "fecha": fecha,
            "nomenclatura_desc": nomen_desc,
            "resumen_arancelario": resumen,
            "medidas": medidas,
            "raw_json": json.dumps(
                {
                    "taric": goods,
                    "fecha": fecha,
                    "medidas": [m.get("raw") for m in medidas],
                },
                ensure_ascii=False,
            ),
        }
