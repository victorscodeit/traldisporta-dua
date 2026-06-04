# Flujo de importación en Odoo (H1 CC415A + G4/DDT + G3)

## Servicios separados (no mezclar)

| Servicio | Modelo Odoo (stub/real) | Endpoint típico | XML raíz |
|----------|-------------------------|-----------------|----------|
| **G4 / depósito temporal** | `aeat.import.g4.temporary.storage` | Propio G4 (futuro) | Propio G4 |
| **G3 presentación** | `aeat.import.g3.presentation` | Propio G3 (futuro) | Propio G3 |
| **Importación H1** | `aduana.expediente` (CC415A) | `CC415AV1SOAP` | `CC415AV1Ent` |

## Campos en el expediente de importación

| Campo | Uso |
|-------|-----|
| `requiere_ddt` | Si es verdadero, CC415A debe incluir documento previo N337 y MRN DDT |
| `mrn_ddt` | MRN 18 caracteres del DDT/G4 (obligatorio si `requiere_ddt`) |
| `ddt_type` | `none` / `dsdt` (DDT PreCAU) / `g4` (afecta decimales en kilos N337) |
| `mrn` | MRN de la **declaración de importación** (tras presentar CC415A) |

## Flujo operativo

### Sin DDT previo (`requiere_ddt = false`)

1. Completar expediente y líneas.
2. **1. Validar** → **2. Generar CC415A** → **4. Presentar**.
3. **5. Consultar** / **6. Bandeja** con MRN de importación.

No se genera bloque `PreviousDocument` N337 en el XML.

### Con DDT previo (`requiere_ddt = true`)

1. **0. G4 / DDT** — abre registro stub G4 (presentación AEAT pendiente).
   - Hoy: registrar MRN manualmente en el formulario G4 y **Aplicar MRN al expediente**.
   - Futuro: **Generar XML G4** → **Presentar G4** (endpoint propio).
2. Completar `mrn_ddt`, tipo DSDT/G4, partidas DDT en líneas.
3. **1. Validar** → **2. Generar CC415A** (incluye N337 por partida) → **4. Presentar**.
4. Guardar `mrn` importación → consultar estado y bandeja.

## Botones en cabecera (importación)

| Orden | Botón |
|-------|--------|
| 0 | G4 / DDT (MRN) |
| 1 | Validar importación |
| 2 | Generar CC415A |
| 3 | Previsualizar CC415A |
| 4 | Presentar importación |
| 5 | Consultar estado |
| 6 | Bandeja importación |

## Validación

- Con `requiere_ddt`: exige `mrn_ddt` válido (18 chars o vuelo+conocimiento), tipo DSDT/G4, partida DDT por línea.
- Sin `requiere_ddt`: no exige MRN DDT; permite CC415A sin `PreviousDocument` N337.
