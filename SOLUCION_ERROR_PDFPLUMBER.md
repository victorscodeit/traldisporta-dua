# Solución: Error al instalar pdfplumber

## 🔴 Problema

```
error: invalid-installed-package
× Cannot process installed package pdfminer.six -VERSION- in '/usr/lib/python3/dist-packages' because it has an invalid version:
│ Invalid version: '-VERSION-'
```

## ✅ Solución 1: Desinstalar el paquete problemático (Recomendado)

```bash
# Dentro del contenedor Docker
docker exec -it odoo-traldisdua bash

# Desinstalar el paquete problemático
pip uninstall pdfminer.six -y

# Ahora instalar pdfplumber
pip install pdfplumber
```

## ✅ Solución 2: Forzar reinstalación

```bash
# Dentro del contenedor
pip uninstall pdfminer.six pdfplumber -y
pip install --force-reinstall pdfplumber
```

## ✅ Solución 3: Instalar en el entorno del sistema (si tienes permisos)

```bash
# Dentro del contenedor, como root
docker exec -it -u root odoo-traldisdua bash

# Desinstalar el paquete problemático
pip uninstall pdfminer.six -y

# Instalar pdfplumber
pip install pdfplumber

# O instalar en el entorno del sistema
pip install --system pdfplumber
```

## ✅ Solución 4: Usar PyPDF2 como alternativa

Si pdfplumber sigue dando problemas, puedes usar PyPDF2:

```bash
# Dentro del contenedor
pip uninstall pdfminer.six -y
pip install PyPDF2
```

Luego actualiza el código para usar PyPDF2 por defecto (el código ya lo soporta).

## 🔧 Solución 5: Agregar al Dockerfile (Persistente)

Para hacerlo persistente, agrega al Dockerfile o docker-compose:

```dockerfile
RUN pip uninstall pdfminer.six -y || true
RUN pip install pdfplumber
```

## 📝 Comandos Completos (Copia y Pega)

```bash
# Entrar al contenedor
docker exec -it odoo-traldisdua bash

# Desinstalar paquete problemático
pip uninstall pdfminer.six -y

# Instalar pdfplumber
pip install pdfplumber

# Verificar instalación
python3 -c "import pdfplumber; print('pdfplumber instalado correctamente')"

# Salir
exit

# Reiniciar contenedor
docker restart odoo-traldisdua
```

## 🆘 Si nada funciona

Usa PyPDF2 que es más simple y no tiene esta dependencia:

```bash
docker exec -it odoo-traldisdua bash
pip install PyPDF2
exit
docker restart odoo-traldisdua
```

El código ya soporta PyPDF2 automáticamente como alternativa.

