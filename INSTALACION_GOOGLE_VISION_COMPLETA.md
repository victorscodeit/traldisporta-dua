# Instalación Completa de Google Vision para PDFs Escaneados

## 🎯 Por qué necesitas Google Vision

- **PyPDF2/pdfplumber**: Solo funciona con PDFs que tienen texto
- **Google Vision**: Hace OCR (reconocimiento de texto) en imágenes escaneadas
- **Tu caso**: PDFs escaneados → Necesitas Google Vision

## 📋 Paso 1: Instalar google-cloud-vision en el contenedor

```bash
# Entrar al contenedor como root
docker exec -it -u root odoo-traldisdua bash

# Instalar google-cloud-vision
pip install google-cloud-vision

# Verificar instalación
python3 -c "from google.cloud import vision; print('✓ Google Vision instalado correctamente')"

# Salir
exit
```

## 📋 Paso 2: Crear cuenta y proyecto en Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea una cuenta o inicia sesión
3. Crea un nuevo proyecto (o selecciona uno existente)
4. Anota el **ID del proyecto**

## 📋 Paso 3: Habilitar la API de Vision

1. En Google Cloud Console, ve a **APIs & Services** → **Library**
2. Busca **"Cloud Vision API"**
3. Haz clic en **Enable** (Habilitar)
4. Espera unos segundos a que se active

## 📋 Paso 4: Crear Service Account y descargar credenciales

1. Ve a **IAM & Admin** → **Service Accounts**
2. Haz clic en **Create Service Account**
3. Completa:
   - **Service account name**: `odoo-vision` (o el que prefieras)
   - **Service account ID**: Se genera automáticamente
   - Haz clic en **Create and Continue**
4. En **Grant this service account access to project**:
   - Selecciona el rol: **Cloud Vision API User**
   - Haz clic en **Continue** → **Done**
5. En la lista de Service Accounts, haz clic en el que acabas de crear
6. Ve a la pestaña **Keys**
7. Haz clic en **Add Key** → **Create new key**
8. Selecciona **JSON**
9. Se descargará un archivo JSON (guárdalo en un lugar seguro)

## 📋 Paso 5: Configurar facturación (Requerido)

1. Ve a **Billing** → **Link a billing account**
2. Agrega un método de pago
3. **Nota**: Google Vision tiene un tier gratuito de 1,000 unidades/mes
   - Cada página de PDF procesada = 1 unidad
   - Después: $1.50 por 1,000 unidades

## 📋 Paso 6: Subir el archivo JSON al servidor

Tienes dos opciones:

### Opción A: Subir el archivo al servidor (Recomendado)

```bash
# Desde tu máquina local, copia el archivo JSON al servidor
scp /ruta/local/credentials.json root@tu-servidor:/mnt/docker/config/google-vision-credentials.json

# O si estás en Windows, usa WinSCP o similar
```

Luego en el servidor:
```bash
# Verificar que el archivo existe
ls -la /mnt/docker/config/google-vision-credentials.json

# Asegurar permisos de lectura
chmod 644 /mnt/docker/config/google-vision-credentials.json
```

### Opción B: Copiar contenido JSON como texto

1. Abre el archivo JSON descargado
2. Copia TODO el contenido
3. Lo pegarás en Odoo (ver paso siguiente)

## 📋 Paso 7: Configurar en Odoo

### Si subiste el archivo al servidor (Opción A):

1. Entra a Odoo como administrador
2. Ve a **Configuración** → **Aduanas**
3. En la sección **"Procesamiento de Facturas PDF (IA/OCR)"**
4. En el campo **"Google Vision Credenciales"**, ingresa la ruta:
   ```
   /mnt/docker/config/google-vision-credentials.json
   ```
5. Guarda

### Si vas a pegar el JSON como texto (Opción B):

1. Entra a Odoo como administrador
2. Ve a **Configuración** → **Aduanas**
3. En la sección **"Procesamiento de Facturas PDF (IA/OCR)"**
4. En el campo **"Google Vision Credenciales"**, pega TODO el contenido del archivo JSON
5. Guarda

## 📋 Paso 8: Reiniciar Odoo

```bash
docker restart odoo-traldisdua
```

## ✅ Paso 9: Probar

1. Crea una expedición en Odoo
2. Sube una factura PDF escaneada
3. Haz clic en **"Procesar Factura PDF"**
4. Verifica que extraiga el texto correctamente

## 🔍 Verificar que funciona

```bash
# Ver logs de Odoo para verificar que usa Google Vision
docker logs odoo-traldisdua --tail 50 | grep -i vision
```

Deberías ver mensajes como:
- "Usando Google Vision con Service Account JSON"
- O si hay errores, los verás aquí

## 🆘 Solución de Problemas

### Error: "Permission denied" al leer el archivo JSON

```bash
# Asegurar permisos
chmod 644 /mnt/docker/config/google-vision-credentials.json
chown odoo:odoo /mnt/docker/config/google-vision-credentials.json
```

### Error: "Invalid credentials"

- Verifica que el archivo JSON sea válido
- Verifica que la API esté habilitada en Google Cloud
- Verifica que el Service Account tenga el rol "Cloud Vision API User"

### Error: "Billing not enabled"

- Debes habilitar facturación en Google Cloud (aunque tengas tier gratuito)

### El sistema sigue usando OCR alternativo

- Verifica que google-cloud-vision esté instalado
- Verifica que la ruta al JSON sea correcta
- Revisa los logs de Odoo para ver el error específico

## 💰 Costos

- **Tier gratuito**: 1,000 unidades/mes (1,000 páginas de PDF)
- **Después**: $1.50 por cada 1,000 unidades adicionales
- **Ejemplo**: 5,000 páginas/mes = $6.00

## 📝 Comandos Rápidos (Resumen)

```bash
# 1. Instalar
docker exec -it -u root odoo-traldisdua pip install google-cloud-vision

# 2. Subir archivo JSON (desde tu máquina)
scp credentials.json root@servidor:/mnt/docker/config/google-vision-credentials.json

# 3. Configurar permisos (en el servidor)
chmod 644 /mnt/docker/config/google-vision-credentials.json

# 4. Reiniciar
docker restart odoo-traldisdua
```

Luego configura la ruta en Odoo: `/mnt/docker/config/google-vision-credentials.json`

