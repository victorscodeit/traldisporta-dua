# Guía del módulo Aduanas — Traldis Porta

Documentación operativa del módulo Odoo **aduanas_transport** (versión **16.0.1.0.22**) para **Traldis Porta** como **agente de aduanas** y **transportista**:

| Flujo | Sentido | Mensaje AEAT | Servicio |
|-------|---------|--------------|----------|
| **Exportación** | España → Andorra / terceros | CC515C (AES) | ADEX-JDIT |
| **Importación** | Andorra → España | CC415A (H1) | ADIP-JDIT |

Perfil habitual Traldis: representación **indirecta**, transportista = empresa Odoo, importación **sin DDT/G4** salvo depósito temporal.

---

## 1. Rol de Traldis Porta en el módulo

| Rol | En Odoo | En el XML AEAT (export, indirecta) | En el XML AEAT (import) |
|-----|---------|--------------------------------------|-------------------------|
| **Agente aduanero** | Compañía Odoo (NIF de la empresa) | Declarant | Declarant |
| **Exportador / vendedor** | Remitente (cliente) | Exporter | Seller / Exporter |
| **Importador** | Consignatario español | — | Importer |
| **Transportista** | Campo transportista | Medios transporte / N705 | Datos transporte CC415A |

**Representación indirecta (recomendada):** Traldis declara en nombre del cliente. El exportador o importador es el partner del expediente.

**Representación directa (solo exportación):** el **declarante** en el XML es el remitente (cliente) y Traldis figura como **Representative**. Campo **Tipo representación** en expedientes de exportación. Requiere mandato legal del cliente. **Importación:** el módulo usa siempre representación indirecta (Declarant = Traldis).

---

## 2. Configuración inicial (una vez)

### 2.1 Certificado electrónico AEAT

Obligatorio para **Presentar** declaraciones (exportación e importación).

1. Menú **Aduanas → Configuración** (o **Compañía → pestaña AEAT**).
2. Subir certificado **.p12 / .pfx** y contraseña (puede configurarse a nivel global o en la ficha de compañía).
3. Verificar vigencia: un certificado caducado provoca rechazo AEAT (401 o página HTML de error aunque HTTP sea 200).

**Antes de presentar importación**, el sistema valida automáticamente que el P12 exista, la contraseña sea correcta y el certificado no esté caducado; si falla, muestra el error y no envía la petición. En exportación la comprobación ocurre al realizar la llamada HTTPS (mismos síntomas si el certificado no es válido).

### 2.2 Endpoints (preproducción por defecto)

| Servicio | Uso | URL preprod (valores por defecto del módulo) |
|----------|-----|-----------------------------------------------|
| CC515C | Presentar exportación | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP` |
| CCAESC | Consultar estado export | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CCAESCV1SOAP` |
| CC507C | Llegada en aduana de salida | `https://prewww1.aeat.es/wlpl/ADEX-JDIT/ws/aes/CC507CV1SOAP` |
| CC415A | Presentar importación H1 | `https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/CC415AV1SOAP` |
| Consulta import V3 | Estado importación por MRN | `https://prewww1.aeat.es/wlpl/ADIP-JDIT/ws/cci/ConsultaImportacionV3SOAP` |
| Bandeja | Levantes y salidas | `https://prewww1.aeat.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP` |
| EXS (IE615) | Declaración sumaria export | `https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP` |
| G4Dec | Depósito temporal (DDT/G4) | `https://prewww1.aeat.es/wlpl/ADDS-JDIT/ws/G4DecV1SOAP` |

En **producción** el administrador cambiará el host según el certificado (`www1` o `www10` según guías AEAT).

### 2.3 Perfil Traldis (valores por defecto)

En **Aduanas → Configuración → Perfil expediente**:

| Parámetro | Valor habitual |
|-----------|----------------|
| Tipo representación | Indirecta |
| Transportista | Traldis Porta |
| País transporte | ES |
| Oficina export / import | ES000101 (preprod); en producción la oficina real (p. ej. ES002501) |
| Requiere DDT/G4 | No |
| Incoterm | DAP |
| Moneda | EUR |

Al crear un expediente, estos valores se aplican según el sentido (import / export).

### 2.4 Datos maestros

- **Compañía Odoo:** NIF configurado en la ficha de compañía (actúa como declarante en importación).
- **Partners:** remitentes y consignatarios con NIF/EORI dados de alta en el censo AEAT del entorno que se use (preprod o producción).

### 2.5 Varias facturas, un expediente y documento N380

| Concepto | Comportamiento del módulo |
|----------|---------------------------|
| **Un expediente** | Una presentación AEAT (un CC515C o un CC415A) con todas las líneas de mercancía |
| **Varias facturas PDF** | Permitido en el bloque **Facturas** del mismo expediente (p. ej. un camión, varios albaranes) |
| **Un expediente por factura** | El wizard **Subir facturas** sin expediente previo crea **un expediente por PDF** (alternativa habitual si cada factura es una operación distinta) |
| **N380 en AEAT** | Referencia de factura comercial **por línea** en el XML; **no se envía el PDF** |

**N380 — prioridad por línea** (desde v16.0.1.0.21):

1. **Nº factura (N380)** de la factura PDF vinculada a la línea (columna en bloque Facturas; el OCR lo rellena al procesar).
2. Si no hay factura vinculada o falta nº: **Nº factura comercial** de cabecera del expediente.
3. Si tampoco hay: nombre del expediente (`EXP-xxx`).

Antes de **Generar DUA** / **Generar CC415A**, comprobar que cada factura tiene su **Nº factura (N380)** o que la cabecera del expediente tiene un valor común. Si falta, la validación mostrará error.

---

## 3. Flujo exportación (España → Andorra)

### 3.1 Visión general

Traldis actúa como **declarante**; el **remitente** es el exportador español y el **consignatario** el destinatario en Andorra (u otro país tercero). El ciclo completo cubre desde la carga de la factura hasta la **salida efectiva** de la mercancía de la UE (relevante para IVA exportación exento).

```
Borrador → Predeclarado → Aceptado (MRN) → Levante → Salida efectiva → Cerrado
```

Tras **Presentar DUA a AEAT** (CC515C), si AEAT admite la declaración el expediente pasa directamente a **Aceptado** con MRN. El estado *Presentado* existe en la barra de estados pero **no se usa** en el flujo habitual CC515C.

### 3.2 Paso A — Crear expediente y cargar factura

1. **Aduanas → Expedientes → Crear.**
2. Sentido: **Exportación**.
3. En el bloque **Facturas** del formulario, subir el PDF comercial con **Subir facturas** (varios PDF a la vez) o desde la pestaña **Facturas**.
4. Completar si falta:
   - **Remitente** (exportador, p. ej. planta en España).
   - **Consignatario** (cliente en Andorra).
   - **Oficina** de exportación y **oficina de salida** declarada.
   - **Matrícula** del vehículo y, si aplica, referencia de transporte.

### 3.3 Paso B — Procesar factura PDF

1. En el bloque **Facturas**, pulsar **Procesar facturas** (todas las pendientes) o **Procesar** en cada línea de factura.
2. El procesamiento se ejecuta en **segundo plano** (cola `queue_job`); la vista se actualiza al terminar. Aparece el estado por factura: pendiente, procesando, completado, advertencia o error.
3. El botón de cabecera **Procesar Factura PDF** solo aplica al campo legacy de factura única en el expediente; el flujo habitual es el bloque **Facturas**.
4. El sistema extrae (IA/OCR): líneas de mercancía, partidas, pesos, valores y número de factura.
5. Revisar pestaña **Líneas de mercancía**:
   - Partida arancelaria **10 dígitos**.
   - Peso bruto y neto por línea.
   - Valor línea coherente con total factura.
6. Revisar en el bloque **Facturas** la columna **Nº factura (N380)** de cada PDF procesado (editable si el OCR no lo detectó). Opcional: **Nº factura comercial** en cabecera como valor común para líneas sin factura vinculada.

**Si algo falla:** corregir manualmente las líneas o volver a procesar tras ajustar el PDF.

### 3.4 Paso C — Verificación IA (opcional)

1. **Realizar Verificación IA** — normaliza partidas a 10 dígitos y señala incoherencias valor/peso.
2. Corregir líneas marcadas antes de generar el DUA.

### 3.5 Paso D — Generar DUA

1. Pulsar **Generar DUA**.
2. El sistema valida datos obligatorios y genera documentación interna; el expediente pasa a **Predeclarado**.
3. Revisar adjuntos en **Documentos** (XML interno y, si el servidor lo permite, PDF resumen).

**Importante:** este paso prepara y valida el expediente. La presentación real a AEAT usa el mensaje **CC515C** (paso siguiente).

### 3.6 Paso E — Presentar DUA a AEAT

1. Con el DUA generado, pulsar **Presentar DUA a AEAT**.
2. Odoo valida datos de exportación, construye **CC515C** y lo envía al servicio AES con el certificado configurado.
3. **Si AEAT acepta:** se guarda el **MRN**, estado **Aceptado**, y datos AES (estado, circuito, CSV si vienen en respuesta).
4. **Si AEAT rechaza:** estado **Error**, mensaje en el expediente e **incidencias** con el detalle funcional (EORI, partida, consignatario, etc.). Corregir y volver a presentar.
5. **Errores de certificado** (403 HTTP, 401 o página HTML de la AEAT): revisar P12, contraseña y fecha de caducidad en **Aduanas → Configuración**.

Los XML de petición y respuesta quedan adjuntos al expediente y en el chatter.

### 3.7 Paso F — Seguimiento post-admisión

Con **MRN** asignado el seguimiento puede ser **manual** (botones) o **parcialmente automático** (cron de bandeja, ver §9).

| Acción | Cuándo usarla | Qué aporta | Automatizable |
|--------|---------------|------------|---------------|
| **Consultar Estado DUA** | Tras admisión o si hay dudas | Estado AES, circuito, fechas vía CCAESC | No (solo manual) |
| **Notificar Llegada Salida** | Mercancía en aduana de salida | CC507C | No (depende del momento físico del transporte) |
| **Consultar Bandeja AEAT** | Levante y salida efectiva | CLEVEX, CSALID, IVA exento | **Sí** — cron opcional |

Cuando la bandeja confirma **salida efectiva**, el expediente refleja **Salida efectiva** e **IVA exportación exento**.

### 3.8 Campos críticos exportación

| Campo Odoo | Efecto en AEAT |
|-------------|----------------|
| Remitente (NIF/EORI) | Exportador |
| Consignatario | Destinatario en Andorra |
| Oficina / oficina destino | Aduanas exportación y salida |
| Matrícula | Identificación transporte y doc. N705 |
| Nº factura (por factura o cabecera) | Referencia **N380** en cada línea del XML |
| Incoterm | Condiciones entrega |
| Líneas (partida, peso, valor) | Partidas CC515C |

### 3.9 Estados del expediente (export)

| Estado | Significado operativo |
|--------|------------------------|
| Borrador | En preparación |
| Predeclarado | DUA generado, listo para presentar |
| Presentado | Reservado (no usado en flujo CC515C habitual) |
| Aceptado | MRN recibido tras presentación CC515C |
| Levante | Mercancía liberada para salir |
| Salida efectiva | Confirmada salida de la UE |
| Error | Rechazo o incidencia; revisar mensaje |
| Cerrado | Expediente archivado / terminado (manual o automático, ver §8.4) |

---

## 4. Flujo importación (Andorra → España)

Flujo **habitual Traldis:** importación directa en frontera, **sin** depósito temporal (no marcar *Requiere DDT/G4*).

### 4.1 Visión general

Traldis es **declarante**; el **remitente** está en Andorra y el **consignatario** es el importador español. La declaración es **H1 (CC415A)** al servicio de importación ADIP-JDIT.

```
Borrador → Predeclarado → Aceptado (MRN) → consulta / bandeja → Cerrado
```

### 4.2 Paso A — Crear expediente y cargar factura

1. **Aduanas → Expedientes → Crear.**
2. Sentido: **Importación**.
3. Subir factura PDF en el bloque **Facturas** (**Subir facturas** o pestaña **Facturas**).
4. Completar:
   - **Remitente** (proveedor en Andorra) — país origen AD.
   - **Consignatario** (importador en España) — debe tener NIF/EORI español válido.
   - **Oficina** de importación / presentación.
   - **Lugar de entrega** (partner de entrega; por defecto el consignatario).
   - **Incoterm** (habitual DAP) y datos de transporte (matrícula).

Verificar que **Requiere DDT/G4** esté **desmarcado** salvo mercancía en depósito temporal.

### 4.3 Paso B — Procesar factura PDF

1. **Procesar facturas** (bloque Facturas) o **Procesar** en cada línea; el OCR/IA corre en segundo plano.
2. Revisar líneas y, en **Facturas**, el **Nº factura (N380)** de cada PDF.
   - **TARIC completo 10 dígitos** (obligatorio en H1).
   - Pesos bruto/neto y valor por línea.
3. Revisar bloque **Importación — factura y entrega** e **Importación — tributos H1**:
   - Región destino (p. ej. 25).
   - Preferencia 100, método valoración 1.
   - Tipo IVA 21 % (casilla 47 / tributo B00).
   - Modo de pago tributos (E).

### 4.4 Paso C — Validar importación

1. Pulsar **1. Validar importación**.
2. El sistema comprueba: partners, oficina, países AD→ES, TARIC, valores, lugar entrega, campos H1.
3. Si hay errores, aparecen en pantalla; corregir antes de generar el XML.

### 4.5 Paso D — Generar CC415A

1. Pulsar **2. Generar CC415A** (incluye validación automática de datos obligatorios, equivalente a **1. Validar importación**).
2. Se crea el adjunto `EXP-xxx_CC415A.xml` y el estado pasa a **Predeclarado**.
3. Opcional: **3. Previsualizar CC415A** para revisar el XML antes de enviar.

El XML incluye por línea: procedimiento 40/00, origen AD, TARIC, IVA B00, factura N380, incoterm y datos de Traldis como declarante.

### 4.6 Paso E — Presentar importación

1. Pulsar **4. Presentar importación**.
2. Odoo comprueba primero el certificado (existencia, contraseña y caducidad); si falla, muestra el error sin enviar.
3. Si el certificado es válido, envía **CC415A** al servicio ADIP-JDIT.
4. **Aceptación:** MRN de importación, estado **Aceptado**, mensaje en chatter.
5. **Rechazo o error HTTP:** estado **Error**, detalle en *Mensaje de error* e incidencias; los adjuntos y notas del chatter se conservan (no se pierde la trazabilidad). Corregir datos y repetir desde validar/generar si cambió el XML.
6. AEAT puede devolver **401/403 en página HTML** aun con HTTP 200; el módulo detecta este caso y muestra un mensaje claro (certificado caducado o no enviado).

Quedan adjuntos `EXP-xxx_CC415A_request.xml` y `_response.xml`.

### 4.7 Paso F — Seguimiento post-admisión

| Acción | Uso | Automatizable |
|--------|-----|---------------|
| **5. Consultar estado** | Consulta completa por MRN (ConsultaImportacionV3) | No (solo manual) |
| **6. Bandeja importación** | Mensajes AEAT de importación (levantes, incidencias) | **Sí** — cron opcional (misma acción que export, bandeja IMPORAES) |

### 4.8 Campos críticos importación

| Campo / bloque | Detalle |
|----------------|---------|
| Remitente AD | countryOfDispatch = AD |
| Consignatario ES | Importer con EORI ES |
| Oficina | CustomsOfficeOfImport y Presentation |
| Lugar entrega | DeliveryTerms (incoterm + municipio) |
| Región destino | p. ej. 25 (Lleida / demarcación habitual) |
| Tributos H1 | IVA B00, preferencia, valoración |
| Líneas TARIC 10 | hs + cn + taric, masas, valor factura |

### 4.9 Importación con DDT/G4 (caso excepcional)

Solo si la mercancía procede de **depósito temporal**:

1. Activar **Requiere DDT/G4 previo** y tipo DSDT o G4.
2. **0. G4 / DDT** — presentar depósito y obtener MRN DDT.
3. Indicar MRN DDT y partida DDT por línea.
4. Continuar con validar → CC415A → presentar (el XML incluirá PreviousDocument N337).

Este flujo **no es el habitual** en Traldis para entradas directas AD→ES.

### 4.10 Estados del expediente (import)

| Estado | Significado |
|--------|-------------|
| Borrador | En preparación |
| Predeclarado | CC415A generado |
| Aceptado | MRN importación recibido |
| Error | Rechazo AEAT |
| Cerrado | Finalizado |

---

## 5. EXS (exportación avanzada)

Pestaña **EXS (avanzado)** en expedientes de exportación, con botón **Presentar EXS** (mensaje IE615 al endpoint configurado). **No sustituye** el flujo CC515C salvo requisito operativo concreto. No es el procedimiento principal de Traldis.

---

## 6. Adjuntos y trazabilidad

Tras presentar, en **Documentos** o **chatter** del expediente:

| Archivo | Cuándo |
|---------|--------|
| EXP-xxx_CC415A_request/response.xml | Importación presentada |
| DUA_CC515C_soap/response.xml | Exportación presentada |
| Factura PDF | Subida al inicio |
| DUA_EXP-xxx_OFICIAL.pdf | Tras Generar DUA (export, interno) |

Errores AEAT: campo *Mensaje de error*, incidencias enlazadas y notas del chatter.

---

## 7. Errores frecuentes

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| Error 403 / no detecta certificado | Certificado no configurado o no usable en HTTPS | Aduanas → Configuración → P12; comprobar `cryptography` en servidor |
| Error 401 (HTTP o HTML AEAT) | Certificado caducado o no autorizado | Renovar P12; revisar censo AEAT del entorno (preprod/prod) |
| «Certificado AEAT caducó el…» al presentar import | Validación previa del módulo | Renovar certificado antes de pulsar Presentar |
| Página HTML en lugar de XML SOAP | AEAT rechaza autenticación | Mismo tratamiento que 401/403; revisar adjunto `_response.xml` |
| Rechazo funcional (cas. xxx) | EORI, partida, partner, N380 | Corregir según incidencia |
| Validación N380 al generar/presentar | Factura sin Nº comercial ni valor en cabecera | Rellenar **Nº factura (N380)** en la factura o en el expediente |
| 9007 / 1092 (preprod) | Partner no en censo pruebas | Alta en entorno preproducción AEAT |

---

## 8. Integraciones y automatización

| Función | Uso Traldis |
|---------|-------------|
| Subir facturas (wizard) | Crear expedientes (1 PDF = 1 expediente) o añadir PDFs a uno existente |
| Import MSoft | Carga desde sistema origen (si configurado) |
| Documentos requeridos TARIC | Certificados según partida (consulta API UE) |

### 8.1 Seguimiento post-MRN: manual vs cron

**Por defecto** el seguimiento tras el MRN es **manual**: el operador pulsa **Consultar estado** y/o **Consultar Bandeja AEAT** cuando corresponda.

| Tarea | Manual | Cron en el módulo |
|-------|--------|-------------------|
| Consultar estado (CCAESC / ConsultaImportacionV3) | Botones en expediente | **No desarrollado** |
| Bandeja AEAT (levante, salida, mensajes) | Botón bandeja | **Sí** — ver abajo |
| Notificar llegada salida (CC507C, export) | Botón en expediente | **No** (requiere acción en el momento del transporte) |

### 8.2 Cron de bandeja AEAT (opcional)

- **Nombre en Odoo:** «Aduanas (Unificado): Consultar Bandeja AEAT»
- **Ubicación:** Ajustes → Técnico → Automatización → Acciones planificadas
- **Estado por defecto:** **desactivado** (`active = False` al instalar)
- **Frecuencia:** cada **3 minutos** (configurable)
- **Alcance:** hasta **50 expedientes** en estados `predeclared`, `presented`, `accepted` o `released`; ejecuta la misma lógica que el botón manual (`action_poll_bandeja`). Export usa bandeja EXPORAES; import IMPORAES.
- **Activación:** marcar **Activo** en la acción planificada. Requiere certificado AEAT válido en el servidor.
- **Nota:** si una consulta de bandeja falla de forma grave, el expediente puede pasar a **Error**; conviene monitorizar incidencias tras activar el cron en producción.

### 8.3 Otros crons del módulo

| Cron | Activo por defecto | Función |
|------|-------------------|---------|
| Procesar facturas PDF en cola (expedientes) | Sí | Procesa OCR en background |
| Procesar facturas pendientes (carga masiva) | No | Cola alternativa de facturas |
| Consultar Bandeja AEAT | No | Seguimiento post-MRN automático |

### 8.4 Cierre del expediente (estado «Cerrado»)

| Modo | Exportación | Importación |
|------|-------------|-------------|
| **Manual** | Botón **Cerrar expediente** cuando el estado es *Salida efectiva* | Botón **Cerrar expediente** cuando el estado es *Aceptado* (MRN) |
| **Automático** | **Activado por defecto:** al confirmar salida efectiva AEAT (bandeja/CCAESC) → *Cerrado* | **Desactivado por defecto:** opcional al admitir CC415A → *Cerrado* |

Configuración en **Aduanas → Configuración → Cierre de expedientes**:

- *Cerrar export al confirmar salida efectiva*
- *Cerrar import al admitir MRN*

No se cierra si hay **incidencias pendientes**. El estado sigue siendo de solo lectura en formulario; el cierre se hace con el botón o la automatización.
