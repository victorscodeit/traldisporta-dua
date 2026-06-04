# -*- coding: utf-8 -*-
"""G4 / depósito temporal: integración futura (endpoint y XML propios, no CC415A H1)."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AeatImportG4TemporaryStorage(models.Model):
    _name = "aeat.import.g4.temporary.storage"
    _description = "G4 depósito temporal (stub AEAT, separado de CC415A)"
    _order = "create_date desc"

    expediente_id = fields.Many2one(
        "aduana.expediente",
        string="Expediente importación",
        required=True,
        ondelete="cascade",
        index=True,
    )
    ddt_type = fields.Selection(
        related="expediente_id.ddt_type",
        readonly=True,
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
    lrn = fields.Char(string="LRN G4")
    mrn = fields.Char(
        string="MRN G4/DDT",
        help="MRN devuelto por AEAT al presentar G4. Se copia al expediente (mrn_ddt) al aceptar.",
    )
    endpoint_url = fields.Char(
        string="Endpoint G4 (futuro)",
        readonly=True,
        help="WSDL/servicio G4 propio. No usar CC415AV1SOAP ni endpoints AES exportación.",
    )
    request_xml = fields.Text(string="XML petición G4", readonly=True)
    response_xml = fields.Text(string="XML respuesta G4", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)

    def _stub_not_implemented(self):
        raise UserError(
            _(
                "Integración AEAT G4/depósito temporal pendiente de implementación.\n\n"
                "G4 usa su propio endpoint, WSDL y XML (distinto de CC415A/H1).\n"
                "Mientras tanto: presente la DDT/G4 en el canal oficial y copie el MRN "
                "de 18 caracteres en el expediente → campo «MRN DDT/G4» (mrn_ddt)."
            )
        )

    def action_generar_xml_g4(self):
        """Stub: generará el XML de presentación G4 (servicio distinto a CC415A)."""
        for rec in self:
            rec._stub_not_implemented()

    def action_presentar_g4(self):
        """Stub: enviará al endpoint G4 configurado (no al de importación H1)."""
        for rec in self:
            rec._stub_not_implemented()

    def action_aplicar_mrn_al_expediente(self):
        """Copia el MRN G4 al expediente de importación vinculado."""
        for rec in self:
            if not rec.expediente_id:
                raise UserError(_("No hay expediente vinculado."))
            if not (rec.mrn or "").strip():
                raise UserError(_("Indique el MRN G4/DDT en este registro antes de aplicar."))
            rec.expediente_id._aplicar_mrn_ddt_desde_g4(rec.mrn.strip())
            rec.state = "accepted"
        return True

    @api.model
    def create_from_expediente(self, expediente):
        """Crea o reutiliza el registro G4 asociado al expediente de importación."""
        expediente.ensure_one()
        if expediente.direction != "import":
            raise UserError(_("G4/DDT solo aplica a expedientes de importación."))
        existing = self.search([("expediente_id", "=", expediente.id)], limit=1, order="id desc")
        if existing:
            return existing
        return self.create({
            "expediente_id": expediente.id,
            "state": "draft",
        })
