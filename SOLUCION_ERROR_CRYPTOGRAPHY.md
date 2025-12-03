# Solución: Error cryptography.hazmat.backends.openssl.x509

## 🔴 Error

```
ModuleNotFoundError: No module named 'cryptography.hazmat.backends.openssl.x509'
```

Este error indica que hay una incompatibilidad entre las versiones de `cryptography`, `pyOpenSSL` y `urllib3`.

## ✅ Solución Completa

```bash
# 1. Entrar al contenedor como root
docker exec -it -u root odoo-traldisdua bash

# 2. Desinstalar todas las librerías relacionadas
pip uninstall cryptography pyOpenSSL urllib3 -y

# 3. Reinstalar con versiones compatibles
pip install 'cryptography>=3.4.8' 'pyOpenSSL>=20.0.0' 'urllib3>=1.26.0'

# 4. Verificar instalación
python3 -c "from cryptography.hazmat.backends.openssl.x509 import _Certificate; print('OK')"

# 5. Salir
exit

# 6. Reiniciar Odoo
docker restart odoo-traldisdua
```

## ✅ Solución Alternativa: Versiones específicas de Odoo 17

Si la anterior no funciona, prueba con versiones específicas compatibles con Odoo 17:

```bash
docker exec -it -u root odoo-traldisdua bash

# Desinstalar
pip uninstall cryptography pyOpenSSL urllib3 -y

# Instalar versiones específicas compatibles
pip install cryptography==41.0.7 pyOpenSSL==23.3.0 urllib3==2.0.7

exit
docker restart odoo-traldisdua
```

## ✅ Solución 3: Forzar reinstalación completa

```bash
docker exec -it -u root odoo-traldisdua bash

# Limpiar cache de pip
pip cache purge

# Desinstalar todo
pip uninstall cryptography pyOpenSSL urllib3 -y

# Reinstalar desde cero
pip install --no-cache-dir cryptography pyOpenSSL urllib3

exit
docker restart odoo-traldisdua
```

## 🔍 Verificar versiones instaladas

```bash
docker exec -it odoo-traldisdua pip list | grep -E "cryptography|pyOpenSSL|urllib3"
```

Deberías ver algo como:
```
cryptography     41.0.7
pyOpenSSL        23.3.0
urllib3          2.0.7
```

## 📝 Nota sobre Odoo 17

Odoo 17 requiere versiones específicas de estas librerías. Si el contenedor fue creado con versiones antiguas, puede haber conflictos.

## 🆘 Si nada funciona

Puede ser necesario:
1. Actualizar la imagen base de Odoo
2. Reconstruir el contenedor
3. Verificar que estás usando la versión correcta de Python (3.10 o 3.11 para Odoo 17)

