# Guía del módulo Aduanas — Traldis Porta

Documentación operativa del módulo Odoo **`aduanas_transport`** para **Traldis Porta** como **agente de aduanas** y **transportista** en los flujos habituales:

| Flujo | Sentido | Mensaje AEAT | Servicio |
|-------|---------|--------------|----------|
| **Exportación** | España → Andorra / terceros | CC515C (AES) | ADEX-JDIT |
| **Importación** | Andorra → España | CC415A (H1) | ADIP-JDIT |

> **Perfil por defecto Traldis:** representación **indirecta**, transportista = empresa Odoo, **sin DDT/G4** en importación salvo casos excepcionales.

---

## 1. Rol de Traldis Porta en el módulo

| Rol | En Odoo | En el XML AEAT (export, indirecta) | En el XML AEAT (import) |
|-----|---------|--------------------------------------|-------------------------|
| **Agente aduanero** | Compañía Odoo (NIF de la empresa) | **Declarant** | **Declarant** |
| **Exportador / vendedor** | Remitente (cliente, p. ej. Dorel) | **Exporter** | **Seller / Exporter** |
| **Importador** | Consignatario español | — | **Importer** |
| **Transportista** | Campo `transportista` (nombre flota) | Medios de transporte / N705 | Datos de transporte en CC415A |

**Representación indirecta (recomendada):** Traldis declara en nombre del cliente; el exportador/importador es el partner del expediente, no Traldis.

**Representación directa (solo exportación):** declarante = remitente, Traldis = `Representative` en CC515C. Campo `tipo_representacion` en el expediente. Importación: siempre indirecta (Declarant = compañía Odoo).

---

## 2. Configuración inicial (una vez)

### 2.1 Certificado electrónico AEAT

Obligatorio para **Presentar** declaraciones (export e import).

1. **Aduanas → Configuración** (o ficha de **Compañía → AEAT**).
2. Subir certificado **.p12 / .pfx** y contraseña.
3. Comprobar que **no esté caducado** (AEAT devuelve HTML 401 si ha expirado).

Detalle: [CONFIGURAR_CERTIFICADO_AEAT.md](CONFIGURAR_CERTIFICADO_AEAT.md)

### 2.2 Endpoints (preproducción por defecto)

| Servicio | URL preprod |
|----------|-------------|
| Export CC515C | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP` |
| Consulta export CCAESC | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP` |
| Llegada salida CC507C | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP` |
| Import CC415A | `https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP` |
| Consulta import | `https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP` |
| Bandeja | `https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP` |

Para **producción**, cambiar host según guías AEAT (`www1` / `www10` según tipo de certificado).

### 2.3 Perfil Traldis (valores por defecto)

Configurables en **Aduanas → Configuración → Perfil expediente**:

| Parámetro | Valor habitual Traldis |
|-----------|------------------------|
| Tipo representación | **Indirecta** |
| Transportista | Nombre empresa (Traldis Porta) |
| País transporte | ES |
| Oficina export / import | `ES000101` en preprod (ajustar a oficina real en prod, p. ej. `ES002501`) |
| Requiere DDT/G4 | **No** (importación directa en frontera) |
| Incoterm | DAP |
| Moneda | EUR |

Al crear un expediente nuevo, estos valores se aplican automáticamente según el sentido (import/export).

### 2.4 Datos maestros

- **Compañía Odoo:** NIF configurado en la ficha de compañía (actúa como declarante en importación H1).
- **Partners:** remitentes/consignatarios con NIF/EORI válidos en censo AEAT (preprod o prod).

### 2.5 Varias facturas y N380 por línea

- **Un expediente = una presentación AEAT** (CC515C o CC415A) con todas las líneas.
- **Varias facturas PDF** en el mismo expediente: bloque **Facturas** → **Subir facturas** / **Procesar facturas**.
- **N380:** cada línea usa el **Nº factura (N380)** de su factura vinculada; si no hay, el de cabecera (`numero_factura`); si no, `EXP-xxx`. El OCR guarda el nº en cada factura al procesar (v16.0.1.0.21+).
- **Alternativa:** wizard sin expediente → **1 PDF = 1 expediente** nuevo.

---

## 3. Documentos y PDFs — qué hace falta

| Documento | ¿Subir PDF en Odoo? | ¿Se envía a AEAT? |
|-----------|---------------------|-------------------|
| **Factura comercial** | **Sí** (inicio del proceso, OCR) | Solo **referencia N380 por línea** (nº en cada factura o cabecera; no el PDF) |
| **PDF DUA export** (`DUA_EXP-xxx_OFICIAL.pdf`) | Se genera con **Generar DUA** | **No** — archivo interno |
| **XML CC515C / CC415A** | Odoo lo genera y adjunta | **Sí** — es la presentación |
| **CMR / albarán** | Opcional en pestaña Documentos | Referencia N705 en export (matrícula/ref.) |
| **Certificados TARIC** | Pestaña *Documentos requeridos* | **No** automático; gestión interna / requerimientos posteriores AEAT |
| **G4 / DDT** | Solo si `requiere_ddt = true` | MRN N337 en CC415A (no PDF) |

**Conclusión:** tras subir la factura y completar datos, **no hace falta generar un PDF para presentar a AEAT**. En exportación, **Generar DUA** incluye PDF interno opcional; en importación solo existe el XML CC415A.

---

## 4. Flujo exportación (ES → AD)

### 4.1 Pasos en Odoo

```
Factura PDF → Procesar factura → (opc.) Verificación IA
    → Generar DUA → Presentar DUA a AEAT
    → Consultar estado / Notificar llegada salida / Bandeja
```

| Paso | Botón | Resultado |
|------|-------|-----------|
| 1 | **Subir facturas** + **Procesar facturas** (o **Procesar** por línea) | Líneas; **Nº factura (N380)** por factura (OCR) |
| 2 | **Realizar Verificación IA** | Revisión partidas TARIC (opcional) |
| 3 | **Generar DUA** | XML CUSDEC interno + PDF interno; estado *Predeclarado* |
| 4 | **Presentar DUA a AEAT** | Envío **CC515C**; MRN si acepta → *Aceptado* |
| 5 | **Consultar Estado DUA** | CCAESC: estado AES, circuito, fechas |
| 6 | **Notificar Llegada Salida** | CC507C cuando mercancía en aduana de salida |
| 7 | **Consultar Bandeja AEAT** | Levante (`CLEVEX`), salida efectiva (`CSALID`), IVA exento (manual o cron §9) |

> **Nota técnica:** *Presentar* reconstruye el mensaje **CC515C** desde los datos del expediente. El CUSDEC/PDF de *Generar DUA* es documentación interna; la pantalla exige haber generado el DUA antes de presentar.

### 4.2 Campos clave

- Remitente (exportador), consignatario (Andorra), **lugar de entrega** (opcional; CC515C DeliveryTerms), oficina exportación y salida.
- Matrícula / `referencia_transporte` → documento transporte **N705**.
- **N380:** por línea desde factura vinculada o `numero_factura` cabecera.
- Líneas: partida 10 dígitos, pesos, valor.

### 4.3 Estados

`draft` → `predeclared` → **`accepted`** (MRN, tras CC515C) → **`released`** (levante) → **`exited`** (salida UE) → `closed`

El estado `presented` existe en el modelo pero **no se usa** en el flujo CC515C habitual.

Detalle ampliado: [FLUJO_EXPORTACION_ES_AD.md](FLUJO_EXPORTACION_ES_AD.md)

---

## 5. Flujo importación (AD → ES) — habitual Traldis

**Sin depósito temporal:** no usar G3/G4 ni marcar *Requiere DDT/G4*.

### 5.1 Pasos en Odoo

```
Factura PDF → Procesar factura → 1. Validar importación
    → 2. Generar CC415A → 4. Presentar importación
    → 5. Consultar estado / 6. Bandeja
```

| Paso | Botón | Resultado |
|------|-------|-----------|
| 1 | **Subir facturas** + **Procesar facturas** (bloque Facturas) | Datos mercancía y factura (OCR en background) |
| 2 | **1. Validar importación** | Comprueba campos H1 obligatorios (opcional; **2. Generar CC415A** también valida) |
| 3 | **2. Generar CC415A** | Adjunto `EXP-xxx_CC415A.xml`; *Predeclarado* |
| 4 | **4. Presentar importación** | Valida certificado P12; envío SOAP CC415A; MRN si acepta |
| 5 | **5. Consultar estado** | ConsultaImportacionV3 por MRN |
| 6 | **6. Bandeja importación** | Mensajes AEAT importación (manual o cron §9) |

Botones **3. Previsualizar CC415A** sirve para revisar el XML antes de presentar.

### 5.2 Campos clave importación

- Remitente (Andorra), consignatario/importador (España, EORI ES).
- `pais_origen = AD`, `pais_destino = ES`.
- Oficina importación / presentación.
- **Lugar de entrega:** partner + municipio (incoterm DAP u otro).
- **Región destino** (p. ej. `25`), preferencia `100`, valoración `1`, IVA **B00**.
- Líneas: **TARIC 10 dígitos**, pesos, valor; **N380** por línea (factura o cabecera).

### 5.3 Cuándo activar DDT/G4 (no habitual)

Solo si la mercancía viene de **depósito temporal**:

1. Marcar **Requiere DDT/G4 previo**.
2. Botón **0. G4 / DDT** → presentar G4, obtener MRN DDT.
3. CC415A incluirá **PreviousDocument N337** por línea.

Detalle: [FLUJO_IMPORTACION_AD_ES.md](FLUJO_IMPORTACION_AD_ES.md)

---

## 6. EXS (exportación avanzada)

Pestaña **EXS (avanzado)** en expedientes de exportación. Alternativa a CC515C para declaración sumaria (IE615). **No es el flujo principal Traldis** salvo requisito operativo concreto.

---

## 7. Adjuntos y trazabilidad

Tras presentar, revisar en el expediente (pestaña Documentos / chatter):

| Archivo | Cuándo |
|---------|--------|
| `EXP-xxx_CC415A_request.xml` / `_response.xml` | Import presentada |
| `DUA_CC515C_soap.xml` / `DUA_CC515C_response.xml` | Export presentada |
| Factura PDF | Subida al inicio |
| `DUA_EXP-xxx_OFICIAL.pdf` | Tras Generar DUA (export) |

Los errores AEAT quedan en `error_message`, incidencias enlazadas y mensajes del chatter.

---

## 8. Errores frecuentes

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| HTML 403 / “no detecta certificado” | Sin P12 o no usado en HTTPS | Configurar certificado en Aduanas |
| HTML 401 / certificado no autorizado | Certificado caducado o sin permiso ADIP/ADEX | Renovar P12; comprobar censo AEAT |
| “mismatched tag” al presentar | Respuesta HTML en lugar de XML SOAP | Renovar certificado; revisar adjunto respuesta |
| Error funcional AEAT (cas. xxx) | Datos censo, EORI, partida, N380 | Corregir campo indicado en incidencia |
| 9007 / 1092 en preprod | Partner no dado de alta en censo pruebas | Alta en entorno preproducción AEAT |

---

## 9. Seguimiento post-MRN y crons

### 9.1 Manual (por defecto)

Tras obtener MRN, el operador usa los botones **Consultar estado** y **Bandeja** cuando proceda. **Notificar llegada salida** (export) solo manual, en el momento físico del transporte.

No existe cron para **consulta de estado** (CCAESC / ConsultaImportacionV3).

### 9.2 Cron bandeja (desarrollado, desactivado por defecto)

| Parámetro | Valor |
|-----------|--------|
| Acción planificada | «Aduanas (Unificado): Consultar Bandeja AEAT» |
| Método | `aduana.expediente.cron_poll_bandeja_all()` |
| Intervalo | 3 minutos |
| Límite | 50 expedientes por ejecución |
| Estados | `predeclared`, `presented`, `accepted`, `released` |
| Activo al instalar | **No** |

Activar en **Ajustes → Técnico → Automatización → Acciones planificadas**. Misma lógica que `action_poll_bandeja` (EXPORAES / IMPORAES).

### 9.3 Otros crons

| Cron | Activo por defecto |
|------|-------------------|
| Procesar facturas PDF en cola (expedientes) | Sí |
| Procesar facturas pendientes (carga masiva) | No |
| Consultar Bandeja AEAT | No |

---

## 10. Integraciones auxiliares

| Función | Uso Traldis |
|---------|-------------|
| **Subir facturas** (wizard) | Crear expedientes o añadir PDFs en lote |
| **Import MSoft** | Carga desde sistema origen (si configurado) |
| **Documentos requeridos TARIC** | Consulta API UE; subir certificados si la mercancía lo exige |

---

## 11. Documentación técnica complementaria

| Documento | Contenido |
|-----------|-----------|
| [README.md](README.md) | Índice de toda la documentación del módulo |
| [FLUJO_EXPORTACION_ES_AD.md](FLUJO_EXPORTACION_ES_AD.md) | Export AES paso a paso |
| [FLUJO_IMPORTACION_AD_ES.md](FLUJO_IMPORTACION_AD_ES.md) | Import H1, G4/DDT |
| [CONFIGURAR_CERTIFICADO_AEAT.md](CONFIGURAR_CERTIFICADO_AEAT.md) | Certificado P12 |
| [PRESENTACION_DUA_Y_PREPRODUCCION.md](PRESENTACION_DUA_Y_PREPRODUCCION.md) | Preprod (parcial; ver nota al inicio) |
| [RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md](RESUMEN_PRESENTACION_DUA_PREPRODUCCION.md) | Referencia campos EXS/DDT |

**Referencias oficiales AEAT:** Guía WEB Exp (AES), Guía técnica Importación CAU v3.x (H1).

---

## 12. Checklist rápido operador

### Exportación
- [ ] Facturas procesadas; **Nº factura (N380)** en cada factura o cabecera
- [ ] Matrícula / ref. transporte
- [ ] Certificado AEAT vigente
- [ ] Generar DUA → Presentar → MRN
- [ ] Seguimiento: consulta estado (manual), llegada salida (manual), bandeja (manual o cron activo) hasta salida efectiva

### Importación (sin DDT)
- [ ] Facturas procesadas; **N380** por factura; TARIC 10 dígitos por línea
- [ ] Consignatario ES con EORI; remitente AD
- [ ] Incoterm, lugar entrega, región destino, IVA
- [ ] Certificado AEAT vigente
- [ ] Validar → Generar CC415A → Presentar → MRN

---

*Módulo `aduanas_transport` — v16.0.1.0.21 (N380 por factura, cron bandeja documentado).*
