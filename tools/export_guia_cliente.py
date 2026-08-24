#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera la guía Traldis Porta en HTML presentable para el cliente (imprimible a PDF).

Uso:
    python tools/export_guia_cliente.py

Salida:
    aduanas_transport/doc/GUIA_TRALDIS_PORTA_CLIENTE.html
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    import markdown
except ImportError as exc:
    raise SystemExit("Instale markdown: pip install markdown") from exc

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aduanas_transport" / "doc" / "GUIA_TRALDIS_PORTA_CLIENTE.md"
OUT = ROOT / "aduanas_transport" / "doc" / "GUIA_TRALDIS_PORTA_CLIENTE.html"

CLIENT_NAME = "Traldis Porta"
PRODUCT = "Módulo Odoo Aduanas (aduanas_transport)"
MANIFEST = ROOT / "aduanas_transport" / "__manifest__.py"
VERSION = "1.6"


def _module_version() -> str:
    if MANIFEST.is_file():
        m = re.search(r'"version"\s*:\s*"([^"]+)"', MANIFEST.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return "?"


def _strip_repo_links(md: str) -> str:
    """Sustituye enlaces a .md internos por texto legible para el cliente."""
    md = re.sub(
        r"\[([^\]]+)\]\([A-Za-z0-9_./-]+\.md\)",
        r"\1 (documentación técnica interna)",
        md,
    )
    md = re.sub(r"^> \*\*Perfil por defecto.*\n\n---\n\n", "", md, flags=re.MULTILINE)
    md = md.replace(
        "## 10. Documentación técnica complementaria\n\n"
        "| Documento | Contenido |\n"
        "|-----------|-----------|\n"
        "| [README.md](README.md) | Índice de toda la documentación del módulo |\n"
        "| [FLUJO_EXPORTACION_ES_AD.md](FLUJO_EXPORTACION_ES_AD.md) | Export AES paso a paso |\n"
        "| [FLUJO_IMPORTACION_AD_ES.md](FLUJO_IMPORTACION_ES_AD.md) | Import H1, G4/DDT |\n"
        "| [CONFIGURAR_CERTIFICADO_AEAT.md](CONFIGURAR_CERTIFICADO_AEAT.md) | Certificado P12 |\n"
        "| [PRESENTACION_DUA_Y_PREPRODUCCION.md](PRESENTACION_DUA_Y_PREPRODUCCION.md) | Preprod (parcial; ver nota al inicio) |\n"
        "| [RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md](RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md) | Referencia campos EXS/DDT |\n\n"
        "**Referencias oficiales AEAT:** Guía WEB Exp (AES), Guía técnica Importación CAU v3.x (H1).\n",
        "## 10. Referencias oficiales\n\n"
        "- **AEAT — Guía WEB Exp** (exportación AES)\n"
        "- **AEAT — Guía técnica Importación CAU** v3.x (importación H1)\n",
    )
    return md


def _html_template(body: str) -> str:
    mod_ver = _module_version()
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Guía operativa — {CLIENT_NAME}</title>
  <style>
    :root {{
      --brand: #1a4d6d;
      --brand-light: #e8f1f6;
      --accent: #c45c26;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #d1d5db;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.55;
      color: var(--text);
      margin: 0;
      background: #f3f4f6;
    }}
    .page {{
      max-width: 210mm;
      margin: 0 auto 24px;
      background: #fff;
      box-shadow: 0 2px 12px rgba(0,0,0,.08);
    }}
    .cover {{
      position: relative;
      min-height: 297mm;
      padding: 48px 56px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      color: #fff;
      page-break-after: always;
      overflow: hidden;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    .cover-bg {{
      position: absolute;
      inset: 0;
      z-index: 0;
      background-color: #1a4d6d;
      background-image: linear-gradient(160deg, #1a4d6d 0%, #0f3347 55%, #1a4d6d 100%);
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    .cover-inner,
    .cover-meta {{
      position: relative;
      z-index: 1;
    }}
    .cover-badge {{
      display: inline-block;
      background: rgba(255,255,255,.15);
      border: 1px solid rgba(255,255,255,.35);
      padding: 6px 14px;
      border-radius: 4px;
      font-size: 10pt;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .cover h1 {{
      font-size: 28pt;
      font-weight: 700;
      line-height: 1.2;
      margin: 32px 0 12px;
      max-width: 14ch;
      color: #fff;
    }}
    .cover .subtitle {{
      font-size: 14pt;
      opacity: .92;
      max-width: 36ch;
      color: #fff;
    }}
    .cover-meta {{
      border-top: 1px solid rgba(255,255,255,.3);
      padding-top: 24px;
      font-size: 10pt;
      opacity: .9;
      color: #fff;
    }}
    .cover-meta p {{ margin: 4px 0; color: #fff; }}
    .cover-badge {{ color: #fff; }}
    .content {{
      padding: 40px 56px 56px;
    }}
    h1, h2, h3 {{ color: var(--brand); }}
    h2 {{
      font-size: 16pt;
      margin-top: 2em;
      padding-bottom: 6px;
      border-bottom: 2px solid var(--brand-light);
      page-break-after: avoid;
    }}
    h3 {{
      font-size: 12pt;
      margin-top: 1.4em;
      page-break-after: avoid;
    }}
    p {{ margin: .6em 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1em 0 1.4em;
      font-size: 10pt;
      page-break-inside: avoid;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--brand-light);
      color: var(--brand);
      font-weight: 600;
    }}
    tr:nth-child(even) td {{ background: #fafafa; }}
    code, pre {{
      font-family: Consolas, "Courier New", monospace;
      font-size: 9pt;
    }}
    pre {{
      background: #f8fafc;
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      overflow-x: auto;
      white-space: pre-wrap;
      page-break-inside: avoid;
    }}
    blockquote {{
      margin: 1em 0;
      padding: 10px 16px;
      background: var(--brand-light);
      border-left: 4px solid var(--brand);
      color: #374151;
    }}
    ul {{ padding-left: 1.4em; }}
    li {{ margin: .35em 0; }}
    li input[type=checkbox] {{ margin-right: 6px; }}
    hr {{
      border: none;
      border-top: 1px solid var(--border);
      margin: 2em 0;
    }}
    @media print {{
      html, body {{
        background: #fff;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .page {{ box-shadow: none; margin: 0; max-width: none; }}
      .no-print {{ display: none; }}
      h2 {{ page-break-before: auto; }}
      th {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      tr:nth-child(even) td {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .cover {{
        min-height: 297mm;
        height: 297mm;
        padding: 22mm 20mm 18mm;
        margin: 0;
        box-sizing: border-box;
        page-break-after: always;
        break-after: page;
      }}
      .cover-bg {{
        inset: 0;
      }}
    }}
    @page {{
      size: A4;
      margin: 18mm 16mm;
    }}
    @page :first {{
      margin: 0;
    }}
    .print-hint {{
      max-width: 210mm;
      margin: 12px auto;
      padding: 12px 16px;
      background: #fffbeb;
      border: 1px solid #fcd34d;
      border-radius: 6px;
      font-size: 10pt;
    }}
  </style>
</head>
<body>
  <div class="print-hint no-print">
    <strong>Exportar a PDF:</strong> Ctrl+P → «Guardar como PDF». Si la portada sale sin fondo azul, active «Gráficos de fondo» / «Background graphics» en opciones de impresión.
  </div>
  <div class="page">
    <section class="cover">
      <div class="cover-bg" aria-hidden="true"></div>
      <div class="cover-inner">
        <span class="cover-badge">Documentación operativa</span>
        <h1>Guía de uso Aduanas</h1>
        <p class="subtitle">{PRODUCT}<br/>Perfil agente aduanero y transportista</p>
      </div>
      <div class="cover-meta">
        <p><strong>Versión documento:</strong> {VERSION}</p>
        <p><strong>Módulo Odoo:</strong> {mod_ver}</p>
      </div>
    </section>
    <article class="content">
      {body}
    </article>
  </div>
</body>
</html>"""


def main():
    if not SRC.is_file():
        raise SystemExit(f"No se encuentra {SRC}")
    md = SRC.read_text(encoding="utf-8")
    md = _strip_repo_links(md)
    md = re.sub(r"^# Guía del módulo Aduanas — Traldis Porta\s*\n", "", md, count=1)
    body = markdown.markdown(
        md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )
    OUT.write_text(_html_template(body), encoding="utf-8")
    print(f"Generado: {OUT}")
    print("Abra el HTML en el navegador y use Imprimir -> Guardar como PDF.")


if __name__ == "__main__":
    main()
