# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SubirFacturasWizard(models.TransientModel):
    _name = "aduanas.subir.facturas.wizard"
    _description = "Wizard para subir múltiples facturas PDF y crear expediciones"

    expediente_id = fields.Many2one(
        "aduana.expediente",
        string="Expediente",
        help="Si se indica, las facturas se añaden a este expediente en lugar de crear expedientes nuevos.",
    )
    factura_ids = fields.One2many(
        "aduanas.subir.facturas.wizard.line",
        "wizard_id",
        string="Facturas PDF",
        required=True
    )

    def action_agregar_archivos(self, files_data):
        """
        Método para agregar archivos PDF al wizard desde JavaScript
        files_data: lista de diccionarios con {name, factura_pdf, factura_pdf_filename}
        """
        self.ensure_one()
        
        if not files_data:
            return False
        
        # Crear las líneas del wizard
        line_vals = []
        for file_data in files_data:
            line_vals.append({
                'wizard_id': self.id,
                'name': file_data.get('name', file_data.get('factura_pdf_filename', 'Sin nombre')),
                'factura_pdf': file_data.get('factura_pdf'),
                'factura_pdf_filename': file_data.get('factura_pdf_filename', file_data.get('name', 'Sin nombre')),
            })
        
        # Crear las líneas
        self.env['aduanas.subir.facturas.wizard.line'].create(line_vals)
        
        return True

    def action_crear_expediciones(self):
        """Crea expediciones desde los PDFs subidos, o añade facturas al expediente indicado."""
        self.ensure_one()
        
        if not self.factura_ids:
            raise UserError(_("Debes subir al menos un archivo PDF"))
        
        expedientes_creados = []
        facturas_creadas = 0
        errores = []
        añadir_a_expediente = bool(self.expediente_id)
        
        for linea in self.factura_ids:
            if not linea.factura_pdf:
                errores.append(_("El archivo %s está vacío") % (linea.factura_pdf_filename or "sin nombre"))
                continue
            
            try:
                if añadir_a_expediente:
                    self.env["aduana.expediente.factura"].create({
                        "expediente_id": self.expediente_id.id,
                        "name": linea.factura_pdf_filename or linea.name,
                        "factura_pdf": linea.factura_pdf,
                        "factura_pdf_filename": linea.factura_pdf_filename or linea.name,
                        "factura_estado_procesamiento": "pendiente",
                    })
                    facturas_creadas += 1
                    _logger.info(
                        "Factura añadida al expediente %s: %s",
                        self.expediente_id.name,
                        linea.factura_pdf_filename,
                    )
                else:
                    expediente = self.env["aduana.expediente"].create({
                        "direction": "export",
                        "factura_pdf": linea.factura_pdf,
                        "factura_pdf_filename": linea.factura_pdf_filename or linea.name,
                        "factura_estado_procesamiento": "pendiente",
                    })
                    expedientes_creados.append(expediente.id)
                    _logger.info("Expedición creada: %s desde %s", expediente.name, linea.factura_pdf_filename)
            except Exception as e:
                _logger.exception("Error creando desde %s: %s", linea.factura_pdf_filename, e)
                errores.append(_("Error con %s: %s") % (linea.factura_pdf_filename or "archivo", str(e)))
        
        if errores and not expedientes_creados and not facturas_creadas:
            raise UserError(_("Errores al subir:\n%s") % "\n".join(errores))
        
        if añadir_a_expediente and facturas_creadas:
            return {
                "type": "ir.actions.act_window",
                "name": _("Expediente"),
                "res_model": "aduana.expediente",
                "res_id": self.expediente_id.id,
                "view_mode": "form",
                "target": "current",
                "context": {"form_view_initial_mode": "edit"},
            }
        if expedientes_creados:
            return {
                "type": "ir.actions.act_window",
                "name": _("Expediciones Creadas"),
                "res_model": "aduana.expediente",
                "domain": [("id", "in", expedientes_creados)],
                "view_mode": "tree,form",
                "target": "current",
                "context": {"default_direction": "export"},
            }
        
        raise UserError(_("No se pudo crear ninguna expedición."))


class SubirFacturasWizardLine(models.TransientModel):
    _name = "aduanas.subir.facturas.wizard.line"
    _description = "Línea del wizard de subir facturas"

    wizard_id = fields.Many2one("aduanas.subir.facturas.wizard", required=True, ondelete="cascade")
    name = fields.Char(string="Nombre", required=True)
    factura_pdf = fields.Binary(string="Factura PDF", required=True)
    factura_pdf_filename = fields.Char(string="Nombre Archivo")

