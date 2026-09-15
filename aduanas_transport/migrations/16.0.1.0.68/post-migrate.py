# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.aduanas_transport.hooks import migrate_country_many2one_fields

    migrate_country_many2one_fields(env)
    _logger.info("post-migrate 16.0.1.0.68: países Many2one sincronizados")
