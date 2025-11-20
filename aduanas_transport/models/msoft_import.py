# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class MsoftImportWizard(models.TransientModel):
    _name = "aduanas.msoft.import.wizard"
    _description = "Importar Expedientes desde MSoft"

    import_mode = fields.Selection([
        ("full", "Importación Completa"),
        ("incremental", "Solo Cambios (Incremental)"),
        ("new_only", "Solo Nuevos"),
    ], string="Modo de Importación", default="incremental", required=True)
    
    fecha_desde = fields.Datetime(string="Fecha Desde", help="Solo importar expedientes modificados desde esta fecha")
    fecha_hasta = fields.Datetime(string="Fecha Hasta", help="Solo importar expedientes hasta esta fecha")
    
    crear_partners = fields.Boolean(string="Crear Partners Automáticamente", default=True)
    actualizar_partners = fields.Boolean(string="Actualizar Partners Existentes", default=True)
    crear_camiones = fields.Boolean(string="Crear Camiones Automáticamente", default=True)
    solo_confirmados = fields.Boolean(string="Solo Expedientes Confirmados", default=False)
    excluir_anulados = fields.Boolean(string="Excluir Anulados", default=True)
    
    resultado_importacion = fields.Text(string="Resultado", readonly=True)
    
    @api.model
    def _get_msoft_connection(self):
        """Obtiene conexión a MSoft desde configuración"""
        icp = self.env["ir.config_parameter"].sudo()
        dsn = icp.get_param("aduanas_transport.msoft.dsn")
        db = icp.get_param("aduanas_transport.msoft.db")
        user = icp.get_param("aduanas_transport.msoft.user")
        password = icp.get_param("aduanas_transport.msoft.pass")
        
        if not all([dsn, db, user, password]):
            raise UserError(_("Configuración MSoft incompleta. Verifique en Configuración > Aduanas AEAT"))
        
        # Retornar parámetros de conexión
        # En producción, usar pyodbc o similar para SQL Server
        return {
            "dsn": dsn,
            "database": db,
            "user": user,
            "password": password,
        }
    
    @api.model
    def _get_or_create_partner(self, codigo, nombre, nif, datos_completos):
        """Busca o crea un partner"""
        Partner = self.env["res.partner"]
        
        # Buscar por código (campo ref)
        partner = Partner.search([("ref", "=", str(codigo))], limit=1)
        if partner:
            if self.actualizar_partners:
                partner.write({
                    "name": nombre,
                    "vat": nif or partner.vat,
                    "street": datos_completos.get("street", partner.street),
                    "phone": datos_completos.get("phone", partner.phone),
                    "zip": datos_completos.get("zip", partner.zip),
                    "city": datos_completos.get("city", partner.city),
                    "country_id": datos_completos.get("country_id", partner.country_id.id),
                })
            return partner
        
        # Buscar por NIF
        if nif:
            nif_clean = nif.replace(" ", "").replace("-", "")
            partner = Partner.search([("vat", "ilike", nif_clean)], limit=1)
            if partner:
                # Actualizar ref si no tiene
                if not partner.ref:
                    partner.ref = str(codigo)
                if self.actualizar_partners:
                    partner.write({
                        "name": nombre,
                        "street": datos_completos.get("street", partner.street),
                        "phone": datos_completos.get("phone", partner.phone),
                        "zip": datos_completos.get("zip", partner.zip),
                        "city": datos_completos.get("city", partner.city),
                        "country_id": datos_completos.get("country_id", partner.country_id.id),
                    })
                return partner
        
        # Crear nuevo partner
        if not self.crear_partners:
            raise UserError(_("Partner no encontrado y creación deshabilitada: %s") % nombre)
        
        country_code = datos_completos.get("country_code", "ES")
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        
        partner = Partner.create({
            "name": nombre,
            "ref": str(codigo),
            "vat": nif,
            "street": datos_completos.get("street", ""),
            "phone": datos_completos.get("phone", ""),
            "zip": datos_completos.get("zip", ""),
            "city": datos_completos.get("city", ""),
            "country_id": country.id if country else False,
            "is_company": True,
        })
        
        return partner
    
    @api.model
    def _get_or_create_camion(self, matricula, transportista_cod=None, conductor_nombre=None):
        """Busca o crea un camión por matrícula (opcional si existe modelo camión)"""
        if not matricula or not matricula.strip():
            return False
        
        # Verificar si existe el modelo de camión
        try:
            Camion = self.env["aduana.camion"]
            matricula_clean = matricula.strip().upper()
            
            # Buscar por matrícula
            camion = Camion.search([("matricula", "=", matricula_clean)], limit=1)
            if camion:
                return camion
            
            # Crear nuevo camión
            if not self.crear_camiones:
                _logger.warning("Camión no encontrado y creación deshabilitada: %s", matricula)
                return False
            
            camion = Camion.create({
                "matricula": matricula_clean,
                "transportista": transportista_cod or "",
                "conductor_nombre": conductor_nombre or "",
                "activo": True,
            })
            
            return camion
        except Exception:
            # Modelo de camión no existe, retornar False
            _logger.debug("Modelo aduana.camion no disponible, usando campos legacy")
            return False
    
    @api.model
    def _map_estado_msoft(self, exp_sit):
        """Mapea estado MSoft a estado Odoo"""
        estado_map = {
            0: "draft",
            1: "predeclared",
            2: "presented",
            3: "accepted",
            4: "released",
            5: "exited",
            6: "closed",
            7: "error",
        }
        return estado_map.get(exp_sit, "draft")
    
    @api.model
    def _map_incoterm(self, ico_cod, ico_des):
        """Mapea incoterm MSoft a código Odoo (Selection)"""
        incoterm_map = {
            1: "DAP",
            2: "EXW",
            3: "FOB",  # FOB no está en la lista, mapear a DAP o FCA
            4: "CIF",  # CIF no está en la lista, mapear a CIP
            5: "DDP",
            6: "FCA",
            7: "CPT",
            8: "CIP",
        }
        
        # Incoterms válidos en Odoo
        valid_incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"]
        
        if ico_cod and ico_cod in incoterm_map:
            mapped = incoterm_map[ico_cod]
            # Si el mapeo no es válido, usar DAP por defecto
            if mapped not in valid_incoterms:
                if mapped == "FOB":
                    mapped = "FCA"  # FOB es similar a FCA
                elif mapped == "CIF":
                    mapped = "CIP"  # CIF es similar a CIP
                else:
                    mapped = "DAP"
            return mapped
        
        if ico_des:
            # Intentar extraer código de la descripción
            ico_des_upper = ico_des.upper().strip()
            # Buscar códigos válidos en la descripción
            for valid_code in valid_incoterms:
                if valid_code in ico_des_upper:
                    return valid_code
            # Si contiene palabras clave, mapear
            if "EXW" in ico_des_upper or "EN FABRICA" in ico_des_upper:
                return "EXW"
            elif "FCA" in ico_des_upper or "FREE CARRIER" in ico_des_upper:
                return "FCA"
            elif "CPT" in ico_des_upper or "CARRIAGE PAID" in ico_des_upper:
                return "CPT"
            elif "CIP" in ico_des_upper or "CARRIAGE AND INSURANCE" in ico_des_upper:
                return "CIP"
            elif "DAP" in ico_des_upper or "DELIVERED AT PLACE" in ico_des_upper:
                return "DAP"
            elif "DPU" in ico_des_upper or "DELIVERED AT PLACE UNLOADED" in ico_des_upper:
                return "DPU"
            elif "DDP" in ico_des_upper or "DELIVERED DUTY PAID" in ico_des_upper:
                return "DDP"
        
        return "DAP"  # Por defecto
    
    @api.model
    def _map_moneda(self, val_div):
        """Mapea código divisa MSoft a código ISO"""
        moneda_map = {
            900: "EUR",
            840: "USD",
            978: "EUR",
        }
        return moneda_map.get(val_div, "EUR")
    
    @api.model
    def _format_oficina(self, ofc_cod):
        """Formatea código oficina a 4 dígitos"""
        if not ofc_cod:
            return "0801"
        ofc_str = str(int(ofc_cod))
        if len(ofc_str) == 1:
            return "000" + ofc_str + "1"
        elif len(ofc_str) == 2:
            return "00" + ofc_str + "1"
        elif len(ofc_str) == 3:
            return "0" + ofc_str
        elif len(ofc_str) == 4:
            return ofc_str
        return "0801"  # Por defecto
    
    @api.model
    def _map_pais(self, pais_cod):
        """Mapea código país MSoft a código ISO"""
        pais_map = {
            1: "ES",
            11: "ES",
            43: "AD",
        }
        return pais_map.get(pais_cod, "ES")
    
    @api.model
    def _map_direction(self, exp_exp_dua, exp_imp_dua, ori_nac, des_pai):
        """Determina dirección del expediente"""
        if exp_exp_dua == 1:
            return "export"
        if exp_imp_dua == 1:
            return "import"
        # Inferir por países
        if ori_nac == 1 and des_pai == 43:
            return "export"  # España → Andorra
        if ori_nac == 43 and des_pai == 1:
            return "import"  # Andorra → España
        return "export"  # Por defecto
    
    def action_import_expedientes(self):
        """Ejecuta la importación de expedientes"""
        self.ensure_one()
        
        resultados = {
            "importados": 0,
            "actualizados": 0,
            "errores": [],
            "omitidos": 0,
            "partners_creados": 0,
            "camiones_creados": 0,
        }
        
        try:
            # Obtener conexión (en producción, conectar a BD real)
            conn_params = self._get_msoft_connection()
            
            # NOTA: Aquí iría la conexión real a MSoft
            # Por ahora, retornamos un mensaje informativo
            self.resultado_importacion = _("""
IMPORTACIÓN DESDE MSOFT

Este es un esqueleto del sistema de importación. Para completarlo necesitas:

1. Instalar pyodbc o pymssql para conectar a SQL Server
2. Ejecutar el SQL de MAPEO_COMPLETO_MSOFT_ODOO.md
3. Procesar los resultados y crear/actualizar registros

Parámetros de conexión configurados:
- DSN: %s
- Database: %s
- User: %s

Para implementar:
- Leer expedientes desde MSoft usando el SQL proporcionado
- Para cada expediente:
  * Buscar/crear remitente
  * Buscar/crear consignatario
  * Buscar/crear camión
  * Crear/actualizar expediente
  * Crear líneas de mercancía

Ver MAPEO_COMPLETO_MSOFT_ODOO.md para el SQL completo.
            """) % (conn_params["dsn"], conn_params["database"], conn_params["user"])
            
            return {
                "type": "ir.actions.act_window",
                "name": _("Resultado Importación"),
                "res_model": "aduanas.msoft.import.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }
            
        except Exception as e:
            _logger.exception("Error en importación MSoft")
            raise UserError(_("Error al importar: %s") % str(e))

