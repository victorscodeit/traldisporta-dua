# Flujo exportación España → Andorra (Guía WEB Exp / AES)

Este documento describe cómo un usuario de Odoo ejecuta el ciclo completo de un DUA de exportación con el módulo `aduanas_transport`, alineado con la [Guía WEB Exp](GuiaWEBExp.pdf) de la AEAT.

## Requisitos previos

1. **Certificado electrónico** de la empresa declarante (agente de aduanas) en Aduanas → Configuración. Ver `CONFIGURAR_CERTIFICADO_AEAT.md`.
2. **Endpoints** en preproducción o producción (`aeat_endpoint_cc515c`, `ccaesc`, `cc507c`, bandeja).
3. Expediente con **dirección = Exportación**, líneas de mercancía, remitente (exportador, p. ej. Dorel), consignatario (Andorra), oficina de exportación/salida.
4. **Representación aduanera**: campo `tipo_representacion` en el expediente (`indirecta` por defecto: declarante = empresa Odoo, exportador = remitente).

## Mapa Guía AEAT ↔ Odoo

| Paso | Mensaje Guía | Servicio AEAT | Botón Odoo | Qué obtiene |
|------|----------------|---------------|------------|-------------|
| 1 | Alta DUA exportación | **CC515C** → `POST …/CC515CV1SOAP` | **Presentar DUA a AEAT** | MRN, admisión o errores funcionales/XML |
| 2 | Consulta estado | **CCAESC** (consulta exportación por MRN) | **Consultar Estado DUA** | `aes_estado`, circuito, CSV, fechas, errores |
| 3 | Llegada aduana salida (IE507) | **CC507C** | **Notificar Llegada Salida** | Confirmación llegada en aduana de salida |
| 4 | Salida efectiva UE (IE599) | **Bandeja** (`ComunicaResulSalida`, tipo `CSALID`) | **Consultar Bandeja AEAT** | Salida efectiva, IVA exento |

> En la guía aparecen códigos IE507/IE599; en el canal web AES los equivalentes operativos son **CC507C** y mensajes de **bandeja** (`CLEVEX`, `CSALID`, etc.).

## Procedimiento en Odoo

### 1. Preparar expediente

1. Crear expediente **Exportación**.
2. Subir factura (**Procesar Factura PDF**) o rellenar líneas manualmente.
3. Opcional: **Verificación IA** de partidas.
4. **Generar DUA** (PDF/informe interno y validación de datos).

### 2. Presentar DUA (CC515C)

1. Pulsar **Presentar DUA a AEAT**.
2. Se adjuntan `DUA_CC515C_soap.xml` y la respuesta AEAT.
3. Si la AEAT admite la declaración: se guarda el **MRN**, estado **Aceptado**, campos AES (`aes_estado`, `aes_circuito`, CSV si vienen en respuesta).
4. Si rechaza (`tipoRespuesta` **EF** funcional o **EX** XML): estado **Error**, mensaje en `error_message` e **incidencias** enlazadas al expediente.

Corrija incidencias (EORI en censo, consignatario, incoterms, documentos N380, etc.) y vuelva a presentar.

### 3. Consultar estado (CCAESC)

Con MRN asignado:

1. **Consultar Estado DUA** → llamada CCAESC.
2. Actualiza panel AES: estado, circuito de llegada, fechas de levante/salida si la AEAT las comunica.

Use este paso cuando necesite comprobar **aceptado / circuito / errores** sin esperar solo a la bandeja.

### 4. Notificar llegada en aduana de salida (CC507C / IE507)

Cuando la mercancía esté físicamente en la aduana de salida:

1. **Notificar Llegada Salida**.
2. Requiere MRN, oficina de salida y datos de transportista configurados en el expediente/empresa.

### 5. Salida efectiva e IVA exento (bandeja / IE599)

1. **Consultar Bandeja AEAT** (también puede ejecutarse por cron si está activo).
2. Procesa mensajes `CLEVEX` (levante exportación), `CSALID` / salida efectiva, etc.
3. Al confirmar **salida efectiva**: estado **Salida efectiva**, `iva_exportacion_exento = True`, `fecha_salida_real` rellenada.

Esto cubre el requisito fiscal de acreditar que la mercancía **salió de la UE**.

## Estados del expediente

`draft` → `predeclared` → `presented` → **`accepted`** (MRN) → **`released`** (levante) → **`exited`** (salida UE / IVA exento) → `closed`

## Campos útiles en formulario

- **MRN**, **Estado AES**, **Circuito AES**
- **IVA exportación exento** (automático tras salida efectiva)
- Fechas: admisión, llegada salida, levante, salida real
- Adjuntos XML de cada petición/respuesta

## Preproducción vs producción

Por defecto los endpoints apuntan a **prewww1.aeat.es**. En preprod los EORI y consignatarios deben estar dados de alta en el censo de pruebas AEAT; errores 9007/1092 suelen ser de datos, no del módulo.

## Referencia técnica

- Modelo: `aduana.expediente` — `action_send_cc515c`, `action_consultar_estado_dua`, `action_notificar_llegada_salida`, `action_poll_bandeja`
- Parser: `aduanas.xml.parser` — `parse_aes_export_response`, `parse_bandeja_response`
- Cliente HTTPS: `aduanas.aeat.client` con certificado P12
