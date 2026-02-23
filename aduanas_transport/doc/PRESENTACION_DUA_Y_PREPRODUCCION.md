# Presentación del DUA y uso en preproducción

Este documento resume los pasos de presentación del DUA en el módulo y cómo usar el entorno de **preproducción** de la AEAT. Para el procedimiento oficial detallado y requisitos de la AEAT, consultar el **GT_EXS.pdf** (Guía Técnica Exportación).

---

## 1. Flujo de estados del expediente (exportación)

1. **Borrador (draft)**  
   Expediente completo: facturas, líneas, documentos, totales.

2. **Generar DUA**  
   Acción: *Generar DUA* (CC515C / CUSDEC EX1).  
   Genera el XML de la declaración y el estado pasa a **Predeclarado**.

3. **Enviar DUA a AEAT**  
   Acción: *Enviar DUA*.  
   Envía el XML al endpoint configurado. Si la AEAT acepta y devuelve MRN → estado **Aceptado (MRN)**.

4. **Presentar CC511C**  
   Acción: *Presentar CC511C* (solo cuando ya existe MRN).  
   Envía el mensaje CC511C. Si es correcto → estado **Presentado**.

5. **Bandeja / Levante**  
   Consultar bandeja AEAT y, cuando corresponda, estado **Levante** / **Cerrado**.

---

## 2. Preproducción AEAT

Por defecto el módulo usa **entorno de preproducción** de la AEAT (`prewww1.agenciatributaria.gob.es`).

### Endpoints por defecto (preproducción)

| Servicio        | Uso              | URL por defecto |
|-----------------|------------------|------------------------------------------|
| **CC515C**      | Envío DUA Export | `https://prewww1.agenciatributaria.gob.es/wlpl/ADEX-JDIT/ws/aes/CC515CV1SOAP` |
| **CC511C**      | Presentación     | `https://prewww1.agenciatributaria.gob.es/wlpl/ADEX-JDIT/ws/aes/CC511CV1SOAP` |
| **Declaración Import** | Importación | `https://prewww1.agenciatributaria.gob.es/wlpl/ADIM-JDIT/ws/imp/DeclaracionSOAP` |
| **Bandeja**     | Consulta bandeja | `https://prewww1.agenciatributaria.gob.es/wlpl/ADHT-BAND/ws/det/DetalleV5SOAP` |

### Dónde configurar

- **Aduanas → Configuración** (o **Ajustes → Aduanas** según menú).
- Sección **Endpoints AEAT**: se pueden cambiar las URLs para preproducción o producción.
- Para **producción**, sustituir el host por el que indique la AEAT (normalmente sin el prefijo `pre` en el dominio).

### Certificado

- En la misma configuración: **Certificado Digital** (archivo P12/PFX y contraseña).
- En preproducción suele usarse un certificado de pruebas facilitado por la AEAT.

---

## 3. Resumen de acciones en el expediente

| Paso        | Acción en Odoo      | Estado resultante |
|------------|---------------------|-------------------|
| Expediente listo | —               | Borrador          |
| Generar declaración | Generar DUA / Generar declaración import | Predeclarado |
| Enviar a AEAT | Enviar DUA / Enviar declaración | Aceptado (si hay MRN) |
| Presentar (export) | Presentar CC511C | Presentado        |
| Consultar bandeja | Consultar bandeja | (actualiza levante, etc.) |

---

## 4. Referencia externa

- **GT_EXS.pdf**: guía técnica con el detalle de los mensajes, preproducción y requisitos oficiales de presentación del DUA.  
  Conservar este PDF en el proyecto como referencia para cumplimiento y pruebas en preproducción.
