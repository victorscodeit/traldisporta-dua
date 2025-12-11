# -*- coding: utf-8 -*-
{
    "name": "Aduanas Transporte España ↔ Andorra (Unificado)",
    "summary": "Expedientes aduaneros de Exportación (AES) e Importación (DUA) con AEAT. Origen de datos MSoft. Bandeja AEAT.",
    "version": "16.0.1.0.0",
    "category": "Operations/Logistics",
    "author": "Indomit / Traldisporta",
    "license": "LGPL-3",
    "website": "https://indomitlab.com",
    "depends": ["base", "mail", "contacts", "web", "queue_job"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/aduanas_config_views.xml",
        "views/aduana_expediente_views.xml",
        "views/aduana_incidencia_views.xml",
        "views/factura_carga_views.xml",
        "wizards/subir_facturas_wizard_views.xml",
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
            "aduanas_transport/static/src/js/expediente_tree_extend.js",
            "aduanas_transport/static/src/xml/expediente_list_button.xml",
            "aduanas_transport/static/src/js/subir_facturas_wizard.js",
            "aduanas_transport/static/src/css/subir_facturas_wizard.css",
        ],
    },
    "application": True,
    "installable": True,
}