# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import base64
import html
import xml.dom.minidom
import logging

_logger = logging.getLogger(__name__)

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'
    
    xml_content_text = fields.Text(
        string="Contenido XML",
        compute="_compute_xml_content_text",
        store=False,
        help="Contenido XML como texto plano para previsualización"
    )
    
    xml_preview_url = fields.Char(
        string="URL Previsualización XML",
        compute="_compute_xml_preview_url",
        store=False,
        help="URL para previsualizar el XML"
    )
    
    is_xml = fields.Boolean(
        string="Es XML",
        compute="_compute_is_xml",
        store=False
    )
    
    tipo_documento = fields.Char(
        string="Tipo",
        compute="_compute_tipo_documento",
        store=False
    )
    
    @api.depends('mimetype', 'name')
    def _compute_is_xml(self):
        """Determina si el archivo es XML"""
        for record in self:
            record.is_xml = (
                (record.mimetype and 'xml' in record.mimetype.lower()) or
                (record.name and record.name.lower().endswith('.xml'))
            )
    
    @api.depends('mimetype', 'name')
    def _compute_tipo_documento(self):
        """Calcula el tipo de documento simplificado (PDF o XML)"""
        for record in self:
            if record.mimetype:
                if 'pdf' in record.mimetype.lower():
                    record.tipo_documento = 'PDF'
                elif 'xml' in record.mimetype.lower():
                    record.tipo_documento = 'XML'
                else:
                    record.tipo_documento = ''
            elif record.name:
                if record.name.lower().endswith('.pdf'):
                    record.tipo_documento = 'PDF'
                elif record.name.lower().endswith('.xml'):
                    record.tipo_documento = 'XML'
                else:
                    record.tipo_documento = ''
            else:
                record.tipo_documento = ''
    
    @api.depends('mimetype', 'name')
    def _compute_xml_preview_url(self):
        """Genera la URL para previsualizar el XML"""
        for record in self:
            if record.is_xml and record.id:
                record.xml_preview_url = f'/web/content/{record.id}?download=0'
            else:
                record.xml_preview_url = False
    
    @api.depends('mimetype', 'name', 'xml_preview_url')
    def _compute_xml_content_text(self):
        """Obtiene el contenido XML como texto plano usando el método que funciona en el código"""
        for record in self:
            if not record.is_xml or not record.id:
                record.xml_content_text = False
                continue
            
            try:
                # Usar exactamente el mismo método que funciona en aduana_expediente.py
                # Buscar el attachment de nuevo para asegurar carga correcta
                xmls = self.env['ir.attachment'].sudo().search([
                    ('id', '=', record.id)
                ], limit=1)
                
                if not xmls:
                    record.xml_content_text = "No se encontró el archivo XML. Usa el botón 'Abrir XML' para verlo."
                    continue
                
                # Intentar leer desde datas
                xml_content = None
                
                # Si el archivo está en base64 (en datas)
                if xmls.datas:
                    try:
                        datas_str = str(xmls.datas).strip()
                        # Verificar que tenga suficiente contenido (más de unos pocos caracteres)
                        if len(datas_str) > 10:
                            xml_content = base64.b64decode(xmls.datas or b"").decode("utf-8")
                    except Exception as decode_error:
                        _logger.warning("No se pudo decodificar XML desde datas para attachment %s: %s", record.id, decode_error)
                
                # Si no se pudo leer desde datas, el archivo está en filesystem
                if not xml_content or not xml_content.strip():
                    # Mostrar mensaje informativo con la URL
                    url = f'/web/content/{record.id}?download=0'
                    record.xml_content_text = f"El archivo XML está almacenado en el sistema de archivos.\n\nPara ver el contenido, usa el botón 'Abrir XML en nueva pestaña' arriba.\n\nURL: {url}"
                    continue
                
                # Formatear el XML de forma bonita
                try:
                    dom = xml.dom.minidom.parseString(xml_content)
                    formatted_xml = dom.toprettyxml(indent="  ")
                    # Limpiar líneas vacías extra después de la declaración XML
                    lines = formatted_xml.split('\n')
                    cleaned_lines = []
                    for i, line in enumerate(lines):
                        # Saltar primera línea vacía después de <?xml
                        if i == 1 and not line.strip() and lines[0].strip().startswith('<?xml'):
                            continue
                        cleaned_lines.append(line)
                    formatted_xml = '\n'.join(cleaned_lines)
                    record.xml_content_text = formatted_xml
                except Exception:
                    # Si no se puede parsear, mostrar el contenido original
                    record.xml_content_text = xml_content
                    
            except Exception as e:
                _logger.exception("Error obteniendo contenido XML para attachment %s: %s", record.id, e)
                record.xml_content_text = ""
    
    def action_preview_xml(self):
        """Abre una vista previa del XML en una nueva pestaña"""
        self.ensure_one()
        if not self.is_xml:
            raise ValueError(_("El archivo no es un XML"))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.id}?download=0',
            'target': 'new',
        }

