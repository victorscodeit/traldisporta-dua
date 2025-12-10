# -*- coding: utf-8 -*-
"""
Script para limpiar registros residuales del wizard eliminado.
Ejecutar desde la consola de Odoo si es necesario.

Uso:
    odoo-bin shell -d tu_base_de_datos
    >>> exec(open('addons/aduanas_transport/scripts/cleanup_wizard_residuals.py').read())
"""

import logging
_logger = logging.getLogger(__name__)

def cleanup_wizard_residuals(env):
    """Elimina registros residuales del wizard aduana.factura.carga.multi.wizard"""
    
    model_name = "aduana.factura.carga.multi.wizard"
    
    # Eliminar vistas
    views = env['ir.ui.view'].search([
        ('model', '=', model_name)
    ])
    if views:
        _logger.info("Eliminando %d vistas residuales...", len(views))
        views.unlink()
    
    # Eliminar acciones de ventana
    actions = env['ir.actions.act_window'].search([
        ('res_model', '=', model_name)
    ])
    if actions:
        _logger.info("Eliminando %d acciones residuales...", len(actions))
        actions.unlink()
    
    # Eliminar registros del modelo (si existen)
    try:
        model = env['ir.model'].search([
            ('model', '=', model_name)
        ])
        if model:
            _logger.info("Eliminando modelo residual...")
            model.unlink()
    except Exception as e:
        _logger.warning("No se pudo eliminar el modelo (puede que ya no exista): %s", e)
    
    # Eliminar permisos de acceso (si existen)
    access_rules = env['ir.model.access'].search([
        ('name', 'like', 'factura_carga_multi_wizard')
    ])
    if access_rules:
        _logger.info("Eliminando %d reglas de acceso residuales...", len(access_rules))
        access_rules.unlink()
    
    env.cr.commit()
    _logger.info("Limpieza completada")

# Si se ejecuta directamente desde la consola
if __name__ == "__main__":
    # Esto solo funciona si se ejecuta desde odoo-bin shell
    if 'env' in globals():
        cleanup_wizard_residuals(env)
    else:
        print("Este script debe ejecutarse desde la consola de Odoo:")
        print("odoo-bin shell -d tu_base_de_datos")
        print(">>> exec(open('addons/aduanas_transport/scripts/cleanup_wizard_residuals.py').read())")







