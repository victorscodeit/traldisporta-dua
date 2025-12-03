# Instalación de Dependencias en Docker

## 🐳 Para Instalación con Docker

Si tu Odoo está en Docker (montado en `/mnt/docker/config/traldisdua#`), sigue estos pasos:

## 📋 Paso 1: Encontrar el contenedor de Docker

```bash
# Listar contenedores de Docker
docker ps

# O buscar contenedores con "odoo" en el nombre
docker ps | grep odoo
```

Anota el **nombre o ID del contenedor** (ejemplo: `odoo`, `odoo-web`, `traldisdua-odoo-1`, etc.)

## 📋 Paso 2: Entrar al contenedor

```bash
# Reemplaza CONTAINER_NAME con el nombre de tu contenedor
docker exec -it CONTAINER_NAME bash

# Si no tienes bash, prueba con sh
docker exec -it CONTAINER_NAME sh
```

**Ejemplo:**
```bash
docker exec -it odoo bash
# o
docker exec -it traldisdua-odoo-1 bash
```

## 📋 Paso 3: Instalar dependencias dentro del contenedor

Una vez dentro del contenedor:

```bash
# Opción A: Instalar pdfplumber (Recomendado)
pip install pdfplumber

# Opción B: Instalar desde requirements.txt (si está en el módulo)
cd /mnt/extra-addons/aduanas_transport  # Ajusta la ruta según tu configuración
pip install -r requirements.txt

# Opción C: Instalar Google Vision (Opcional)
pip install google-cloud-vision
```

## 📋 Paso 4: Reiniciar el contenedor

```bash
# Salir del contenedor
exit

# Reiniciar el contenedor
docker restart CONTAINER_NAME
```

## 🔄 Alternativa: Agregar al Dockerfile (Persistente)

Si quieres que las dependencias se instalen automáticamente al reconstruir la imagen:

### Opción 1: Modificar Dockerfile existente

Si tienes un Dockerfile, agrega:

```dockerfile
RUN pip install pdfplumber
# o
RUN pip install -r /mnt/extra-addons/aduanas_transport/requirements.txt
```

### Opción 2: Usar docker-compose con volumen de requirements

Si usas docker-compose, puedes agregar:

```yaml
services:
  odoo:
    # ... otras configuraciones
    command: >
      bash -c "pip install pdfplumber && odoo"
```

## 🎯 Verificación

Después de instalar, verifica que funciona:

```bash
# Dentro del contenedor
python3 -c "import pdfplumber; print('pdfplumber instalado correctamente')"
```

## 📝 Notas Importantes

1. **Las dependencias se instalan en el contenedor**, no en el host
2. Si reconstruyes la imagen, necesitarás reinstalar las dependencias
3. Para hacerlo persistente, modifica el Dockerfile o docker-compose.yml
4. **pdfplumber es suficiente** para la mayoría de casos, no necesitas Google Vision a menos que tengas PDFs escaneados

## 🆘 Solución de Problemas

### Error: "docker: command not found"
- Asegúrate de tener Docker instalado
- Puede que necesites usar `sudo docker` en algunos sistemas

### Error: "Cannot connect to the Docker daemon"
- Verifica que Docker esté corriendo: `sudo systemctl status docker`
- Puede que necesites permisos: `sudo usermod -aG docker $USER` (luego reinicia sesión)

### Error: "No such container"
- Verifica el nombre del contenedor con `docker ps`
- Usa el ID del contenedor en lugar del nombre

### Las dependencias se pierden al reiniciar
- Esto es normal si no están en el Dockerfile
- Considera agregarlas al Dockerfile para persistencia
- O crea un script de inicio que las instale automáticamente

## 🚀 Comando Rápido (Todo en uno)

```bash
# Reemplaza CONTAINER_NAME con tu contenedor
CONTAINER_NAME="odoo"  # Cambia esto

docker exec -it $CONTAINER_NAME pip install pdfplumber
docker restart $CONTAINER_NAME
```

