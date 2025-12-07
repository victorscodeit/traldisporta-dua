# -*- coding: utf-8 -*-
{
    "name": "Aduanas Transporte España ↔ Andorra (Unificado)",
    "summary": "Expedientes aduaneros de Exportación (AES) e Importación (DUA) con AEAT. Origen de datos MSoft. Bandeja AEAT.",
    "version": "17.0.1.0.0",
    "category": "Operations/Logistics",
    "author": "Indomit / Traldisporta",
    "license": "LGPL-3",
    "website": "https://indomitlab.com",
    "depends": ["base", "mail", "contacts", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/aduana_incidencia_views.xml",
        "views/res_config_settings_views.xml",
        "views/aduana_expediente_views.xml",
        "views/factura_carga_views.xml",
        "wizards/msoft_import_views.xml",
        "data/ir_cron.xml",
        "reports/dua_report.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "external_dependencies_optional": {
        "python": ["pdfplumber", "PyPDF2", "openai", "PyMuPDF"],
    },
    "assets": {
        "web.assets_backend": [
            "aduanas_transport/static/src/js/multi_file_upload_action.js",
            "aduanas_transport/static/src/xml/multi_file_upload_action.xml",
        ],
    },
    "application": True,
    "installable": True,
}