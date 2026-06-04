# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

CC415A_DEFAULT = "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP"
LEGACY_IMP_DECL = "ADIM-JDIT/ws/imp/DeclaracionSOAP"


def _normalize_imp_decl(endpoint):
    if not endpoint or LEGACY_IMP_DECL in endpoint:
        return CC415A_DEFAULT
    return endpoint


def migrate_aeat_config_to_companies(env):
    """Copia endpoints/certificado desde ir.config_parameter a res.company (una sola vez)."""
    icp = env["ir.config_parameter"].sudo()
    if icp.get_param("aduanas_transport.company_config_migrated") == "1":
        return

    field_params = [
        ("aeat_endpoint_cc515c", "aduanas_transport.endpoint.cc515c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP"),
        ("aeat_endpoint_cc511c", "aduanas_transport.endpoint.cc511c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP"),
        ("aeat_endpoint_ccaesc", "aduanas_transport.endpoint.ccaesc", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP"),
        ("aeat_endpoint_cc507c", "aduanas_transport.endpoint.cc507c", "https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP"),
        ("aeat_endpoint_imp_decl", "aduanas_transport.endpoint.imp_decl", CC415A_DEFAULT),
        ("aeat_endpoint_imp_query", "aduanas_transport.endpoint.imp_query", "https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP"),
        ("aeat_endpoint_bandeja", "aduanas_transport.endpoint.bandeja", "https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP"),
        ("aeat_endpoint_ie615", "aduanas_transport.endpoint.ie615", "https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP"),
    ]

    attach_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
    cert_password = icp.get_param("aduanas_transport.cert_password") or ""
    nif_firmante = icp.get_param("aduanas_transport.aeat_nif_firmante") or ""

    for company in env["res.company"].sudo().search([]):
        vals = {}
        for field_name, param_key, default in field_params:
            current = getattr(company, field_name, False)
            if current:
                if field_name == "aeat_endpoint_imp_decl":
                    normalized = _normalize_imp_decl(current)
                    if normalized != current:
                        vals[field_name] = normalized
                continue
            value = icp.get_param(param_key) or default
            if field_name == "aeat_endpoint_imp_decl":
                value = _normalize_imp_decl(value)
            vals[field_name] = value

        if attach_id and not company.aeat_cert_attachment_id:
            vals["aeat_cert_attachment_id"] = attach_id
        if cert_password and not company.aeat_cert_password:
            vals["aeat_cert_password"] = cert_password
        if nif_firmante and not company.aeat_nif_firmante:
            vals["aeat_nif_firmante"] = nif_firmante

        if vals:
            company.write(vals)

    imp_decl = _normalize_imp_decl(icp.get_param("aduanas_transport.endpoint.imp_decl") or "")
    icp.set_param("aduanas_transport.endpoint.imp_decl", imp_decl)
    icp.set_param("aduanas_transport.company_config_migrated", "1")
    _logger.info("Migración AEAT: configuración copiada a res.company")


def migrate_import_ddt_fields(env):
    """Expedientes import con referencia legacy → requiere_ddt + mrn_ddt."""
    Expediente = env["aduana.expediente"].sudo()
    for exp in Expediente.search([
        ("direction", "=", "import"),
        ("import_previous_document_ref", "!=", False),
        ("requiere_ddt", "=", False),
    ]):
        ref = (exp.import_previous_document_ref or "").strip()
        if ref:
            exp.write({
                "requiere_ddt": True,
                "mrn_ddt": ref,
                "ddt_type": "g4" if exp.import_previous_document_is_g4 else "dsdt",
            })


def post_init_hook(cr, registry):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_aeat_config_to_companies(env)
    migrate_import_ddt_fields(env)
