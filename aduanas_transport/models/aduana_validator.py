# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import ValidationError
import re

class AduanaValidator(models.AbstractModel):
    _name = "aduanas.validator"
    _description = "Validador de datos aduaneros"

    def validate_nif_cif(self, vat):
        """Valida formato de NIF/CIF español (admite prefijo de país, ej. ESA58307836)."""
        if not vat:
            return False
        vat = vat.replace(' ', '').replace('-', '').upper()
        # Quitar prefijo de país (p.ej. ES) si viene en el VAT de Odoo
        if len(vat) > 2 and vat[:2].isalpha():
            vat_core = vat[2:]
        else:
            vat_core = vat
        # NIF: 8 dígitos + letra. CIF: letra + 7 dígitos + dígito control, o letra + 8 dígitos.
        # Aceptamos: 8 dígitos + 1 alfanumérico, o 1 letra + 7–8 dígitos (+ opcional control)
        if re.match(r'^\d{8}[A-Z0-9]$', vat_core):
            return True
        if re.match(r'^[A-Z]\d{7}[A-Z0-9]?$', vat_core):  # CIF 9 chars (A58307836) o 8
            return True
        if re.match(r'^[A-Z]\d{8}$', vat_core):
            return True
        return False

    def validate_oficina_aduana(self, oficina):
        """Valida oficina aduanera: 4 dígitos ECS (0801) o AES de 8 (ES000801, ES001741)."""
        if not oficina:
            return False
        oficina = oficina.replace(' ', '').upper()
        if oficina == 'ES0801':
            return False
        if len(oficina) == 4 and oficina.isdigit():
            return True
        if len(oficina) == 8 and re.match(r'^[A-Z]{2}[A-Z0-9]{6}$', oficina):
            return True
        return False

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
            errors.append(_("La oficina aduanera debe ser 4 dígitos (ej: 0801) o código AES de 8 caracteres (ej: ES000801, ES001741)"))
        elif expediente.oficina_destino and not self.validate_oficina_aduana(expediente.oficina_destino):
            errors.append(_("La oficina de salida debe ser 4 dígitos (ej: 1741) o código AES de 8 caracteres (ej: ES001741)"))

        if expediente.direction == "export":
            pais_destino = (expediente.pais_destino or "").strip().upper()
            if not re.match(r"^[A-Z]{2}$", pais_destino):
                errors.append(_("El país destino debe ser un código ISO de 2 letras (ej: AD, CH, GB, MA)"))
            elif expediente.export_destination_type == "other" and pais_destino == "AD":
                errors.append(_("Para 'España → otro país', el país destino no puede ser AD. Seleccione Andorra o indique otro código ISO."))
        
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
            errors.append(_("La oficina aduanera debe ser 4 dígitos (ej: 0801) o código AES de 8 caracteres (ej: ES000801)"))
        
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

