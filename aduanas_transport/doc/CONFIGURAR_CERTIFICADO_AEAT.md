# Cómo configurar el certificado electrónico de la AEAT

Para que **Presentar DUA a AEAT** (y el resto de servicios AEAT) no devuelva **403 Forbidden**, el servidor debe autenticarse con el **certificado electrónico** que te haya facilitado la AEAT.

## 1. Obtener el certificado

- Debe ser un archivo **.p12** o **.pfx** (PKCS#12) emitido o aceptado por la AEAT para el entorno que uses (preproducción o producción).
- Necesitas también la **contraseña** del archivo.

## 2. Subir el certificado en Odoo

1. Vaya a **Aplicaciones** (o **Ajustes**) y abra el módulo **Aduanas**.
2. Entre en **Configuración** (menú Aduanas > Configuración o el enlace de configuración del módulo).
3. En la sección **Certificado electrónico AEAT**:
   - **Subir certificado .p12/.pfx**: haga clic en “Subir” o “Seleccionar archivo” y elija su archivo .p12 o .pfx de la AEAT.
   - **Contraseña del certificado**: escriba la contraseña del archivo .p12.
4. Guarde los cambios con **Aplicar** (o **Guardar**). El certificado quedará guardado y se usará en las siguientes peticiones a la AEAT.

## 3. Dependencias (ya cubiertas en Odoo 16)

El módulo convierte el P12 a PEM usando **cryptography** (incluido en Odoo 16, p. ej. 3.4.8) y envía la petición con **requests** estándar. No hace falta instalar `requests-pkcs12` ni actualizar `cryptography`.

## 4. Comprobar

1. Abra un expediente de **exportación**.
2. Genere el DUA y pulse **Presentar DUA a AEAT**.
3. Si el certificado y la contraseña son correctos y la librería está instalada, la petición debería dejar de devolver 403 y podrá recibir la respuesta XML de la AEAT.

## Notas

- El certificado y la contraseña se guardan en la configuración de Odoo; el archivo P12 se almacena como adjunto. Restrinja el acceso a la configuración y a los adjuntos según su política de seguridad.
- Si sigue apareciendo 403, compruebe que el certificado sea válido para la URL que esté usando (preproducción: `prewww1.aeat.es`, producción: `www1.agenciatributaria.gob.es`) y que el NIF/CIF del certificado sea el autorizado para ese servicio.
