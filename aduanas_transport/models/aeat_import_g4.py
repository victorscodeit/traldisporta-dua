# -*- coding: utf-8 -*-
"""G4 / depósito temporal — presentación G4DecV1SOAP (distinto de CC415A H1)."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.aduanas_transport.services.g4_xml_builder import G4_DEC_DEFAULT_ENDPOINT


class AeatImportG4TemporaryStorage(models.Model):
    _name = "aeat.import.g4.temporary.storage"
    _description = "G4 depósito temporal (G4Dec AEAT)"
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
    lrn = fields.Char(
        string="LRN G4",
        help="Número de referencia local (máx. 22). Si está vacío se genera desde el expediente.",
    )
    mrn = fields.Char(
        string="MRN G4/DDT",
        help="MRN devuelto por AEAT al presentar G4. Se copia al expediente (mrn_ddt) al aceptar.",
    )
    endpoint_url = fields.Char(
        string="Endpoint G4Dec",
        readonly=True,
        help="Servicio G4DecV1SOAP (ADDS-JDIT). No usar CC415AV1SOAP ni endpoints AES.",
    )
    request_xml = fields.Text(string="XML petición G4", readonly=True)
    response_xml = fields.Text(string="XML respuesta G4", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)

    def _get_g4_endpoint(self):
        self.ensure_one()
        settings = self.expediente_id._get_settings()
        return (
            settings.get("aeat_endpoint_g4_dec")
            or G4_DEC_DEFAULT_ENDPOINT
        )

    def _ensure_cert_configured(self):
        icp = self.env["ir.config_parameter"].sudo()
        attach_id = int(icp.get_param("aduanas_transport.cert_attachment_id") or 0)
        password = (icp.get_param("aduanas_transport.cert_password") or "").strip()
        if not attach_id or not password:
            raise UserError(
                _(
                    "Configure el certificado AEAT (.p12) y su contraseña en "
                    "Aduanas → Configuración antes de presentar G4."
                )
            )

    def action_generar_xml_g4(self):
        builder = self.env["aduanas.g4.xml.builder"]
        for rec in self:
            endpoint = rec._get_g4_endpoint()
            xml = builder.build_g4_soap_envelope(rec, endpoint_url=endpoint)
            lrn = builder._lrn(rec, rec.expediente_id)
            rec.write({
                "request_xml": xml,
                "endpoint_url": endpoint,
                "lrn": lrn,
                "state": "generated",
                "error_message": False,
            })
            rec.expediente_id._attach_xml(
                "%s_G4Dec_request.xml" % (rec.expediente_id.name or "G4"),
                xml,
            )
        return True

    def action_presentar_g4(self):
        client = self.env["aduanas.aeat.client"]
        parser = self.env["aduanas.xml.parser"]
        builder = self.env["aduanas.g4.xml.builder"]
        for rec in self:
            rec._ensure_cert_configured()
            endpoint = rec._get_g4_endpoint()
            xml = rec.request_xml
            if not (xml or "").strip() or rec.state == "draft":
                xml = builder.build_g4_soap_envelope(rec, endpoint_url=endpoint)
                rec.write({
                    "request_xml": xml,
                    "lrn": builder._lrn(rec, rec.expediente_id),
                })
            rec.write({
                "endpoint_url": endpoint,
                "state": "presented",
                "error_message": False,
            })
            rec.expediente_id._attach_xml(
                "%s_G4Dec_request.xml" % (rec.expediente_id.name or "G4"),
                xml,
            )
            status_code, resp_xml = client.send_xml(
                endpoint, xml, service="G4_DEC", timeout=60
            )
            rec.response_xml = resp_xml or ""
            rec.expediente_id._attach_xml(
                "%s_G4Dec_response.xml" % (rec.expediente_id.name or "G4"),
                resp_xml or "",
            )
            if status_code != 200:
                rec.state = "error"
                rec.error_message = _("AEAT respondió HTTP %s. Revise el XML de respuesta.") % status_code
                raise UserError(rec.error_message)
            parsed = parser.parse_g4_dec_response(resp_xml)
            if parsed.get("success"):
                rec.state = "accepted"
                if parsed.get("mrn"):
                    rec.mrn = parsed["mrn"]
                if parsed.get("lrn") and not rec.lrn:
                    rec.lrn = parsed["lrn"]
                rec.error_message = False
                if rec.mrn:
                    rec.expediente_id._aplicar_mrn_ddt_desde_g4(rec.mrn.strip())
                rec.expediente_id.with_context(mail_notrack=True).message_post(
                    body=_(
                        "G4/depósito temporal aceptado. MRN: %s. LRN: %s"
                    )
                    % (rec.mrn or _("—"), rec.lrn or _("—")),
                    subtype_xmlid="mail.mt_note",
                )
            else:
                rec.state = "error"
                errors = parsed.get("errors") or [parsed.get("error") or _("Rechazo G4")]
                rec.error_message = "\n".join(e for e in errors if e)
                raise UserError(
                    _("AEAT rechazó la G4:\n%s") % rec.error_message
                )
        return True

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
        existing = self.search(
            [("expediente_id", "=", expediente.id)],
            limit=1,
            order="id desc",
        )
        if existing:
            return existing
        return self.create({
            "expediente_id": expediente.id,
            "state": "draft",
        })
