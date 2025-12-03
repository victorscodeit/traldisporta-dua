# Guía de Uso: Procesamiento de Facturas PDF con IA/OCR

## ✅ Paso 1: Reiniciar Odoo (si no lo has hecho)

```bash
docker restart odoo-traldisdua
```

Espera unos segundos a que Odoo se inicie completamente.

## ✅ Paso 2: Actualizar el Módulo (si es necesario)

1. Entra a Odoo como administrador
2. Ve a **Aplicaciones**
3. Activa el modo desarrollador (si no está activo):
   - Clic en tu nombre (arriba derecha) → **Activar modo desarrollador**
4. Busca el módulo **"Aduanas Transporte España ↔ Andorra (Unificado)"**
5. Si hay un botón **"Actualizar"**, haz clic en él
6. Si no aparece, el módulo ya está actualizado

## ✅ Paso 3: Configurar (Opcional)

### Configurar Google Vision (Opcional - No necesario)

Si quieres usar Google Vision API (solo si tienes PDFs escaneados):

1. Ve a **Configuración** → **Aduanas**
2. En la sección **"Procesamiento de Facturas PDF (IA/OCR)"**
3. Ingresa la ruta al archivo JSON de Google Vision o déjalo vacío
4. Guarda

**Nota:** Si no configuras Google Vision, el sistema usará automáticamente PyPDF2/pdfplumber, que funciona perfectamente para facturas normales.

## ✅ Paso 4: Probar la Funcionalidad

### Crear una Expedición y Subir Factura

1. Ve a **Aduanas** → **Expedientes**
2. Clic en **Crear**
3. Completa los campos básicos:
   - **Referencia**: (se genera automáticamente)
   - **Sentido**: Export o Import
   - Otros campos básicos
4. Ve a la pestaña **"Factura PDF"**
5. Clic en **"Seleccionar archivo"** y sube una factura PDF
6. Guarda el expediente

### Procesar la Factura

Tienes dos opciones:

#### Opción A: Solo Procesar Factura (Extraer Datos)

1. Con la factura subida, haz clic en el botón **"Procesar Factura PDF"** (en el header)
2. El sistema extraerá:
   - Número de factura
   - Fecha
   - Remitente (buscará o creará automáticamente)
   - Consignatario (buscará o creará automáticamente)
   - Valor total y moneda
   - Incoterm (si está en la factura)
   - Países
3. Los datos se rellenarán automáticamente en la expedición
4. Puedes revisar los datos extraídos en la pestaña **"Factura PDF"** → **"Datos Extraídos de Factura"**

#### Opción B: Procesar y Generar DUA Automáticamente

1. Con la factura subida, haz clic en **"Procesar Factura y Generar DUA"** (en el header)
2. El sistema:
   - Extraerá los datos de la factura
   - Rellenará la expedición
   - Generará automáticamente el DUA (CC515C para exportación o IMP_DECL para importación)
3. El DUA se generará y podrás previsualizarlo o descargarlo

## ✅ Paso 5: Verificar Resultados

### Revisar Datos Extraídos

1. Ve a la pestaña **"Factura PDF"**
2. Verifica que **"Factura Procesada"** esté marcado
3. Revisa el campo **"Datos Extraídos de Factura"** para ver qué se extrajo
4. Verifica que los campos de la expedición se hayan rellenado:
   - Remitente
   - Consignatario
   - Valor de factura
   - Moneda
   - Incoterm (si estaba en la factura)

### Revisar Partners Creados

1. Ve a **Contactos**
2. Busca el remitente y consignatario extraídos
3. Si no existían, se habrán creado automáticamente

### Revisar DUA Generado

1. Si usaste "Procesar Factura y Generar DUA", ve a la pestaña **"Chatter"**
2. Busca el mensaje de confirmación
3. Usa los botones de previsualización o descarga del DUA en el header

## 🔍 Solución de Problemas

### La factura no se procesa

1. Verifica que el PDF tenga texto (no solo imágenes escaneadas)
2. Revisa los logs de Odoo:
   ```bash
   docker logs odoo-traldisdua --tail 100
   ```
3. Verifica que PyPDF2/pdfplumber esté instalado:
   ```bash
   docker exec -it odoo-traldisdua python3 -c "import PyPDF2; print('OK')"
   ```

### Los datos no se extraen correctamente

- El OCR no es perfecto, especialmente con facturas mal escaneadas
- Puedes completar manualmente los campos que falten
- Los datos extraídos se guardan en JSON para revisión

### El DUA no se genera

- Verifica que todos los campos obligatorios estén completos:
  - Remitente
  - Consignatario
  - Líneas de mercancía (si son necesarias)
- Revisa los mensajes de error en el chatter

## 📝 Notas Importantes

1. **El OCR no es 100% preciso**: Siempre revisa los datos extraídos
2. **Facturas escaneadas**: Para PDFs escaneados (imágenes), considera usar Google Vision
3. **Líneas de productos**: Actualmente se extraen datos básicos. Las líneas de productos pueden requerir ajuste manual
4. **Partners**: Se crean automáticamente si no existen, basándose en NIF o nombre

## 🎯 Próximos Pasos

Una vez que funcione:

1. Prueba con diferentes tipos de facturas
2. Ajusta los patrones de extracción si es necesario (en `invoice_ocr_service.py`)
3. Considera configurar Google Vision si trabajas con PDFs escaneados
4. Personaliza los campos que se extraen según tus necesidades

