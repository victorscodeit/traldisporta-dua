# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)


class FacturaCarga(models.Model):
    """Modelo para gestionar la carga y procesamiento de facturas individuales"""
    _name = "aduana.factura.carga"
    _description = "Carga de Factura Individual"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Nombre Archivo", required=True, copy=False)
    factura_pdf = fields.Binary(string="Factura PDF", required=True)
    factura_pdf_filename = fields.Char(string="Nombre Archivo PDF")
    
    # Estado del procesamiento
    state = fields.Selection([
        ("pendiente", "Pendiente"),
        ("procesando", "Procesando"),
        ("completado", "Completado"),
        ("error", "Error"),
    ], string="Estado", default="pendiente", tracking=True, required=True)
    
    # Mensajes
    mensaje = fields.Text(string="Mensaje", help="Mensaje de error o información sobre el procesamiento")
    
    # Relación con expediente creado
    expediente_id = fields.Many2one("aduana.expediente", string="Expediente Creado", readonly=True)
    
    # Relación con carga masiva (si aplica)
    carga_masiva_id = fields.Many2one("aduana.carga.masiva", string="Carga Masiva", ondelete="cascade")
    
    # Información adicional
    datos_extraidos = fields.Text(string="Datos Extraídos", readonly=True)
    
    # Fechas
    fecha_procesamiento = fields.Datetime(string="Fecha Procesamiento", readonly=True)
    
    def action_procesar_factura(self):
        """Procesa la factura y crea una expedición"""
        self.ensure_one()
        if self.state != "pendiente":
            raise UserError(_("Solo se pueden procesar facturas en estado 'Pendiente'"))
        
        if not self.factura_pdf:
            self.state = "error"
            self.mensaje = _("No hay factura PDF adjunta")
            return
        
        try:
            self.state = "procesando"
            self.mensaje = _("Procesando factura...")
            
            # Crear nueva expedición
            expediente = self.env["aduana.expediente"].create({
                "name": self.env["ir.sequence"].next_by_code("aduana.expediente") or _("Nuevo"),
                "direction": "export",  # Por defecto exportación, se puede cambiar después
                "factura_pdf": self.factura_pdf,
                "factura_pdf_filename": self.factura_pdf_filename or self.name,
            })
            
            # Procesar la factura en la expedición creada
            expediente.action_process_invoice_pdf()
            
            # Actualizar estado
            if expediente.factura_estado_procesamiento == "completado":
                self.state = "completado"
                self.mensaje = _("Factura procesada correctamente. Expedición creada: %s") % expediente.name
            elif expediente.factura_estado_procesamiento == "advertencia":
                self.state = "completado"  # Se considera completado aunque haya advertencias
                self.mensaje = expediente.factura_mensaje_error or _("Factura procesada con advertencias. Expedición creada: %s") % expediente.name
            elif expediente.factura_estado_procesamiento == "error":
                self.state = "error"
                self.mensaje = expediente.factura_mensaje_error or _("Error al procesar la factura")
            
            self.expediente_id = expediente.id
            self.fecha_procesamiento = fields.Datetime.now()
            self.datos_extraidos = expediente.factura_datos_extraidos
            
        except Exception as e:
            _logger.exception("Error procesando factura %s: %s", self.name, e)
            self.state = "error"
            self.mensaje = _("Error al procesar: %s") % str(e)
    
    def action_ver_expediente(self):
        """Abre la expedición creada"""
        self.ensure_one()
        if not self.expediente_id:
            raise UserError(_("No se ha creado ninguna expedición para esta factura"))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Expediente %s", self.expediente_id.name),
            "res_model": "aduana.expediente",
            "res_id": self.expediente_id.id,
            "view_mode": "form",
            "target": "current",
        }
    
    @api.model
    def cron_procesar_facturas_pendientes(self, limit=10):
        """Cron para procesar facturas pendientes en background"""
        facturas_pendientes = self.env["aduana.factura.carga"].search([
            ("state", "=", "pendiente")
        ], limit=limit, order="create_date asc")
        
        for factura in facturas_pendientes:
            try:
                factura.action_procesar_factura()
            except Exception as e:
                _logger.exception("Error en cron procesando factura %s: %s", factura.name, e)
        
        return True


class CargaMasivaFacturas(models.Model):
    """Modelo para gestionar la carga masiva de facturas"""
    _name = "aduana.carga.masiva"
    _description = "Carga Masiva de Facturas"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Nueva Carga"))
    
    # Facturas cargadas
    factura_ids = fields.One2many("aduana.factura.carga", "carga_masiva_id", string="Facturas")
    
    # Estado general
    state = fields.Selection([
        ("draft", "Borrador"),
        ("procesando", "Procesando"),
        ("completado", "Completado"),
        ("parcial", "Parcialmente Completado"),
        ("error", "Con Errores"),
    ], string="Estado General", default="draft", tracking=True, required=True)
    
    # Contadores
    total_facturas = fields.Integer(string="Total Facturas", compute="_compute_estadisticas", store=True)
    pendientes = fields.Integer(string="Pendientes", compute="_compute_estadisticas", store=True)
    procesando = fields.Integer(string="Procesando", compute="_compute_estadisticas", store=True)
    completadas = fields.Integer(string="Completadas", compute="_compute_estadisticas", store=True)
    con_error = fields.Integer(string="Con Error", compute="_compute_estadisticas", store=True)
    
    # Fechas
    fecha_inicio = fields.Datetime(string="Fecha Inicio", readonly=True)
    fecha_fin = fields.Datetime(string="Fecha Fin", readonly=True)
    
    @api.depends("factura_ids", "factura_ids.state")
    def _compute_estadisticas(self):
        """Calcula estadísticas de la carga masiva"""
        for rec in self:
            rec.total_facturas = len(rec.factura_ids)
            rec.pendientes = len(rec.factura_ids.filtered(lambda f: f.state == "pendiente"))
            rec.procesando = len(rec.factura_ids.filtered(lambda f: f.state == "procesando"))
            rec.completadas = len(rec.factura_ids.filtered(lambda f: f.state == "completado"))
            rec.con_error = len(rec.factura_ids.filtered(lambda f: f.state == "error"))
            
            # Actualizar estado general
            if rec.total_facturas == 0:
                rec.state = "draft"
            elif rec.pendientes > 0 or rec.procesando > 0:
                if rec.completadas > 0 or rec.con_error > 0:
                    rec.state = "parcial"
                else:
                    rec.state = "procesando"
            elif rec.con_error == rec.total_facturas:
                rec.state = "error"
            elif rec.con_error > 0:
                rec.state = "parcial"
            else:
                rec.state = "completado"
    
    @api.model
    def create(self, vals):
        """Generar nombre automático"""
        if vals.get("name", _("Nueva Carga")) == _("Nueva Carga"):
            vals["name"] = self.env["ir.sequence"].next_by_code("aduana.carga.masiva") or _("Nueva Carga")
        return super().create(vals)
    
    def action_iniciar_procesamiento(self):
        """Inicia el procesamiento de todas las facturas pendientes"""
        self.ensure_one()
        facturas_pendientes = self.factura_ids.filtered(lambda f: f.state == "pendiente")
        
        if not facturas_pendientes:
            raise UserError(_("No hay facturas pendientes para procesar"))
        
        self.state = "procesando"
        self.fecha_inicio = fields.Datetime.now()
        
        # Procesar facturas (se ejecuta inmediatamente, pero cada una puede tardar)
        for factura in facturas_pendientes:
            try:
                factura.action_procesar_factura()
            except Exception as e:
                _logger.exception("Error procesando factura %s: %s", factura.name, e)
                factura.state = "error"
                factura.mensaje = _("Error: %s") % str(e)
        
        # Actualizar estadísticas y estado final
        self._compute_estadisticas()
        if self.pendientes == 0 and self.procesando == 0:
            self.fecha_fin = fields.Datetime.now()
    
    def action_subir_facturas_multiple(self, files_data):
        """Crea múltiples facturas desde archivos PDF subidos
        
        :param files_data: Lista de diccionarios con formato:
            [{'name': 'nombre.pdf', 'content': 'base64_content'}, ...]
        :return: Diccionario con resultado
        """
        self.ensure_one()
        import os
        
        if not files_data:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Error"),
                    "message": _("No se proporcionaron archivos"),
                    "type": "danger",
                    "sticky": False,
                }
            }
        
        facturas_creadas = []
        errores = []
        
        for file_data in files_data:
            try:
                filename = file_data.get('name', 'factura.pdf')
                content = file_data.get('content', '')
                
                if not content:
                    errores.append(_("Archivo %s está vacío") % filename)
                    continue
                
                # Extraer solo el nombre del archivo sin ruta
                basename = os.path.basename(filename)
                
                # Crear registro de factura
                factura = self.env["aduana.factura.carga"].create({
                    "name": basename,
                    "factura_pdf": content,
                    "factura_pdf_filename": basename,
                    "carga_masiva_id": self.id,
                })
                
                facturas_creadas.append(factura.id)
                
            except Exception as e:
                _logger.exception("Error creando factura desde %s: %s", filename, e)
                errores.append(_("Error con %s: %s") % (filename, str(e)))
        
        mensaje = _("Se crearon %d factura(s) correctamente.") % len(facturas_creadas)
        if errores:
            mensaje += "\n\nErrores:\n" + "\n".join(errores)
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Carga Múltiple"),
                "message": mensaje,
                "type": "success" if not errores else "warning",
                "sticky": False,
            }
        }
    
    def action_ver_expedientes(self):
        """Abre la vista de expedientes creados desde esta carga"""
        self.ensure_one()
        expedientes = self.factura_ids.mapped("expediente_id").filtered(lambda e: e)
        
        if not expedientes:
            raise UserError(_("No se han creado expedientes aún"))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Expedientes de %s", self.name),
            "res_model": "aduana.expediente",
            "domain": [("id", "in", expedientes.ids)],
            "view_mode": "tree,form",
            "target": "current",
        }
    
    def action_subir_facturas_multiple_wizard(self):
        """Abre una acción de cliente para subir múltiples archivos"""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "multi_file_upload",
            "params": {
                "carga_masiva_id": self.id,
                "model": "aduana.carga.masiva",
                "method": "action_subir_facturas_multiple",
            }
        }
    
    def action_upload_multiple_facturas(self, files_data):
        """Crea múltiples facturas desde archivos subidos
        
        :param files_data: Lista de diccionarios con formato:
            [{'name': 'nombre.pdf', 'content': 'base64_content'}, ...]
        :return: Diccionario con resultado
        """
        self.ensure_one()
        
        if not files_data:
            raise UserError(_("No se proporcionaron archivos"))
        
        facturas_creadas = []
        errores = []
        
        for file_data in files_data:
            try:
                filename = file_data.get('name', 'factura.pdf')
                content = file_data.get('content', '')
                
                if not content:
                    errores.append(_("Archivo %s está vacío") % filename)
                    continue
                
                # Crear registro de factura
                factura = self.env["aduana.factura.carga"].create({
                    "name": filename,
                    "factura_pdf": content,
                    "factura_pdf_filename": filename,
                    "carga_masiva_id": self.id,
                })
                
                facturas_creadas.append(factura.id)
                
            except Exception as e:
                _logger.exception("Error creando factura desde %s: %s", filename, e)
                errores.append(_("Error con %s: %s") % (filename, str(e)))
        
        mensaje = _("Se crearon %d factura(s) correctamente.") % len(facturas_creadas)
        if errores:
            mensaje += "\n\nErrores:\n" + "\n".join(errores)
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Carga Múltiple"),
                "message": mensaje,
                "type": "success" if not errores else "warning",
                "sticky": False,
            }
        }

