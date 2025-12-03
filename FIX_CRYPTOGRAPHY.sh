#!/bin/bash
# Script para arreglar el error de cryptography en Odoo

echo "=== Solucionando error de cryptography ==="

# Entrar al contenedor y ejecutar comandos
docker exec -it -u root odoo-traldisdua bash << 'EOF'

echo "1. Desinstalando librerías problemáticas..."
pip uninstall cryptography pyOpenSSL urllib3 -y

echo "2. Limpiando cache de pip..."
pip cache purge

echo "3. Reinstalando cryptography con versión compatible..."
pip install --no-cache-dir 'cryptography>=41.0.0'

echo "4. Reinstalando pyOpenSSL..."
pip install --no-cache-dir 'pyOpenSSL>=23.0.0'

echo "5. Reinstalando urllib3..."
pip install --no-cache-dir 'urllib3>=2.0.0'

echo "6. Verificando instalación..."
python3 -c "from cryptography.hazmat.backends.openssl.x509 import _Certificate; print('✓ cryptography OK')" || echo "✗ Error en verificación"

echo "7. Mostrando versiones instaladas..."
pip list | grep -E "cryptography|pyOpenSSL|urllib3"

EOF

echo ""
echo "=== Reiniciando contenedor ==="
docker restart odoo-traldisdua

echo ""
echo "=== Verificando logs (últimas 20 líneas) ==="
sleep 5
docker logs odoo-traldisdua --tail 20

