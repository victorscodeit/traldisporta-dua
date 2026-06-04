# -*- coding: utf-8 -*-
"""G3 presentación importación: integración futura (endpoint y XML propios, no CC415A H1)."""
from odoo import fields, models, _
from odoo.exceptions import UserError


class AeatImportG3Presentation(models.Model):
    _name = "aeat.import.g3.presentation"
    _description = "G3 presentación importación (stub AEAT, separado de CC415A)"
    _order = "create_date desc"

    expediente_id = fields.Many2one(
        "aduana.expediente",
        string="Expediente importación",
        ondelete="cascade",
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("generated", "XML generado"),
            ("presented", "Presentado"),
            ("accepted", "Aceptado"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
    )
    lrn = fields.Char(string="LRN G3")
    mrn = fields.Char(string="MRN G3")
    endpoint_url = fields.Char(
        string="Endpoint G3 (futuro)",
        readonly=True,
        help="Servicio G3 propio. No mezclar con CC415AV1SOAP (H1).",
    )
    request_xml = fields.Text(string="XML petición G3", readonly=True)
    response_xml = fields.Text(string="XML respuesta G3", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)

    def _stub_not_implemented(self):
        raise UserError(
            _(
                "Integración AEAT G3 pendiente de implementación.\n"
                "G3 tiene endpoint, WSDL y XML independientes de CC415A/H1."
            )
        )

    def action_generar_xml_g3(self):
        for rec in self:
            rec._stub_not_implemented()

    def action_presentar_g3(self):
        for rec in self:
            rec._stub_not_implemented()
