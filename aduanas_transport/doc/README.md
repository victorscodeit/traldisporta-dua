# Documentación — módulo `aduanas_transport`

## Guía principal (Traldis Porta)

**→ [GUIA_TRALDIS_PORTA.md](GUIA_TRALDIS_PORTA.md)** — documento recomendado para operadores y administradores de Traldis Porta.

**→ [MANUAL_IMPORTACION_EXPORTACION.html](MANUAL_IMPORTACION_EXPORTACION.html)** — manual HTML (imprimible) con procesos, campos, estados y llamadas AEAT (v16.0.1.0.37).

**Entrega al cliente:** [COMO_ENTREGAR_AL_CLIENTE.md](COMO_ENTREGAR_AL_CLIENTE.md) — editar `GUIA_TRALDIS_PORTA_CLIENTE.md` y ejecutar `python tools/export_guia_cliente.py`.

---

## Contenido reciente en la guía (v16.0.1.0.21)

- **N380 por línea** desde cada factura del bloque Facturas (varias facturas, un DUA).
- **Seguimiento post-MRN:** manual por defecto; **cron bandeja** desarrollado pero desactivado al instalar.
- **Representación directa** documentada (solo exportación).

---

## Resto de documentos

| Archivo | Descripción | Estado |
|---------|-------------|--------|
| [MANUAL_IMPORTACION_EXPORTACION.html](MANUAL_IMPORTACION_EXPORTACION.html) | Manual HTML: flujos, campos, estados, AEAT | **Actual** |
| [GUIA_TRALDIS_PORTA.md](GUIA_TRALDIS_PORTA.md) | Guía operativa completa Traldis | **Actual** |
| [FLUJO_EXPORTACION_ES_AD.md](FLUJO_EXPORTACION_ES_AD.md) | Export AES (CC515C, bandeja, CC507C) | Actual |
| [FLUJO_IMPORTACION_AD_ES.md](FLUJO_IMPORTACION_AD_ES.md) | Import H1 (CC415A), G4/DDT opcional | Actual |
| [CONFIGURAR_CERTIFICADO_AEAT.md](CONFIGURAR_CERTIFICADO_AEAT.md) | Certificado P12/PFX | Actual |
| [PRESENTACION_DUA_Y_PREPRODUCCION.md](PRESENTACION_DUA_Y_PREPRODUCCION.md) | Preproducción y estados | Parcial — ver nota abajo |
| [RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md](RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md) | Campos EXS / DDT técnicos | Referencia |

---

## Notas sobre documentos antiguos

- **Importación:** el endpoint vigente es **CC415AV1SOAP** (`ADIP-JDIT`), no `DeclaracionSOAP` legacy.
- **Exportación:** el flujo principal es **CC515C** con botón *Presentar DUA a AEAT*; CC511C está oculto en la interfaz actual.
- **PDF DUA:** solo exportación, uso interno; AEAT recibe XML (CC515C / CC415A).

Para cualquier duda operativa, usar primero **GUIA_TRALDIS_PORTA.md**.
