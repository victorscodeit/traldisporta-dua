# -*- coding: utf-8 -*-
"""Revisión TARIC por línea de mercancía: preguntas, documentación y aranceles."""
from odoo import api, fields, models, _


class AduanaExpedienteTaricLinea(models.Model):
    _name = "aduana.expediente.taric.linea"
    _description = "Revisión TARIC por línea de mercancía"
    _order = "item_number, id"

    expediente_id = fields.Many2one(
        "aduana.expediente", string="Expediente", required=True, ondelete="cascade", index=True
    )
    line_id = fields.Many2one(
        "aduana.expediente.line",
        string="Línea mercancía",
        required=True,
        ondelete="cascade",
        index=True,
    )
    factura_id = fields.Many2one(
        "aduana.expediente.factura", string="Factura", ondelete="set null", index=True
    )
    item_number = fields.Integer(string="Partida", related="line_id.item_number", store=True)
    descripcion = fields.Char(string="Mercancía", related="line_id.descripcion", store=True)
    partida_arancelaria = fields.Char(string="Clasificación TARIC", required=True, index=True)
    nomenclatura_desc = fields.Char(string="Descripción nomenclatura AEAT")
    fecha_consulta = fields.Date(string="Fecha consulta")
    resumen_arancelario = fields.Text(string="Resumen arancelario")

    medida_ids = fields.One2many("aduana.expediente.taric.medida", "taric_linea_id", string="Medidas")
    documento_ids = fields.One2many(
        "aduana.expediente.documento.requerido", "taric_linea_id", string="Requisitos"
    )

    preguntas_pendientes_count = fields.Integer(compute="_compute_situacion", store=True)
    docs_pendientes_count = fields.Integer(compute="_compute_situacion", store=True)
    situacion = fields.Selection(
        [
            ("faltan_respuestas", "Faltan respuestas"),
            ("pendiente_aportar", "Pendiente de aportar"),
            ("pendiente_revision", "Pendiente de revisión"),
            ("completo", "Completo"),
            ("sin_consulta", "Sin consulta"),
        ],
        string="Situación",
        compute="_compute_situacion",
        store=True,
    )
    situacion_detalle = fields.Char(string="Detalle situación", compute="_compute_situacion", store=True)

    pregunta_ids = fields.One2many(
        "aduana.expediente.taric.medida",
        "taric_linea_id",
        string="Preguntas",
        domain=[("es_pregunta_operativa", "=", True)],
    )
    arancel_ids = fields.One2many(
        "aduana.expediente.taric.medida",
        "taric_linea_id",
        string="Aranceles",
        domain=[("kind", "=", "duty_info")],
    )
    documento_tarea_ids = fields.One2many(
        "aduana.expediente.documento.requerido",
        "taric_linea_id",
        string="Documentación necesaria",
        domain=[("estado_requisito", "in", ("pendiente_aportar", "pendiente_revision", "validado"))],
    )

    @api.depends(
        "medida_ids.decision_status",
        "medida_ids.kind",
        "medida_ids.es_pregunta_operativa",
        "documento_ids.estado_requisito",
        "documento_ids.aplicabilidad",
    )
    def _compute_situacion(self):
        for rec in self:
            preguntas = rec.medida_ids.filtered(lambda m: m.es_pregunta_operativa)
            pend_preg = preguntas.filtered(
                lambda m: m.decision_status in ("requires_decision",) or m.decision_answer == "unknown"
            )
            docs = rec.documento_ids.filtered(
                lambda d: d.estado_requisito in ("pendiente_aportar", "pendiente_revision")
                or (
                    d.aplicabilidad == "required"
                    and d.estado_requisito not in ("validado", "no_aplica")
                    and d.estado == "pendiente"
                )
            )
            # Normalizar conteo docs por estado_requisito preferente
            docs_aportar = rec.documento_ids.filtered(lambda d: d.estado_requisito == "pendiente_aportar")
            docs_rev = rec.documento_ids.filtered(lambda d: d.estado_requisito == "pendiente_revision")
            rec.preguntas_pendientes_count = len(pend_preg)
            rec.docs_pendientes_count = len(docs_aportar) + len(docs_rev)
            if not rec.medida_ids and not rec.documento_ids:
                rec.situacion = "sin_consulta"
                rec.situacion_detalle = _("Sin consulta TARIC")
            elif pend_preg:
                rec.situacion = "faltan_respuestas"
                rec.situacion_detalle = _("Faltan %s respuesta(s)") % len(pend_preg)
            elif docs_aportar:
                rec.situacion = "pendiente_aportar"
                rec.situacion_detalle = _("Faltan %s requisito(s) por aportar") % len(docs_aportar)
            elif docs_rev:
                rec.situacion = "pendiente_revision"
                rec.situacion_detalle = _("Hay %s requisito(s) por revisar") % len(docs_rev)
            else:
                rec.situacion = "completo"
                rec.situacion_detalle = _("Requisitos resueltos")

    def action_revisar_requisitos(self):
        self.ensure_one()
        view = self.env.ref("aduanas_transport.view_aduana_expediente_taric_linea_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Requisitos TARIC — partida %s") % (self.item_number or self.id),
            "res_model": "aduana.expediente.taric.linea",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": {
                "form_view_initial_mode": "edit",
                "dialog_size": "extra-large",
            },
        }


class AduanaExpedienteTaricMedida(models.Model):
    _name = "aduana.expediente.taric.medida"
    _description = "Medida TARIC AEAT (por línea)"
    _order = "partida_arancelaria, measure_code"

    expediente_id = fields.Many2one(
        "aduana.expediente", string="Expediente", required=True, ondelete="cascade", index=True
    )
    taric_linea_id = fields.Many2one(
        "aduana.expediente.taric.linea", string="Revisión línea", ondelete="cascade", index=True
    )
    line_id = fields.Many2one("aduana.expediente.line", string="Línea mercancía", ondelete="cascade", index=True)
    item_number = fields.Integer(string="Nº partida", related="line_id.item_number", store=True)
    factura_id = fields.Many2one(
        "aduana.expediente.factura", string="Factura", ondelete="set null", index=True
    )
    partida_arancelaria = fields.Char(string="Partida", required=True, index=True)
    measure_code = fields.Char(string="Código medida", required=True, index=True)
    measure_title = fields.Char(string="Descripción medida")
    ambito_geo = fields.Char(string="Ámbito geográfico")
    reglamento = fields.Char(string="Reglamento")
    derechos = fields.Char(string="Derechos")
    condiciones_raw = fields.Text(string="Condiciones (texto AEAT)")
    indicaciones_raw = fields.Text(string="Indicaciones (texto AEAT)")
    raw_json = fields.Text(string="JSON bruto medida")
    fecha_consulta = fields.Date(string="Fecha consulta")
    nomenclatura_desc = fields.Char(string="Descripción nomenclatura")
    operador_explicacion = fields.Text(
        string="Qué comprobar",
        help="Explicación breve para el operario sobre qué debe revisar en la mercancía.",
    )

    kind = fields.Selection(
        [
            ("mandatory_control", "Control obligatorio (decidir)"),
            ("optional_benefit", "Beneficio opcional"),
            ("declaration", "Declaración"),
            ("duty_info", "Información arancelaria"),
            ("other", "Otra"),
        ],
        string="Tipo lógico",
        default="other",
    )
    es_pregunta_operativa = fields.Boolean(
        string="Es pregunta operativa",
        compute="_compute_es_pregunta_operativa",
        store=True,
    )
    decision_question = fields.Char(string="Pregunta de decisión")
    decision_status = fields.Selection(
        [
            ("requires_decision", "Pendiente de decisión"),
            ("decided", "Decidido"),
            ("not_applicable", "No aplicable"),
            ("info_only", "Solo informativo"),
        ],
        string="Estado decisión",
        default="requires_decision",
    )
    decision_answer = fields.Selection(
        [
            ("yes", "Sí / procede control"),
            ("no", "No / no procede"),
            ("claim", "Solicitar beneficio"),
            ("skip", "No solicitar"),
            ("unknown", "No lo sé / solicitar revisión"),
        ],
        string="Respuesta",
    )
    selected_certificate_code = fields.Char(string="Código seleccionado")
    option_yes_code = fields.Char(string="Código si Sí / acogerse")
    option_no_code = fields.Char(string="Código si No / no acogerse")
    option_yes_label = fields.Char(string="Etiqueta opción A")
    option_no_label = fields.Char(string="Etiqueta opción B")

    condicion_ids = fields.One2many(
        "aduana.expediente.taric.condicion", "medida_id", string="Condiciones"
    )
    documento_ids = fields.One2many(
        "aduana.expediente.documento.requerido", "taric_medida_id", string="Documentos"
    )

    @api.depends("kind", "decision_status")
    def _compute_es_pregunta_operativa(self):
        for rec in self:
            rec.es_pregunta_operativa = rec.kind in (
                "mandatory_control",
                "optional_benefit",
                "declaration",
            ) and rec.decision_status != "info_only"

    def action_decidir_si(self):
        return self._aplicar_decision("yes")

    def action_decidir_no(self):
        return self._aplicar_decision("no")

    def action_decidir_acogerse(self):
        return self._aplicar_decision("claim")

    def action_decidir_no_acogerse(self):
        return self._aplicar_decision("skip")

    def action_decidir_desconocido(self):
        return self._aplicar_decision("unknown")

    def action_ver_fundamento(self):
        self.ensure_one()
        view = self.env.ref("aduanas_transport.view_aduana_expediente_taric_medida_fundamento")
        return {
            "type": "ir.actions.act_window",
            "name": _("Fundamento TARIC — %s") % (self.measure_code or ""),
            "res_model": "aduana.expediente.taric.medida",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": {"dialog_size": "extra-large"},
        }

    def _aplicar_decision(self, answer):
        self.ensure_one()
        options = self._decision_options_from_condiciones()
        if answer == "unknown":
            self.write({
                "decision_answer": "unknown",
                "decision_status": "requires_decision",
                "selected_certificate_code": False,
            })
            self._sync_documentos_aplicabilidad(chosen_code=None, mode="unknown")
        elif self.kind == "optional_benefit":
            if answer == "claim":
                chosen_code = (
                    self.option_yes_code
                    or (options.get("yes") or {}).get("code")
                    or (options.get("claim") or {}).get("code")
                )
                self.write({
                    "decision_answer": "claim",
                    "decision_status": "decided",
                    "selected_certificate_code": chosen_code or False,
                })
                self._sync_documentos_aplicabilidad(chosen_code=chosen_code, mode="optional_claim")
            else:
                self.write({
                    "decision_answer": "skip",
                    "decision_status": "not_applicable",
                    "selected_certificate_code": False,
                })
                self._sync_documentos_aplicabilidad(chosen_code=None, mode="optional_skip")
        else:
            key = "yes" if answer == "yes" else "no"
            chosen_code = (
                (self.option_yes_code if key == "yes" else self.option_no_code)
                or (options.get(key) or {}).get("code")
            )
            if answer == "no" and not chosen_code:
                # Sin alternativa documental: el operario indica que el control no procede
                self.write({
                    "decision_answer": "no",
                    "decision_status": "not_applicable",
                    "selected_certificate_code": False,
                })
                self._sync_documentos_aplicabilidad(chosen_code=None, mode="optional_skip")
            else:
                self.write({
                    "decision_answer": answer,
                    "decision_status": "decided" if chosen_code else "requires_decision",
                    "selected_certificate_code": chosen_code or False,
                })
                if chosen_code:
                    self._sync_documentos_aplicabilidad(chosen_code=chosen_code, mode="binary")
                elif answer == "yes" and not chosen_code and self.documento_ids:
                    # Control sin código C/Y: exigir el documento de la medida
                    first = self.documento_ids[:1]
                    self.write({"selected_certificate_code": first.codigo_documento})
                    self._sync_documentos_aplicabilidad(
                        chosen_code=first.codigo_documento, mode="binary"
                    )
        # Recargar el popup de requisitos (act_window completo con views; evita error .map)
        if self.taric_linea_id:
            linea = self.taric_linea_id
            linea.invalidate_recordset()
            linea._compute_situacion()
            return linea.action_revisar_requisitos()
        return False

    def _decision_options_from_condiciones(self):
        self.ensure_one()
        options = {}
        if self.option_yes_code:
            options["yes"] = {"code": self.option_yes_code, "name": self.option_yes_label or self.option_yes_code}
        if self.option_no_code:
            options["no"] = {"code": self.option_no_code, "name": self.option_no_label or self.option_no_code}
        docs = self.condicion_ids.filtered(
            lambda c: c.role in ("document", "declaration") and c.certificate_code
        )
        c_codes = docs.filtered(lambda c: (c.certificate_code or "")[:1] == "C")
        y_codes = docs.filtered(lambda c: (c.certificate_code or "")[:1] == "Y")
        if "yes" not in options and c_codes:
            options["yes"] = {"code": c_codes[0].certificate_code, "name": c_codes[0].name}
        if "no" not in options and y_codes:
            options["no"] = {"code": y_codes[0].certificate_code, "name": y_codes[0].name}
        if "no" not in options and docs and not c_codes:
            options["no"] = {"code": docs[0].certificate_code, "name": docs[0].name}
        if "yes" not in options or "no" not in options:
            linked = self.documento_ids
            if "yes" not in options:
                cdoc = linked.filtered(lambda d: (d.codigo_documento or "")[:1] == "C")[:1]
                if cdoc:
                    options["yes"] = {"code": cdoc.codigo_documento, "name": cdoc.name}
            if "no" not in options:
                ydoc = linked.filtered(lambda d: (d.codigo_documento or "")[:1] == "Y")[:1]
                if ydoc:
                    options["no"] = {"code": ydoc.codigo_documento, "name": ydoc.name}
        return options

    def _tipo_requisito_for_code(self, code):
        code = (code or "").upper()
        if not code:
            return "documento"
        if code[0] == "Y":
            return "declaracion"
        if code in ("C990",) or "autoriz" in (self.measure_title or "").lower():
            return "autorizacion"
        if self.kind == "optional_benefit":
            return "autorizacion"
        return "documento"

    def _sync_documentos_aplicabilidad(self, chosen_code=None, mode="binary"):
        self.ensure_one()
        chosen = (chosen_code or "").upper() or None
        for doc in self.documento_ids:
            code = (doc.codigo_documento or "").upper()
            tipo = self._tipo_requisito_for_code(code)
            vals = {"tipo_requisito": tipo}
            if mode == "unknown":
                vals.update({
                    "aplicabilidad": "pending_information",
                    "mandatory": False,
                    "estado_requisito": "por_determinar",
                    "motivo_no_aplica": False,
                })
            elif mode == "optional_skip":
                motivo = (
                    _("Beneficio no solicitado")
                    if self.kind == "optional_benefit"
                    else _("Control no procede según respuesta del operario")
                )
                vals.update({
                    "aplicabilidad": "not_applicable",
                    "mandatory": False,
                    "estado_requisito": "no_aplica",
                    "motivo_no_aplica": motivo,
                })
            elif mode == "optional_claim":
                if chosen and code == chosen:
                    vals.update({
                        "aplicabilidad": "optional_benefit",
                        "mandatory": False,
                        "estado_requisito": "pendiente_aportar",
                        "motivo_no_aplica": False,
                    })
                else:
                    vals.update({
                        "aplicabilidad": "not_applicable",
                        "mandatory": False,
                        "estado_requisito": "no_aplica",
                        "motivo_no_aplica": _("Alternativa no elegida"),
                    })
            else:
                if not chosen:
                    continue
                if code == chosen:
                    vals.update({
                        "aplicabilidad": "required",
                        "mandatory": True,
                        "estado_requisito": "pendiente_aportar" if doc.estado == "pendiente" else (
                            "pendiente_revision" if doc.estado == "subido" else "validado"
                        ),
                        "motivo_no_aplica": False,
                    })
                else:
                    vals.update({
                        "aplicabilidad": "not_applicable",
                        "mandatory": False,
                        "estado_requisito": "no_aplica",
                        "motivo_no_aplica": _("Alternativa descartada al responder la pregunta"),
                    })
            doc.write(vals)


class AduanaExpedienteTaricCondicion(models.Model):
    _name = "aduana.expediente.taric.condicion"
    _description = "Condición / alternativa de una medida TARIC"
    _order = "sequence, id"

    medida_id = fields.Many2one(
        "aduana.expediente.taric.medida",
        string="Medida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Secuencia", default=10)
    condition_branch = fields.Char(string="Rama condición")
    certificate_code = fields.Char(string="Código certificado/declaración")
    name = fields.Char(string="Descripción")
    role = fields.Selection(
        [
            ("document", "Documento a presentar"),
            ("declaration", "Declaración TARIC (Y…)"),
            ("branch", "Rama / condición (B…)"),
            ("deny", "Prohibición / no autorizado"),
            ("other", "Otro"),
        ],
        string="Rol",
        default="other",
    )
    action_label = fields.Char(string="Acción AEAT")
