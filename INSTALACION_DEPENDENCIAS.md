# Instalación de Dependencias para Procesamiento de Facturas PDF

## ⚠️ Importante: Entorno de Odoo

Las dependencias Python deben instalarse en el **entorno virtual de Odoo**, no en el sistema operativo.

## 📦 Opción 1: OCR Alternativo (Recomendado - Más Fácil)

Esta opción no requiere configuración adicional y funciona inmediatamente:

```bash
# Activar el entorno virtual de Odoo (ajusta la ruta según tu instalación)
source /opt/odoo/venv/bin/activate
# o
source /usr/bin/odoo-venv/bin/activate
# o si usas odoo.sh
source ~/odoo/venv/bin/activate

# Instalar pdfplumber (recomendado)
pip install pdfplumber

# O instalar PyPDF2 (alternativa)
pip install PyPDF2
```

**Ventajas:**
- ✅ No requiere API keys
- ✅ Funciona offline
- ✅ Fácil de instalar
- ✅ Gratis

**Desventajas:**
- ⚠️ Menos preciso que Google Vision para PDFs escaneados (imágenes)

## 📦 Opción 2: Google Cloud Vision API (Opcional - Más Preciso)

Solo necesario si quieres usar Google Vision para PDFs escaneados o mejor precisión:

### Paso 1: Instalar la librería

```bash
# Activar el entorno virtual de Odoo
source /opt/odoo/venv/bin/activate  # Ajusta según tu instalación

# Instalar google-cloud-vision
pip install google-cloud-vision
```

### Paso 2: Configurar credenciales de Google Cloud

Tienes dos opciones:

#### Opción A: Service Account JSON (Recomendado para producción)

1. Crear un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
2. Habilitar la API de Vision
3. Crear una Service Account y descargar el JSON de credenciales
4. Configurar la variable de entorno:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/ruta/al/archivo/credentials.json"
```

O agregar en el archivo de configuración de Odoo (odoo.conf):

```ini
[options]
google_application_credentials = /ruta/al/archivo/credentials.json
```

#### Opción B: API Key (Más simple, menos seguro)

1. Obtener API Key de Google Cloud Console
2. Configurarla en Odoo: **Configuración → Aduanas → Google Vision API Key**

### Paso 3: Habilitar facturación en Google Cloud

Google Vision API requiere facturación habilitada (tiene un tier gratuito generoso).

## 🔍 Cómo encontrar el entorno virtual de Odoo

Si no sabes dónde está el entorno virtual de Odoo:

```bash
# Buscar el proceso de Odoo
ps aux | grep odoo

# O buscar archivos de configuración
find / -name "odoo.conf" 2>/dev/null

# O buscar el ejecutable
which odoo
```

## ✅ Verificar instalación

Después de instalar, reinicia Odoo y verifica:

```python
# En la consola de Odoo (shell)
import pdfplumber  # Debe funcionar sin error
```

## 🚀 Uso

Una vez instaladas las dependencias:

1. **Sin Google Vision (usando pdfplumber):**
   - No necesitas configurar nada
   - Sube la factura PDF y haz clic en "Procesar Factura PDF"

2. **Con Google Vision:**
   - Configura las credenciales (ver arriba)
   - O configura la API Key en Odoo
   - El sistema usará Google Vision automáticamente si está disponible

## 📝 Notas

- El sistema intenta usar Google Vision primero si está configurado
- Si falla o no está configurado, usa automáticamente pdfplumber/PyPDF2
- No necesitas ambas opciones, con una es suficiente
- Para la mayoría de casos, **pdfplumber es suficiente**

## 🆘 Solución de problemas

### Error: "No module named 'pdfplumber'"
- Asegúrate de estar en el entorno virtual correcto de Odoo
- Verifica que Odoo esté usando ese entorno

### Error: "google-cloud-vision no está instalado"
- Es normal si no lo instalaste
- El sistema usará pdfplumber automáticamente

### Error: "Error al procesar factura con Google Vision"
- Verifica las credenciales
- Asegúrate de que la API esté habilitada en Google Cloud
- Revisa que la facturación esté activa

