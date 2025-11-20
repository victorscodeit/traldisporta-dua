# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import ValidationError
import re

class AduanaValidator(models.AbstractModel):
    _name = "aduanas.validator"
    _description = "Validador de datos aduaneros"

    def validate_nif_cif(self, vat):
        """Valida formato de NIF/CIF español"""
        if not vat:
            return False
        vat = vat.replace(' ', '').replace('-', '').upper()
        # Patrón básico: 8 dígitos + letra o letra + 7 dígitos + letra/dígito
        pattern = r'^[A-Z]?\d{7,8}[A-Z0-9]$'
        return bool(re.match(pattern, vat))

    def validate_oficina_aduana(self, oficina):
        """Valida formato de oficina aduanera (4 dígitos)"""
        if not oficina:
            return False
        oficina = oficina.replace(' ', '')
        return len(oficina) == 4 and oficina.isdigit()

    def validate_partida_arancelaria(self, partida):
        """Valida formato de partida arancelaria (10 dígitos)"""
        if not partida:
            return False
        partida = partida.replace(' ', '').replace('.', '')
        return len(partida) == 10 and partida.isdigit()

    def validate_expediente_export(self, expediente):
        """Valida expediente de exportación antes de enviar"""
        errors = []
        
        if not expediente.remitente:
            errors.append(_("El remitente es obligatorio"))
        elif not expediente.remitente.vat:
            errors.append(_("El remitente debe tener NIF/CIF"))
        elif not self.validate_nif_cif(expediente.remitente.vat):
            errors.append(_("El NIF/CIF del remitente no es válido"))
        
        if not expediente.oficina:
            errors.append(_("La oficina aduanera es obligatoria"))
        elif not self.validate_oficina_aduana(expediente.oficina):
            errors.append(_("La oficina aduanera debe tener 4 dígitos (ej: 0801)"))
        
        if not expediente.line_ids:
            errors.append(_("Debe haber al menos una línea de mercancía"))
        
        for idx, line in enumerate(expediente.line_ids, 1):
            if not line.partida:
                errors.append(_("Línea %d: La partida arancelaria es obligatoria") % idx)
            elif not self.validate_partida_arancelaria(line.partida):
                errors.append(_("Línea %d: La partida arancelaria debe tener 10 dígitos") % idx)
            
            if not line.peso_bruto or line.peso_bruto <= 0:
                errors.append(_("Línea %d: El peso bruto debe ser mayor que 0") % idx)
            
            if not line.peso_neto or line.peso_neto <= 0:
                errors.append(_("Línea %d: El peso neto debe ser mayor que 0") % idx)
            
            if line.peso_neto > line.peso_bruto:
                errors.append(_("Línea %d: El peso neto no puede ser mayor que el peso bruto") % idx)
            
            if not line.valor_linea or line.valor_linea <= 0:
                errors.append(_("Línea %d: El valor de la línea debe ser mayor que 0") % idx)
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        return True

    def validate_expediente_import(self, expediente):
        """Valida expediente de importación antes de enviar"""
        errors = []
        
        if not expediente.remitente:
            errors.append(_("El remitente es obligatorio"))
        elif not expediente.remitente.vat:
            errors.append(_("El remitente debe tener NIF/CIF"))
        elif not self.validate_nif_cif(expediente.remitente.vat):
            errors.append(_("El NIF/CIF del remitente no es válido"))
        
        if not expediente.consignatario:
            errors.append(_("El consignatario es obligatorio"))
        elif not expediente.consignatario.vat:
            errors.append(_("El consignatario debe tener NIF/CIF"))
        elif not self.validate_nif_cif(expediente.consignatario.vat):
            errors.append(_("El NIF/CIF del consignatario no es válido"))
        
        if not expediente.oficina:
            errors.append(_("La oficina aduanera es obligatoria"))
        elif not self.validate_oficina_aduana(expediente.oficina):
            errors.append(_("La oficina aduanera debe tener 4 dígitos (ej: 0801)"))
        
        if not expediente.valor_factura or expediente.valor_factura <= 0:
            errors.append(_("El valor de la factura debe ser mayor que 0"))
        
        if not expediente.line_ids:
            errors.append(_("Debe haber al menos una línea de mercancía"))
        
        for idx, line in enumerate(expediente.line_ids, 1):
            if not line.partida:
                errors.append(_("Línea %d: La partida arancelaria es obligatoria") % idx)
            elif not self.validate_partida_arancelaria(line.partida):
                errors.append(_("Línea %d: La partida arancelaria debe tener 10 dígitos") % idx)
            
            if not line.peso_bruto or line.peso_bruto <= 0:
                errors.append(_("Línea %d: El peso bruto debe ser mayor que 0") % idx)
            
            if not line.peso_neto or line.peso_neto <= 0:
                errors.append(_("Línea %d: El peso neto debe ser mayor que 0") % idx)
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        return True

