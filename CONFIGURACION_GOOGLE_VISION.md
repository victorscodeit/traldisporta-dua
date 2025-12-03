# Configuración de Google Cloud Vision API

## 📋 Opciones de Configuración

Google Cloud Vision API puede configurarse de dos formas:

### Opción 1: Service Account JSON (Recomendado)

Esta es la forma más segura y recomendada para producción.

#### Paso 1: Crear Service Account en Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Selecciona o crea un proyecto
3. Ve a **IAM & Admin** → **Service Accounts**
4. Clic en **Create Service Account**
5. Completa el formulario y crea la cuenta
6. En la cuenta creada, ve a **Keys** → **Add Key** → **Create new key**
7. Selecciona **JSON** y descarga el archivo

#### Paso 2: Configurar en Odoo

**Método A: Ruta al archivo JSON (Recomendado)**

1. Sube el archivo JSON al servidor de Odoo (ej: `/opt/odoo/config/google-vision-credentials.json`)
2. Asegúrate de que Odoo tenga permisos de lectura
3. En Odoo: **Configuración → Aduanas → Google Vision Credenciales**
4. Ingresa la ruta completa: `/opt/odoo/config/google-vision-credentials.json`

**Método B: Contenido JSON como texto**

1. Abre el archivo JSON descargado
2. Copia todo el contenido
3. En Odoo: **Configuración → Aduanas → Google Vision Credenciales**
4. Pega el contenido JSON completo

#### Paso 3: Habilitar la API

1. En Google Cloud Console, ve a **APIs & Services** → **Library**
2. Busca "Cloud Vision API"
3. Clic en **Enable**

#### Paso 4: Configurar facturación

Google Vision API requiere facturación habilitada (tiene un tier gratuito generoso).

### Opción 2: Variable de Entorno (Alternativa)

Si prefieres usar variable de entorno en lugar de configuración en Odoo:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
```

Luego reinicia Odoo.

## 🔐 Permisos Necesarios

El Service Account necesita el rol:
- **Cloud Vision API User** o
- **Cloud Vision API Client**

## 💰 Costos

Google Cloud Vision API tiene:
- **Tier gratuito**: 1,000 unidades/mes
- **Después**: $1.50 por 1,000 unidades

Cada página de PDF procesada cuenta como 1 unidad.

## ✅ Verificación

Después de configurar:

1. Reinicia Odoo
2. Crea una expedición
3. Sube una factura PDF
4. Haz clic en "Procesar Factura PDF"
5. Revisa los logs de Odoo para ver si usa Google Vision o OCR alternativo

## 🆘 Solución de Problemas

### Error: "Permission denied"
- Verifica que el archivo JSON tenga permisos de lectura
- Verifica que la ruta sea correcta

### Error: "Invalid credentials"
- Verifica que el archivo JSON sea válido
- Verifica que la API esté habilitada en Google Cloud
- Verifica que el Service Account tenga los permisos correctos

### Error: "Billing not enabled"
- Habilita facturación en Google Cloud Console

### El sistema sigue usando OCR alternativo
- Verifica que la ruta o contenido JSON sea correcto
- Revisa los logs de Odoo para ver el error específico
- Verifica que `google-cloud-vision` esté instalado: `pip install google-cloud-vision`

## 📝 Nota Importante

**No necesitas Google Vision para usar el sistema.** El OCR alternativo (pdfplumber) funciona perfectamente para la mayoría de facturas PDF con texto. Google Vision es útil principalmente para:
- PDFs escaneados (imágenes)
- Mayor precisión en OCR
- Procesamiento de documentos complejos

Para facturas normales con texto, **pdfplumber es suficiente y más fácil de configurar**.

