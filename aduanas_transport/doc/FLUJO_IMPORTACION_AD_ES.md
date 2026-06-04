# Flujo de importación Andorra → España (H1 / CC415A) en Odoo

Este documento describe qué puede hacer hoy el operario en el módulo `aduanas_transport` y qué pasos quedan fuera de Odoo.

## Resumen ejecutivo

| Fase | ¿En Odoo hoy? | Notas |
|------|----------------|-------|
| Alta expediente importación | Sí | Manual, MSoft (esqueleto) u OCR de factura |
| Presentar DDT (obtener MRN N337) | **No** | Prerrequisito AEAT; MRN se copia a mano o desde otro expediente |
| Validar datos | Sí | Botón **1. Validar importación** |
| Generar XML CC415A | Sí | Botón **2. Generar CC415A** |
| Presentar a AEAT | Sí | Botón **4. Presentar importación** |
| Consultar estado / bandeja | Sí | Tras MRN de la importación (botones 5 y 6) |

**Conclusión:** el proceso de la **declaración de importación** está cubierto en Odoo, pero **no** la presentación de la **DDT** (documento previo N337). Sin MRN de DDT el operario no puede cerrar el circuito solo desde Odoo.

---

## Flujo recomendado para el operario

### Fase A — Fuera de Odoo (o expediente auxiliar)

1. Presentar la **declaración sumaria de depósito temporal (DDT)** ante AEAT y obtener su **MRN de 18 caracteres** (ej. `24ES00280180000019`).
2. Anotar el MRN y, por cada partida a importar, el **nº de partida DDT** y bultos/kilos que se van a datar.

> Opcional en Odoo: crear un expediente “contenedor” del DDT y guardar ahí el MRN cuando se disponga de él; en el expediente de importación usar **Expediente origen DDT** para copiar el MRN.

### Fase B — Expediente de importación en Odoo

1. Crear expediente con sentido **País tercero → España (Importación)**.
2. **Remitente**: exportador en Andorra (país **AD** en contacto).
3. **Consignatario**: importador español con NIF válido.
4. **Oficina aduanas**, incoterm, lugar entrega, región destino, preferencia, valoración.
5. **MRN DDT** en «MRN / referencia documento previo» o vincular **Expediente origen DDT**.
6. Pestaña **Facturas**: subir PDF → procesar (o rellenar **Líneas** a mano).
7. En líneas: TARIC 10 dígitos, pesos, bultos, **Nº partida DDT**, tipo bulto (`CT`…).
8. Pestaña **Totales**: valor factura y moneda.
9. **Aduanas → Configuración**: certificado y endpoints H1.

### Fase C — Presentación H1

| Paso | Botón | Resultado |
|------|--------|-----------|
| 1 | Validar importación | Errores claros o OK |
| 2 | Generar CC415A | XML adjunto, estado *Predeclarado* |
| 3 | Previsualizar CC415A | Revisar XML |
| 4 | Presentar importación | Envío AEAT; si acepta → **MRN declaración** y estado *Aceptado* |
| 5 | Consultar estado | ConsultaImportacionV3 |
| 6 | Bandeja importación | IMPORAES (levantes/comunicaciones) |

---

## Campos críticos (errores frecuentes AEAT)

- **MRN cabecera expediente**: vacío hasta presentar CC415A (normal).
- **MRN documento previo N337**: obligatorio; 18 caracteres; no usar `EXP-000037` ni `fecha:referencia`.
- **PreviousDocument por línea**: `KGMG`, `quantity` = masa bruta, `numberOfPackages` = bultos (si no es a granel).
- **País expedición**: debe ser **AD** (desde remitente andorrano).

---

## Gaps conocidos (mejoras futuras)

1. **Presentación DDT / alta PreCAU** integrada en Odoo (servicio distinto a CC415A).
2. **Sincronización MSoft** operativa (hoy es esqueleto).
3. **Documento previo 9NDD** u otros tipos cuando no hay DDT (reglas H1 específicas).
4. **Estado levante importación** con colores dedicados (hoy reutiliza lógica export en parte).
5. **Guía operativa** embebida en formulario (checklist ya visible en expediente).

---

## Referencias técnicas

- Presentación: `action_generate_imp_decl`, `action_send_imp_decl`
- Validación: `aduanas.validator.validate_expediente_import`
- XML: `_build_cc415a_soap_envelope`, `_imp_previous_document_xml`
- Consulta: `action_consultar_estado_importacion`, `action_poll_bandeja` (código `IMPORAES`)
