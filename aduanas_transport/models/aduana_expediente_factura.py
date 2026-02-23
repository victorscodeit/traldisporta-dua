# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.queue_job.job import job
    QUEUE_JOB_AVAILABLE = True
except Exception:
    QUEUE_JOB_AVAILABLE = False
    def job(func):
        return func


class AduanaExpedienteFactura(models.Model):
    _name = "aduana.expediente.factura"
    _description = "Factura PDF del expediente"
    _order = "id asc"

    expediente_id = fields.Many2one("aduana.expediente", string="Expediente", required=True, ondelete="cascade", index=True)
    name = fields.Char(string="Factura", default="Factura", help="Nombre o referencia de la factura (p. ej. nombre del archivo)")
    factura_pdf = fields.Binary(string="Factura PDF", attachment=True)
    factura_pdf_filename = fields.Char(string="Nombre archivo")
    factura_estado_procesamiento = fields.Selection([
        ("sin_factura", "Sin Factura"),
        ("pendiente", "Pendiente de Procesar"),
        ("en_cola", "En cola (background)"),
        ("procesando", "Procesando..."),
        ("completado", "Completado"),
        ("error", "Error en Procesamiento"),
        ("advertencia", "Completado con Advertencias"),
    ], string="Estado", default="sin_factura", readonly=True)
    factura_en_cola_at = fields.Datetime(string="Fecha en cola", readonly=True)
    factura_procesada = fields.Boolean(string="Procesada", default=False)
    fecha_procesamiento = fields.Datetime(string="Fecha Procesamiento", readonly=True)
    factura_mensaje_error = fields.Text(string="Mensaje Error/Advertencia", readonly=True)
    factura_mensaje_html = fields.Html(compute="_compute_factura_mensaje_html", store=False, sanitize=False)
    factura_datos_extraidos = fields.Text(string="Datos Extraídos", readonly=True)
    lineas_count = fields.Integer(string="Nº Líneas", compute="_compute_lineas_count", store=False)

    @api.depends("expediente_id", "expediente_id.line_ids", "expediente_id.line_ids.factura_id")
    def _compute_lineas_count(self):
        for rec in self:
            if not rec.expediente_id:
                rec.lineas_count = 0
            else:
                rec.lineas_count = len(rec.expediente_id.line_ids.filtered(lambda l: l.factura_id == rec))

    @api.depends("factura_estado_procesamiento", "factura_mensaje_error")
    def _compute_factura_mensaje_html(self):
        for rec in self:
            estado = rec.factura_estado_procesamiento
            mensaje = rec.factura_mensaje_error or ""
            icon_err = '<i class="fa fa-exclamation-circle"></i> '
            icon_warn = '<i class="fa fa-exclamation-triangle"></i> '
            icon_ok = '<i class="fa fa-check-circle"></i> '
            if estado == "error":
                rec.factura_mensaje_html = '<div class="alert alert-danger">' + (icon_err + mensaje if mensaje else "Error") + '</div>'
            elif estado == "advertencia":
                rec.factura_mensaje_html = '<div class="alert alert-warning">' + (icon_warn + mensaje if mensaje else "Advertencias") + '</div>'
            elif estado == "en_cola":
                rec.factura_mensaje_html = '<div class="alert alert-info"><i class="fa fa-clock-o"></i> En cola para procesamiento</div>'
            elif estado == "completado":
                rec.factura_mensaje_html = '<div class="alert alert-success">' + (icon_ok + mensaje if mensaje else "Completado") + '</div>'
            else:
                rec.factura_mensaje_html = False

    def _adjuntar_factura_en_expediente_documentos(self, datas, filename):
        """Crea o actualiza un adjunto en el expediente para que la factura aparezca en la sección Documentos."""
        self.ensure_one()
        if not self.expediente_id or not datas:
            return
        name = filename or self.name or _("Factura")
        existing = self.env["ir.attachment"].search([
            ("res_model", "=", "aduana.expediente"),
            ("res_id", "=", self.expediente_id.id),
            ("name", "=", name),
        ], limit=1)
        if existing:
            existing.write({"datas": datas})
        else:
            self.env["ir.attachment"].create({
                "name": name,
                "res_model": "aduana.expediente",
                "res_id": self.expediente_id.id,
                "type": "binary",
                "mimetype": "application/pdf",
                "datas": datas,
            })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "Factura":
                vals["name"] = vals.get("factura_pdf_filename") or "Factura"
            if vals.get("factura_pdf") and not vals.get("factura_estado_procesamiento"):
                vals["factura_estado_procesamiento"] = "pendiente"
            elif not vals.get("factura_pdf") and not vals.get("factura_estado_procesamiento"):
                vals["factura_estado_procesamiento"] = "sin_factura"
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if vals.get("factura_pdf") and rec.expediente_id:
                rec._adjuntar_factura_en_expediente_documentos(
                    vals["factura_pdf"],
                    vals.get("factura_pdf_filename") or rec.name,
                )
        expedientes = records.mapped("expediente_id")
        if expedientes:
            expedientes._recompute_factura_estado_from_facturas()
        return records

    def action_view_lineas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Líneas de %s", self.name),
            "res_model": "aduana.expediente.line",
            "view_mode": "tree,form",
            "domain": [("expediente_id", "=", self.expediente_id.id), ("factura_id", "=", self.id)],
            "context": {"default_expediente_id": self.expediente_id.id, "default_factura_id": self.id},
        }

    def action_process_invoice_pdf(self):
        """Encola el procesamiento de la factura o ejecuta en línea si force_sync."""
        force_sync = self.env.context.get("force_sync") or (self.env.context.get("process_async") is False)
        if force_sync:
            return self._process_invoice_pdf_sync()
        for rec in self:
            if not rec.factura_pdf:
                raise UserError(_("No hay factura PDF adjunta para procesar"))
            rec.write({
                "factura_estado_procesamiento": "en_cola",
                "factura_mensaje_error": _("Factura en cola para procesamiento en segundo plano"),
                "factura_en_cola_at": fields.Datetime.now(),
                "factura_procesada": False,
            })
            rec.with_delay(
                description=_("Procesar factura PDF %s", rec.name),
                max_retries=3,
                identity_key=lambda job, rec_id=rec.id: f"process_pdf_factura_{rec_id}",
            ).process_pdf_job()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Procesamiento en background"),
                "message": _("La factura se ha encolado. La vista se actualizará al terminar."),
                "type": "info",
                "sticky": False,
            },
        }

    @job
    def process_pdf_job(self):
        for rec in self:
            try:
                rec._process_invoice_pdf_sync()
            except Exception as e:
                msg = _("Error procesando factura en background: %s") % str(e)
                rec.write({
                    "factura_estado_procesamiento": "error",
                    "factura_mensaje_error": msg,
                })
                _logger.exception("Error en job de factura %s: %s", rec.id, e)
                raise

    def _process_invoice_pdf_sync(self):
        """Procesa el PDF de esta factura y rellena el expediente (líneas en expediente con factura_id=self)."""
        self.ensure_one()
        if not self.factura_pdf:
            self.write({
                "factura_estado_procesamiento": "error",
                "factura_mensaje_error": _("No hay factura PDF adjunta para procesar"),
            })
            raise UserError(_("No hay factura PDF adjunta para procesar"))
        return self.expediente_id._process_factura_pdf_sync(self)

    def write(self, vals):
        expedientes_before = self.mapped("expediente_id")
        result = super().write(vals)
        if "factura_pdf" in vals or "factura_pdf_filename" in vals:
            for rec in self:
                if rec.factura_pdf and rec.expediente_id:
                    rec._adjuntar_factura_en_expediente_documentos(
                        rec.factura_pdf,
                        rec.factura_pdf_filename or rec.name,
                    )
        if "factura_estado_procesamiento" in vals or "expediente_id" in vals:
            expedientes = expedientes_before
            if vals.get("expediente_id"):
                expedientes = expedientes | self.env["aduana.expediente"].browse(vals["expediente_id"])
            if expedientes:
                expedientes._recompute_factura_estado_from_facturas()
        return result

    def unlink(self):
        expedientes = self.mapped("expediente_id")
        result = super().unlink()
        if expedientes:
            expedientes._recompute_factura_estado_from_facturas()
        return result
