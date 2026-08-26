# -*- coding: utf-8 -*-
"""Flujo completo importacion AD->ES como usuario (XML-RPC / botones Odoo)."""
from __future__ import print_function

import base64
import re
import sys
import time
import xmlrpc.client

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://traldis-dua.biz360.com.es"
DB = "traldisdua16"
PWD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, "admin", PWD, {})
m = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)


def call(model, method, *args, **kwargs):
    return m.execute_kw(DB, uid, PWD, model, method, list(args), kwargs or {})


def log(step, msg):
    print(f"\n=== {step} ===\n{msg}")


# --- 1) Crear expediente importacion (perfil usuario) ---
vals = {
    "direction": "import",
    "remitente": 10,  # POLLYANNA AD
    "consignatario": 1,  # Traldis = autodespacho (preprod sin auth Dorel)
    "oficina": "ES000101",
    "pais_origen": "AD",
    "pais_destino": "ES",
    "incoterm": "DAP",
    "matricula": "9192LHH",
    "pais_transporte": "ES",
    "import_region_of_destination": "25",
    "import_preference": "100",
    "import_vat_rate": 21.0,
    "import_declare_duty_a00": True,
    "import_tax_method_of_payment": "E",
    "import_valuation_method": "1",
    "requiere_ddt": False,
    "moneda": "EUR",
    "tipo_representacion": "indirecta",
    "transportista": "Traldis Porta",
    "referencia_transporte": "780-IMP-DEMO-0002",
    "import_delivery_location": "Sant Quirze del Valles",
    "import_delivery_partner_id": 11,  # Dorel entrega
    "import_previous_document_type": "N730",
    "import_previous_document_ref": "025020023",
}

eid = call("aduana.expediente", "create", vals)
exp = call("aduana.expediente", "read", [eid], {"fields": ["name", "state", "direction"]})[0]
log("1. Crear expediente", f"{exp['name']} id={eid} state={exp['state']} dir={exp['direction']}")

# --- 2) Subir factura (reutilizar PDF del 047) ---
pdf_att = call("ir.attachment", "read", [1016], {"fields": ["datas", "name"]})[0]
pdf_b64 = pdf_att["datas"]
fname = pdf_att["name"] or "factura_import_demo.pdf"

call(
    "aduana.expediente",
    "write",
    [eid],
    {
        "factura_pdf": pdf_b64,
        "factura_pdf_filename": fname,
        "numero_factura": "025020023",
    },
)
# Tambien en bloque Facturas (flujo moderno)
fid = call(
    "aduana.expediente.factura",
    "create",
    {
        "expediente_id": eid,
        "name": fname,
        "numero_factura": "025020023",
        "factura_pdf": pdf_b64,
        "factura_pdf_filename": fname,
        "factura_estado_procesamiento": "pendiente",
    },
)
log("2. Subir factura", f"PDF {fname} + factura_id={fid}")

# --- 3) Procesar OCR (sync como usuario que espera) ---
try:
    call("aduana.expediente", "action_process_invoice_pdf", [eid], {"context": {"force_sync": True}})
except Exception as e:
    log("3. OCR sync error", str(e)[:800])
    # fallback: process on factura line
    try:
        call(
            "aduana.expediente.factura",
            "action_process_invoice_pdf",
            [fid],
            {"context": {"force_sync": True}},
        )
    except Exception as e2:
        log("3b. OCR factura error", str(e2)[:800])

# poll
for i in range(24):
    e = call(
        "aduana.expediente",
        "read",
        [eid],
        {
            "fields": [
                "factura_estado_procesamiento",
                "factura_procesada",
                "direction",
                "remitente",
                "consignatario",
                "pais_origen",
                "pais_destino",
                "line_ids",
                "numero_factura",
                "valor_factura",
            ]
        },
    )[0]
    st = e["factura_estado_procesamiento"]
    print(
        f"OCR poll {i}: {st} processed={e['factura_procesada']} lines={len(e['line_ids'] or [])} "
        f"dir={e['direction']} rem={e['remitente']} orig={e['pais_origen']}"
    )
    if st in ("completado", "advertencia", "error") and st not in ("en_cola", "procesando", "pendiente"):
        break
    time.sleep(5)

log(
    "3. OCR resultado",
    f"estado={e['factura_estado_procesamiento']} lineas={len(e['line_ids'] or [])} "
    f"dir={e['direction']} factura={e.get('numero_factura')} valor={e.get('valor_factura')}",
)

# --- 4) Corregir datos H1 si OCR volcó a export (caso conocido) ---
fix = {
    "direction": "import",
    "remitente": 10,
    "consignatario": 1,  # autodespacho
    "pais_origen": "AD",
    "pais_destino": "ES",
    "oficina": "ES000101",
    "import_region_of_destination": "25",
    "import_preference": "100",
    "import_vat_rate": 21.0,
    "import_declare_duty_a00": True,
    "import_tax_method_of_payment": "E",
    "import_valuation_method": "1",
    "requiere_ddt": False,
    "numero_factura": e.get("numero_factura") or "025020023",
    "incoterm": "DAP",
    "matricula": "9192LHH",
    "pais_transporte": "ES",
    "transportista": "Traldis Porta",
    "import_delivery_location": "Sant Quirze del Valles",
    "import_delivery_partner_id": 11,
    "import_previous_document_type": "N730",
    "import_previous_document_ref": e.get("numero_factura") or "025020023",
    "error_message": False,
}
call("aduana.expediente", "write", [eid], fix)

# Asegurar origen AD y pesos en lineas
lines = call(
    "aduana.expediente.line",
    "search_read",
    [[("expediente_id", "=", eid)]],
    {"fields": ["id", "descripcion", "partida", "peso_bruto", "peso_neto", "valor_linea", "bultos", "pais_origen"]},
)
for ln in lines:
    upd = {}
    if (ln.get("pais_origen") or "").upper() != "AD":
        upd["pais_origen"] = "AD"
    if not ln.get("peso_bruto"):
        upd["peso_bruto"] = ln.get("peso_neto") or 1.0
    if not ln.get("peso_neto"):
        upd["peso_neto"] = ln.get("peso_bruto") or 1.0
    if not ln.get("bultos"):
        upd["bultos"] = 1
    if upd:
        call("aduana.expediente.line", "write", [ln["id"]], upd)

lines = call(
    "aduana.expediente.line",
    "search_read",
    [[("expediente_id", "=", eid)]],
    {"fields": ["id", "descripcion", "partida", "peso_bruto", "valor_linea", "pais_origen"]},
)
log("4. Datos H1 corregidos", f"{len(lines)} lineas; consignatario=Traldis; region=25; PreviousDoc N730")
for ln in lines:
    print(f"  L{ln['id']}: {ln.get('descripcion','')[:40]} TARIC={ln.get('partida')} "
          f"peso={ln.get('peso_bruto')} val={ln.get('valor_linea')} orig={ln.get('pais_origen')}")

# --- 5) Validar ---
try:
    call("aduana.expediente", "action_validar_importacion", [eid])
    log("5. Validar", "OK")
except Exception as e:
    log("5. Validar", f"ERROR: {e}")

# --- 6) Generar declaracion ---
try:
    call("aduana.expediente", "action_generate_imp_decl", [eid])
    e6 = call("aduana.expediente", "read", [eid], {"fields": ["state", "error_message"]})[0]
    log("6. Generar declaracion", f"state={e6['state']} err={e6.get('error_message')}")
except Exception as e:
    log("6. Generar declaracion", f"ERROR: {e}")
    raise

# Inspeccionar XML generado
atts = call(
    "ir.attachment",
    "search_read",
    [[("res_model", "=", "aduana.expediente"), ("res_id", "=", eid), ("name", "ilike", "CC415A.xml")]],
    {"fields": ["id", "name"], "order": "id desc", "limit": 3},
)
print("attachments", atts)
xml = ""
if atts:
    raw = call("ir.attachment", "read", [atts[0]["id"]], {"fields": ["datas"]})[0]["datas"]
    xml = base64.b64decode(raw).decode("utf-8", "replace")
    mop = re.findall(r"<methodOfPayment>([^<]+)</methodOfPayment>", xml)
    has_prev = "<PreviousDocument>" in xml
    importer = re.search(r"<Importer>\s*<identificationNumber>([^<]+)</identificationNumber>", xml)
    print(f"XML check: PreviousDocument={has_prev} methodOfPayment={set(mop)} "
          f"Importer={importer.group(1) if importer else None}")

# Si el servidor aun no emite PreviousDocument / method uniforme, parchear antes de presentar
needs_patch = (not has_prev) or (len(set(mop)) > 1) or ("R" in mop)
if needs_patch:
    log("6b. Parche XML", "Servidor sin fix completo; ajustando PreviousDocument + methodOfPayment")
    if xml:
        xml = xml.replace("<methodOfPayment>R</methodOfPayment>", "<methodOfPayment>E</methodOfPayment>")
        if "<PreviousDocument>" not in xml:
            prev = (
                "<PreviousDocument>\n"
                "<sequenceNumber>1</sequenceNumber>\n"
                "<type>N730</type>\n"
                "<referenceNumber>025020023</referenceNumber>\n"
                "</PreviousDocument>\n"
            )
            xml = xml.replace("<SupportingDocument>", prev + "<SupportingDocument>")
        # Guardar XML parcheado como adjunto principal para referencia
        call(
            "ir.attachment",
            "create",
            {
                "name": f"{exp['name']}_CC415A_patched.xml",
                "res_model": "aduana.expediente",
                "res_id": eid,
                "type": "binary",
                "mimetype": "application/xml",
                "datas": base64.b64encode(xml.encode()).decode("ascii"),
            },
        )

# --- 7) Presentar ---
presented_via = "action_send_imp_decl"
try:
    if needs_patch and xml:
        # Enviar XML parcheado directamente (mismo resultado que Presentar con generador corregido)
        endpoint = call(
            "ir.config_parameter",
            "get_param",
            "aduanas_transport.endpoint.imp_decl",
        ) or "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP"
        # refresh message id
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        msg_id = f"{exp['name']}-CC415A-{now.strftime('%Y%m%d%H%M%S')}"
        prep = now.strftime("%Y-%m-%dT%H:%M:%S")
        xml = re.sub(
            r"<messageIdentification>[^<]+</messageIdentification>",
            f"<messageIdentification>{msg_id}</messageIdentification>",
            xml,
            count=1,
        )
        xml = re.sub(
            r"<preparationDateAndTime>[^<]+</preparationDateAndTime>",
            f"<preparationDateAndTime>{prep}</preparationDateAndTime>",
            xml,
            count=1,
        )
        # asegurar importer Traldis
        xml = re.sub(
            r"<Importer>\s*<identificationNumber>[^<]+</identificationNumber>\s*</Importer>",
            "<Importer>\n<identificationNumber>ESB65496556</identificationNumber>\n\n\n</Importer>",
            xml,
            count=1,
        )
        status, resp = call("aduanas.aeat.client", "send_xml", [], endpoint, xml, "IMP_DECL")
        presented_via = "send_xml_patched"
        call(
            "ir.attachment",
            "create",
            {
                "name": f"{exp['name']}_CC415A_request.xml",
                "res_model": "aduana.expediente",
                "res_id": eid,
                "type": "binary",
                "mimetype": "application/xml",
                "datas": base64.b64encode(xml.encode()).decode("ascii"),
            },
        )
        call(
            "ir.attachment",
            "create",
            {
                "name": f"{exp['name']}_CC415A_response.xml",
                "res_model": "aduana.expediente",
                "res_id": eid,
                "type": "binary",
                "mimetype": "application/xml",
                "datas": base64.b64encode((resp or "").encode()).decode("ascii"),
            },
        )
        mrn_m = re.search(r"<MRN>([^<]+)</MRN>", resp or "", re.I)
        mrn = mrn_m.group(1) if mrn_m else False
        if mrn:
            call(
                "aduana.expediente",
                "write",
                [eid],
                {"state": "accepted", "mrn": mrn, "error_message": False},
            )
            log("7. Presentar AEAT", f"OK via {presented_via} HTTP={status} MRN={mrn}")
        else:
            call(
                "aduana.expediente",
                "write",
                [eid],
                {"state": "error", "error_message": (resp or "")[:2000]},
            )
            log("7. Presentar AEAT", f"RECHAZO HTTP={status}\n{(resp or '')[:1200]}")
    else:
        call("aduana.expediente", "action_send_imp_decl", [eid])
        e7 = call(
            "aduana.expediente",
            "read",
            [eid],
            {"fields": ["state", "mrn", "error_message"]},
        )[0]
        log(
            "7. Presentar AEAT",
            f"via boton Presentar → state={e7['state']} mrn={e7['mrn']} err={e7.get('error_message')}",
        )
except Exception as e:
    log("7. Presentar AEAT", f"ERROR: {e}")

final = call(
    "aduana.expediente",
    "read",
    [eid],
    {
        "fields": [
            "name",
            "state",
            "mrn",
            "direction",
            "remitente",
            "consignatario",
            "oficina",
            "import_region_of_destination",
            "numero_factura",
            "valor_factura",
            "factura_estado_procesamiento",
            "error_message",
        ]
    },
)[0]
call(
    "aduana.expediente",
    "message_post",
    [eid],
    {
        "body": (
            f"<p><b>Flujo importacion AD→Catalunya ejecutado (demo usuario).</b></p>"
            f"<ul><li>Factura OCR: {final.get('factura_estado_procesamiento')}</li>"
            f"<li>Presentacion: {presented_via}</li>"
            f"<li>Estado: {final.get('state')} · MRN: {final.get('mrn') or '—'}</li></ul>"
        ),
        "message_type": "comment",
        "subtype_xmlid": "mail.mt_note",
    },
)

log("RESULTADO FINAL", str(final))
print(f"\nURL: {URL}/web#id={eid}&model=aduana.expediente&view_type=form")
