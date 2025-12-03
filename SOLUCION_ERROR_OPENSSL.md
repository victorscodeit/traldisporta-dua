# Solución: Error OpenSSL en Odoo

## 🔴 Error

```
AttributeError: module 'lib' has no attribute 'X509_V_FLAG_NOTIFY_POLICY'
```

Este es un error de compatibilidad entre `pyOpenSSL` y `cryptography` en el contenedor.

## ✅ Solución: Actualizar librerías

```bash
# Entrar al contenedor como root
docker exec -it -u root odoo-traldisdua bash

# Actualizar pyOpenSSL y cryptography
pip install --upgrade pyOpenSSL cryptography

# O reinstalar
pip uninstall pyOpenSSL cryptography -y
pip install pyOpenSSL cryptography

# Salir
exit

# Reiniciar Odoo
docker restart odoo-traldisdua
```

## ✅ Solución Alternativa: Versiones específicas compatibles

Si la solución anterior no funciona, instala versiones específicas compatibles:

```bash
docker exec -it -u root odoo-traldisdua bash

pip install --upgrade 'cryptography>=3.4.8' 'pyOpenSSL>=20.0.0'

exit
docker restart odoo-traldisdua
```

## ✅ Solución 3: Reinstalar desde cero

```bash
docker exec -it -u root odoo-traldisdua bash

# Desinstalar
pip uninstall pyOpenSSL cryptography -y

# Reinstalar
pip install pyOpenSSL cryptography

exit
docker restart odoo-traldisdua
```

## 🔍 Verificar versión de OpenSSL del sistema

```bash
docker exec -it odoo-traldisdua openssl version
```

## 📝 Nota

Este error es común cuando:
- Se actualizó Odoo pero no las dependencias Python
- Hay conflictos de versiones entre librerías
- El contenedor tiene versiones antiguas de OpenSSL

## 🆘 Si nada funciona

Puede ser necesario reconstruir el contenedor o actualizar la imagen base de Odoo.

