# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class AduanaIncidencia(models.Model):
    _name = "aduana.incidencia"
    _description = "Incidencia Aduanera de AEAT"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "fecha_incidencia desc, create_date desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Nueva"))
    expediente_id = fields.Many2one("aduana.expediente", string="Expediente", required=True, ondelete="cascade", tracking=True, index=True)
    mrn = fields.Char(string="MRN", related="expediente_id.mrn", store=True, readonly=True)
    
    # Información de la incidencia
    tipo_incidencia = fields.Selection([
        ("error", "Error"),
        ("advertencia", "Advertencia"),
        ("solicitud_info", "Solicitud de Información"),
        ("rechazo", "Rechazo"),
        ("suspension", "Suspensión"),
        ("requerimiento", "Requerimiento"),
        ("notificacion", "Notificación"),
        ("otra", "Otra"),
    ], string="Tipo de Incidencia", required=True, default="error", tracking=True)
    
    codigo_incidencia = fields.Char(string="Código Incidencia", help="Código de error o incidencia de AEAT")
    titulo = fields.Char(string="Título", required=True)
    descripcion = fields.Text(string="Descripción", required=True)
    mensaje_aeat = fields.Text(string="Mensaje Original AEAT", readonly=True, help="Mensaje completo recibido de AEAT")
    
    # Fechas
    fecha_incidencia = fields.Datetime(string="Fecha Incidencia", default=fields.Datetime.now, required=True, tracking=True)
    fecha_deteccion = fields.Datetime(string="Fecha Detección", default=fields.Datetime.now, readonly=True)
    fecha_resolucion = fields.Datetime(string="Fecha Resolución", tracking=True)
    
    # Estado y seguimiento
    state = fields.Selection([
        ("pendiente", "Pendiente"),
        ("en_revision", "En Revisión"),
        ("resuelta", "Resuelta"),
        ("cerrada", "Cerrada"),
        ("rechazada", "Rechazada"),
    ], string="Estado", default="pendiente", tracking=True, required=True)
    
    prioridad = fields.Selection([
        ("baja", "Baja"),
        ("media", "Media"),
        ("alta", "Alta"),
        ("critica", "Crítica"),
    ], string="Prioridad", default="media", tracking=True)
    
    # Origen
    origen = fields.Selection([
        ("bandeja", "Bandeja AEAT"),
        ("cusdec_ex1", "CUSDEC EX1 (DUA Exportación)"),
        ("cc511c", "CC511C (Exportación)"),
        ("imp_decl", "Declaración Importación"),
        ("manual", "Manual"),
    ], string="Origen", default="bandeja", required=True)
    
    # Resolución
    resolucion = fields.Text(string="Resolución", help="Descripción de cómo se resolvió la incidencia")
    usuario_resolucion = fields.Many2one("res.users", string="Resuelto por", readonly=True)
    accion_tomada = fields.Text(string="Acción Tomada", help="Acciones realizadas para resolver la incidencia")
    
    # Archivos relacionados
    attachment_ids = fields.Many2many("ir.attachment", string="Archivos Adjuntos", help="Documentos relacionados con la incidencia")
    
    # Campos computados
    dias_pendiente = fields.Integer(string="Días Pendiente", compute="_compute_dias_pendiente", store=True)
    expediente_name = fields.Char(string="Expediente", related="expediente_id.name", store=True, readonly=True)
    
    @api.depends("fecha_incidencia", "fecha_resolucion", "state")
    def _compute_dias_pendiente(self):
        """Calcula días que lleva pendiente la incidencia"""
        for rec in self:
            if rec.state in ("resuelta", "cerrada", "rechazada") and rec.fecha_resolucion:
                # Ya resuelta
                rec.dias_pendiente = 0
            elif rec.fecha_incidencia:
                delta = fields.Datetime.now() - rec.fecha_incidencia
                rec.dias_pendiente = delta.days
            else:
                rec.dias_pendiente = 0
    
    @api.model
    def create(self, vals):
        """Generar nombre automático"""
        if vals.get("name", _("Nueva")) == _("Nueva"):
            vals["name"] = self.env["ir.sequence"].next_by_code("aduana.incidencia") or _("Nueva")
        return super().create(vals)
    
    def action_marcar_resuelta(self):
        """Marca la incidencia como resuelta"""
        for rec in self:
            rec.state = "resuelta"
            rec.fecha_resolucion = fields.Datetime.now()
            rec.usuario_resolucion = self.env.user
            rec.message_post(body=_("Incidencia marcada como resuelta por %s") % self.env.user.name)
    
    def action_marcar_cerrada(self):
        """Marca la incidencia como cerrada"""
        for rec in self:
            rec.state = "cerrada"
            if not rec.fecha_resolucion:
                rec.fecha_resolucion = fields.Datetime.now()
            rec.message_post(body=_("Incidencia cerrada por %s") % self.env.user.name)
    
    def action_ver_expediente(self):
        """Abre el expediente relacionado"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Expediente %s", self.expediente_id.name),
            "res_model": "aduana.expediente",
            "res_id": self.expediente_id.id,
            "view_mode": "form",
            "target": "current",
        }

