# Mejoras Implementadas: Sistema de Incoterms

## ✅ A) Campo Incoterm como Selection

**Antes:**
```python
incoterm = fields.Char()
```

**Ahora:**
```python
incoterm = fields.Selection([
    ("EXW", "EXW – En fábrica"),
    ("FCA", "FCA – Free Carrier"),
    ("CPT", "CPT – Carriage Paid To"),
    ("CIP", "CIP – Carriage and Insurance Paid To"),
    ("DAP", "DAP – Delivered At Place"),
    ("DPU", "DPU – Delivered at Place Unloaded"),
    ("DDP", "DDP – Delivered Duty Paid"),
], string="Incoterm", default="DAP", tracking=True)
```

**Beneficios:**
- ✅ Validación automática de valores válidos
- ✅ Interfaz más clara con dropdown
- ✅ Tracking de cambios
- ✅ Default a DAP (más común)

---

## ✅ B) Información Contextual del Incoterm

**Campo agregado:**
```python
incoterm_info = fields.Html(string="Información Incoterm", compute="_compute_incoterm_info")
```

**Muestra automáticamente:**
- ✅ Quién paga transporte
- ✅ Quién paga seguro
- ✅ Quién asume riesgo
- ✅ Responsabilidad aduanera (exportación e importación)
- ✅ Descripción del incoterm

**Ejemplo visual:**
```
┌─────────────────────────────────────────┐
│ DAP - Delivered At Place                │
│                                         │
│ Transporte:    Vendedor                │
│ Seguro:        Vendedor                │
│ Riesgo:        Vendedor (hasta destino)│
│ Aduana Exp:    Vendedor                │
│ Aduana Imp:    Comprador                │
└─────────────────────────────────────────┘
```

---

## ✅ C) Cálculo Automático del Valor Aduanero

**Campo agregado:**
```python
valor_aduanero = fields.Float(
    string="Valor Aduanero", 
    compute="_compute_valor_aduanero", 
    store=True,
    help="Valor aduanero calculado automáticamente según incoterm"
)
```

**Campos de gastos adicionales:**
- `gastos_transporte` - Gastos de transporte
- `gastos_seguro` - Gastos de seguro
- `gastos_manipulacion` - Gastos de manipulación
- `gastos_otros` - Otros gastos

**Lógica de cálculo:**

| Incoterm | Fórmula |
|----------|---------|
| **EXW** | `valor_factura + transporte + seguro + manipulación + otros` |
| **FCA** | `valor_factura + seguro + otros` |
| **CPT** | `valor_factura + otros` (transporte ya incluido) |
| **CIP** | `valor_factura + otros` (transporte y seguro ya incluidos) |
| **DAP** | `valor_factura` (todo incluido) |
| **DPU** | `valor_factura` (todo incluido) |
| **DDP** | `valor_factura` (todo incluido) |

**Nota:** Solo se calcula para importación (`direction = "import"`)

---

## ✅ D) Validaciones Automáticas

**Validaciones implementadas en `validate_expediente_import()`:**

### 1. **EXW - Requiere gastos de transporte**
```python
if expediente.incoterm == "EXW":
    if not expediente.gastos_transporte or expediente.gastos_transporte <= 0:
        errors.append("EXW requiere especificar gastos de transporte para cálculo del valor aduanero")
```

### 2. **FCA - Requiere punto de entrega**
```python
if expediente.incoterm == "FCA":
    if not expediente.punto_entrega_fca:
        errors.append("FCA requiere especificar el punto de entrega")
```

### 3. **DAP/DPU/DDP - No permitir gastos duplicados**
```python
if expediente.incoterm in ("DAP", "DPU", "DDP"):
    if expediente.gastos_transporte > 0 or expediente.gastos_seguro > 0:
        errors.append("DAP/DPU/DDP: Los gastos ya están incluidos en el valor de factura. No añada gastos duplicados.")
```

**Campo agregado:**
```python
punto_entrega_fca = fields.Char(string="Punto de Entrega (FCA)", help="Obligatorio para FCA")
```

---

## ✅ E) Ajuste XML al Formato Oficial AEAT

### **Antes (Incorrecto):**
```xml
<TermsOfDelivery>DAP</TermsOfDelivery>
```

### **Ahora (Correcto):**
```xml
<TermsOfDelivery>
    <Code>DAP</Code>
</TermsOfDelivery>
```

**Archivos actualizados:**
1. ✅ `aduanas_transport/data/ir_cron.xml` - Template CC515C (Exportación)
2. ✅ `aduanas_transport/data/ir_cron.xml` - Template Importación

**Cambios realizados:**

**CC515C (Exportación):**
```xml
<!-- Antes -->
<TermsOfDelivery t-esc="exp.incoterm or 'DAP'"/>

<!-- Ahora -->
<TermsOfDelivery>
    <Code t-esc="exp.incoterm or 'DAP'"/>
</TermsOfDelivery>
```

**Importación:**
```xml
<!-- Antes -->
<Incoterm t-esc="exp.incoterm or 'DAP'"/>

<!-- Ahora -->
<Incoterm>
    <Code t-esc="exp.incoterm or 'DAP'"/>
</Incoterm>
```

---

## 📋 Resumen de Campos Agregados

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `incoterm` | Selection | Cambiado de Char a Selection con 7 opciones |
| `incoterm_info` | Html (compute) | Información contextual del incoterm |
| `valor_aduanero` | Float (compute) | Valor aduanero calculado automáticamente |
| `gastos_transporte` | Float | Gastos de transporte |
| `gastos_seguro` | Float | Gastos de seguro |
| `gastos_manipulacion` | Float | Gastos de manipulación |
| `gastos_otros` | Float | Otros gastos |
| `punto_entrega_fca` | Char | Punto de entrega (obligatorio para FCA) |

---

## 🎯 Mejoras en la Vista

### **Sección Incoterm:**
- Campo de selección con dropdown
- Información contextual visible automáticamente
- Campo punto de entrega FCA (visible solo para FCA)

### **Sección Facturación:**
- Campo valor aduanero (solo visible para importación)
- Campos de gastos adicionales (solo visibles para importación y según incoterm)
- Los gastos se ocultan automáticamente para DAP/DPU/DDP

---

## 🔄 Compatibilidad con MSoft

**Actualizado `msoft_import.py`:**
- ✅ Mapeo mejorado de incoterms MSoft → Odoo
- ✅ Manejo de códigos no válidos (FOB → FCA, CIF → CIP)
- ✅ Búsqueda por palabras clave en descripción
- ✅ Validación de incoterms válidos antes de asignar

---

## ✅ Validaciones Implementadas

1. ✅ **EXW:** Requiere gastos de transporte > 0
2. ✅ **FCA:** Requiere punto de entrega especificado
3. ✅ **DAP/DPU/DDP:** No permite gastos duplicados
4. ✅ Validación automática antes de generar/enviar XML

---

## 📝 Próximos Pasos Recomendados

1. **Probar con datos reales** para verificar cálculos
2. **Ajustar fórmulas** si es necesario según reglas aduaneras específicas
3. **Añadir más incoterms** si se requieren (FOB, CIF, etc.)
4. **Documentar** reglas de negocio específicas

---

## 🎉 Estado: COMPLETADO

Todas las mejoras solicitadas han sido implementadas:
- ✅ Campo Selection
- ✅ Información contextual
- ✅ Cálculo automático valor aduanero
- ✅ Validaciones automáticas
- ✅ XML ajustado al formato oficial

