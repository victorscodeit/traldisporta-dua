# Resumen: Presentación DUA (EXS) y pruebas en preproducción

Basado en la **Guía técnica de declaraciones EXS, notificaciones Reexportación y Reexpedición** (GT_EXS) versión 5.3.

---

## 1. Pasos del procedimiento de presentación del DUA

### 1.1 Flujo general

1. **Envío del mensaje**  
   El operador envía a la AEAT (vía telemática) una de estas declaraciones/notificaciones:
   - **EXS (A1/A2)**: Declaración Sumaria de Salida
   - **A3**: Notificación de Reexportación
   - **NR**: Notificación de Reexpedición  

   La presentación se hace mediante **Servicios Web** y mensajes **XML** (adaptación del mensaje **IE615**).

2. **Contenido del mensaje de petición (IE615)**  
   - Información de la mercancía (cabecera, partidas, contenedores, precintos, etc.)
   - Itinerario por países
   - Datos del Declarante, Expedidor y Destinatario

3. **Validación en la AEAT**  
   La AEAT valida de forma automática:
   - Formato XML
   - Reglas y condiciones de negocio de la guía
   - Otras validaciones funcionales aduaneras

4. **Respuesta según el resultado**
   - **IE919**: error de formato XML → no reenviar sin corregir.
   - **IE616**: rechazo funcional (código de error indicado).
   - **IE628**: aceptación → se devuelve:
     - Circuito aduanero (salvo PreEXS, que se calcula en la activación)
     - MRN asignado
     - CSV de la declaración
     - CSV de levante y justificante PDF (si hay levante, no es PreEXS, circuito verde y despacho automático)

Todas las respuestas son **síncronas**.

### 1.2 Mensajes implicados

| Código | Nombre     | Descripción                          |
|--------|------------|--------------------------------------|
| IE615  | E_EXS_DAT  | Presentación de A1/A2/A3/NR          |
| IE616  | E_EXS_REJ  | Presentación rechazada               |
| IE628  | E_EXS_ACK  | Presentación aceptada                |
| IE919  | C_XML_NCK  | XML incorrecto                       |

### 1.3 Requisitos técnicos

- **Transporte**: HTTPS.
- **Certificado**: Certificado de usuario admitido por la AEAT (o de sello).
- **Identificador único**: `<MesIdMES19>` debe ser distinto por cada mensaje (y por cada reintento con contenido distinto).
- **Integridad**: Si se reenvía el mismo `<MesSenMES3>` + `<MesIdMES19>` con contenido idéntico, se devuelve la misma respuesta; si el contenido es distinto, se rechaza.
- **Indicador de test**: Valor `1` para pruebas; no enviar en presentación real.

---

## 2. Cómo hacerlo en preproducción

### 2.1 Endpoint y WSDL (preproducción)

- **Endpoint (certificado personal):**  
  `https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP`
- **Endpoint (certificado de sello):**  
  `https://prewww10.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP`
- **WSDL**: El mismo que en producción (en la guía se indica el de producción; en preproducción se usa el endpoint anterior).

### 2.2 Declaraciones marítimas (preproducción)

Usar **recinto 9999** con estos datos:

| Atributo / Campo                         | Valor                                                                 | Observaciones                                      |
|-----------------------------------------|-----------------------------------------------------------------------|----------------------------------------------------|
| Endpoint                                 | `https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP`              | Entorno de pruebas                                 |
| `<MesIdeMES19>`                          | A criterio del usuario                                                | **Distinto** por mensaje (aceptado o rechazado)    |
| `<CusSubPlaHEA66>`                       | `9999AAAAAA`                                                          | Ubicación de la mercancía                          |
| `<PREDOCGODITM1>.<DocTypPD11>`           | `N337`                                                                | Tipo documento previo DDT                          |
| `<PREDOCGODITM1>.<DocRefPD12>`           | Por nº escala: `99992600404` o por MRN: `22ES00999986004042`          | Referencia DSDT                                    |
| `<PREDOCGODITM1>.<DocGdsIteNumPD13>`     | `00001` → verde, `00002` → naranja, `00003` → rojo (o `1`, `2`, `3`)  | Partida DDT → circuito                             |
| `<CUSOFFLON>.<RefNumCOL1>`               | `ES009999`                                                            | Recinto de declaración                             |

### 2.3 Declaraciones aéreas (preproducción)

Usar **recinto 9998** con estos datos:

| Atributo / Campo                         | Valor                                                                 | Observaciones                                      |
|-----------------------------------------|-----------------------------------------------------------------------|----------------------------------------------------|
| Endpoint                                 | `https://prewww1.aeat.es/wlpl/ADRX-JDIT/ws/IE615V5SOAP`              | Entorno de pruebas                                 |
| `<MesIdeMES19>`                          | A criterio del usuario                                                | **Distinto** por mensaje                            |
| `<CusSubPlaHEA66>`                       | `9998AAAAAA`                                                          | Ubicación de la mercancía                          |
| `<PREDOCGODITM1>.<DocTypPD11>`           | `N337`                                                                | Tipo documento previo DDT                          |
| `<PREDOCGODITM1>.<DocRefPD12>`           | Nº escala: `99985000383` o MRN: `25ES00999880003831`; o vuelo+conocimiento con `+`: `20251128PRU00432+CONOPRU00432A` (verde), `...B` (naranja), `...C` (rojo) | Referencia DSDT aérea; tres formas de declarar      |
| `<PREDOCGODITM1>.<DocGdsIteNumPD13>`     | `00001` → verde, `00002` → naranja, `00003` → rojo (o `1`, `2`, `3`)  | Partida DDT → circuito                             |
| `<CUSOFFLON>.<RefNumCOL1>`               | `ES009998`                                                            | Recinto de declaración                             |

**Nota aérea:** Si el destino del itinerario (`<ITI>`) es un Estado miembro UE, en el ejemplo indicado saldrá siempre circuito verde.

### 2.4 Predeclaraciones EXS (PreEXS) – versión 5

- Se pueden presentar EXS con documento previo **N337** (DSDT o G4) cuya mercancía **aún no** esté presentada/activada ante aduana.
- Esas EXS se consideran **PreEXS**.
- La PreEXS se **activa de oficio** cuando se presenta/activa el último DSDT/G4 declarado como documento previo.
- En predeclaración la respuesta devuelve siempre **circuito verde**; el circuito real se calcula en la activación.
- PreEXS no activada en **30 días** desde el alta → anulación de oficio.

---

## 3. Esquemas XML (referencia)

- Petición (altas/modificaciones/anulaciones): `IE615V5Ent.xsd`
- Respuesta aceptación: `IE628V5Sal.xsd`
- Respuesta rechazo funcional: `IE616V5Sal.xsd`
- Respuesta rechazo XML: `IE919V5Sal.xsd`
- Auxiliares: `types_exs_simple_v5.xsd`, `types_exs_complex_v5.xsd`

Las URLs completas están en el apartado 4.4 de la guía (dominio producción; en preproducción se cambia solo el endpoint de envío).

---

## 4. Calendario versión 5 (guía 5.3)

- Pruebas en preproducción: septiembre 2025  
- Pruebas en producción (recintos 999x): octubre 2025  
- Entrada en producción: noviembre 2025  
- Cierre de versión 4: 2º trimestre 2026  

Consultar la sede electrónica de la AEAT y el canal RSS de Novedades de Aduanas para fechas definitivas.

---

*Documento generado a partir de GT_EXS.txt (Guía técnica EXS v5.3).*
