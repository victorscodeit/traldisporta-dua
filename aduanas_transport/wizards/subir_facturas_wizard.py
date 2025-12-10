# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SubirFacturasWizard(models.TransientModel):
    _name = "aduanas.subir.facturas.wizard"
    _description = "Wizard para subir múltiples facturas PDF y crear expediciones"

    factura_ids = fields.One2many(
        "aduanas.subir.facturas.wizard.line",
        "wizard_id",
        string="Facturas PDF",
        required=True
    )

    def action_crear_expediciones(self):
        """Crea expediciones desde los PDFs subidos"""
        self.ensure_one()
        
        if not self.factura_ids:
            raise UserError(_("Debes subir al menos un archivo PDF"))
        
        expedientes_creados = []
        errores = []
        
        for linea in self.factura_ids:
            if not linea.factura_pdf:
                errores.append(_("El archivo %s está vacío") % (linea.factura_pdf_filename or "sin nombre"))
                continue
            
            try:
                # Crear expedición (la secuencia se generará automáticamente en el método create)
                expediente = self.env["aduana.expediente"].create({
                    "direction": "export",  # Por defecto exportación
                    "factura_pdf": linea.factura_pdf,
                    "factura_pdf_filename": linea.factura_pdf_filename or linea.name,
                    "factura_estado_procesamiento": "pendiente",  # Estado inicial
                })
                
                expedientes_creados.append(expediente.id)
                _logger.info("Expedición creada: %s desde archivo %s", expediente.name, linea.factura_pdf_filename)
                
            except Exception as e:
                _logger.exception("Error creando expedición desde %s: %s", linea.factura_pdf_filename, e)
                errores.append(_("Error con %s: %s") % (linea.factura_pdf_filename or "archivo", str(e)))
        
        # Mostrar resultado
        if errores:
            mensaje = _("Se crearon %d expedición(es) correctamente.\n\nErrores:\n%s") % (
                len(expedientes_creados), "\n".join(errores)
            )
            tipo = "warning"
        else:
            mensaje = _("Se crearon %d expedición(es) correctamente.") % len(expedientes_creados)
            tipo = "success"
        
        # Abrir vista de expedientes creados
        if expedientes_creados:
            return {
                "type": "ir.actions.act_window",
                "name": _("Expediciones Creadas"),
                "res_model": "aduana.expediente",
                "domain": [("id", "in", expedientes_creados)],
                "view_mode": "tree,form",
                "target": "current",
                "context": {
                    "default_direction": "export",
                }
            }
        else:
            raise UserError(mensaje)


class SubirFacturasWizardLine(models.TransientModel):
    _name = "aduanas.subir.facturas.wizard.line"
    _description = "Línea del wizard de subir facturas"

    wizard_id = fields.Many2one("aduanas.subir.facturas.wizard", required=True, ondelete="cascade")
    name = fields.Char(string="Nombre", required=True)
    factura_pdf = fields.Binary(string="Factura PDF", required=True)
    factura_pdf_filename = fields.Char(string="Nombre Archivo")

