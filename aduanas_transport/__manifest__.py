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
        "wizards/msoft_import_views.xml",
        "data/ir_cron.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "assets": {},
    "application": True,
    "installable": True,
}