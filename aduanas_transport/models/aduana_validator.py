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

    def _validate_n337_mrn_format(self, mrn):
        ref = (mrn or "").strip().upper().replace(" ", "")
        if not ref:
            return False, _("Indique el MRN DDT/G4 (campo «MRN DDT/G4»).")
        valid_mrn = bool(len(ref) == 18 and re.match(r"^[A-Z0-9]{18}$", ref))
        valid_plus = (len(ref) > 16 and ref[16] == "+") or (len(ref) > 18 and ref[18] == "+")
        if valid_mrn or valid_plus:
            return True, None
        return False, _(
            "El MRN DDT/G4 debe tener 18 caracteres (ej. 24ES00280180000019) "
            "o formato vuelo+conocimiento con «+» en posición 17 o 19."
        )

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
            elif pais_destino == "ES":
                errors.append(_("En exportación España → País tercero, el país destino no puede ser ES. Revise el destinatario."))
        
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
        """Valida expediente de importación antes de enviar CC415A."""
        errors = []
        
        if not expediente.remitente:
            errors.append(_("El remitente es obligatorio"))
        
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

        pais_origen = (expediente.pais_origen or "").strip().upper()
        pais_destino = (expediente.pais_destino or "").strip().upper()
        if not re.match(r"^[A-Z]{2}$", pais_origen):
            errors.append(_("El país origen debe ser un código ISO de 2 letras (ej: AD, CH, GB, MA)"))
        elif pais_origen != "AD":
            errors.append(_("En importación Andorra → España, countryOfDispatch debe ser AD. Revise el remitente."))
        if pais_destino != "ES":
            errors.append(_("En importación Andorra → España, countryOfDestination debe ser ES."))
        if not (getattr(expediente, "import_region_of_destination", "") or "").strip():
            errors.append(_("En importación H1 debe informarse Region of Destination."))
        preference = (getattr(expediente, "import_preference", "") or "").strip()
        if not re.match(r"^[0-9]{3}$", preference):
            errors.append(_("En importación H1, la preferencia debe tener 3 dígitos (ej: 100)."))
        valuation_method = (getattr(expediente, "import_valuation_method", "") or "").strip()
        if not re.match(r"^[0-9]{1}$", valuation_method):
            errors.append(_("En importación H1, el método de valoración debe tener 1 dígito (ej: 1)."))
        vat_rate = float(getattr(expediente, "import_vat_rate", 21.0) or 0.0)
        if vat_rate <= 0:
            errors.append(_("El tipo de IVA de importación debe ser mayor que 0 (casilla 47 / B00)."))
        tax_pay_method = (getattr(expediente, "import_tax_method_of_payment", "") or "E").strip().upper()[:1]
        if not re.match(r"^[A-Z]$", tax_pay_method):
            errors.append(_("El modo de pago de tributos debe ser una letra A-Z (ej: E)."))

        requiere_ddt = bool(getattr(expediente, "requiere_ddt", False))
        ddt_type = getattr(expediente, "ddt_type", "none") or "none"
        mrn_ddt = ""
        if hasattr(expediente, "_get_mrn_ddt"):
            mrn_ddt = expediente._get_mrn_ddt()
        else:
            mrn_ddt = (getattr(expediente, "mrn_ddt", "") or getattr(expediente, "import_previous_document_ref", "") or "").strip()

        if requiere_ddt:
            if ddt_type == "none":
                errors.append(_("Si «Requiere DDT/G4 previo» está activo, seleccione tipo DSDT o G4."))
            ok, msg = self._validate_n337_mrn_format(mrn_ddt)
            if not ok:
                errors.append(msg)
            elif len((mrn_ddt or "").replace(" ", "")) == 18 and re.match(
                r"^[A-Z0-9]{18}$", (mrn_ddt or "").upper().replace(" ", "")
            ):
                for idx, line in enumerate(expediente.line_ids, 1):
                    ddt_item = getattr(line, "import_ddt_goods_item", False) or line.item_number
                    if not ddt_item:
                        errors.append(
                            _("Línea %d: indique el nº de partida del DDT (campo «Nº partida DDT»).") % idx
                        )

        if getattr(expediente, "requested_procedure", "40") != "40":
            errors.append(_("Para importación normal, requestedProcedure debe ser 40."))
        if getattr(expediente, "previous_procedure", "00") != "00":
            errors.append(_("Para importación normal, previousProcedure debe ser 00."))
        
        if not expediente.line_ids:
            errors.append(_("Debe haber al menos una línea de mercancía"))
        
        for idx, line in enumerate(expediente.line_ids, 1):
            taric = (getattr(line, "taric_completo", False) or line.partida or "").replace(" ", "").replace(".", "")
            if not taric:
                errors.append(_("Línea %d: El TARIC completo es obligatorio") % idx)
            elif not self.validate_partida_arancelaria(taric):
                errors.append(_("Línea %d: El TARIC completo debe tener 10 dígitos. No se asume validez arancelaria automática.") % idx)
            
            if not line.peso_bruto or line.peso_bruto <= 0:
                errors.append(_("Línea %d: El peso bruto debe ser mayor que 0") % idx)
            
            if not line.peso_neto or line.peso_neto <= 0:
                errors.append(_("Línea %d: El peso neto debe ser mayor que 0") % idx)
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        return True
