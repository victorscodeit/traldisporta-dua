# Resumen de Campos Agregados y Sistema de Importación

## ✅ Campos Agregados al Modelo `aduana.expediente`

### 1. **Campos de Trazabilidad MSoft** (CRÍTICO para importación)

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `msoft_codigo` | Char (indexed) | Código original MSoft | `ExpCod` |
| `msoft_recepcion_num` | Integer | Número recepción MSoft | `ExpRecNum` |
| `msoft_fecha_recepcion` | Datetime | Fecha recepción MSoft | `ExpDatRec` |
| `msoft_fecha_modificacion` | Datetime (indexed) | Última modificación MSoft | `ExpModFec` |
| `msoft_usuario_modificacion` | Char | Usuario modificación MSoft | `ExpModUsu` |
| `msoft_usuario_creacion` | Char | Usuario creación MSoft | `ExpAltUsu` |
| `msoft_fecha_creacion` | Datetime | Fecha creación MSoft | `ExpAltFec` |
| `msoft_estado_original` | Integer | Estado original MSoft | `ExpSit` |
| `msoft_sincronizado` | Boolean | Si está sincronizado | - |
| `msoft_ultima_sincronizacion` | Datetime | Última sincronización | - |

**Uso:** Identificar expedientes ya importados, sincronización incremental, debugging.

---

### 2. **Campos de Fechas Adicionales**

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `fecha_levante` | Datetime | Fecha levante aduanero | `ExpDatLev` |
| `fecha_recepcion` | Datetime | Fecha recepción | `ExpDatRec` |

**Uso:** Actualizar estado automáticamente cuando hay levante, reportes.

---

### 3. **Campos de Control y Validación**

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `flag_confirmado` | Boolean | Expediente confirmado | `ExpConf = 'S'` |
| `flag_origen_ok` | Boolean | Origen validado | `ExpOriOk = 'S'` |
| `flag_destino_ok` | Boolean | Destino validado | `ExpDesOk = 'S'` |
| `flag_anulado` | Boolean | Expediente anulado | `ExpFlgAnu = 'S'` |

**Uso:** Validar antes de enviar a AEAT, filtrar anulados, control de calidad.

---

### 4. **Campos de Transporte Adicionales**

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `remolque` | Char | Matrícula remolque | `ExpRemol` |
| `codigo_transporte` | Char | Código transporte | `TraCod` |

**Uso:** Información completa del transporte.

---

### 5. **Campos de Documentación**

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `numero_albaran_remitente` | Char | Albarán remitente | `ExpAlbRem` |
| `numero_albaran_destinatario` | Char | Albarán destinatario | `ExpAlbDes` |
| `codigo_orden` | Char | Código orden | `ExpOrdCod` |
| `descripcion_orden` | Char | Descripción orden | `ExpOrdDes` |
| `referencia_proveedor` | Char | Referencia proveedor | `ExpProRef` |

**Uso:** Referencias comerciales, trazabilidad, búsqueda.

---

### 6. **Campos de Oficina Aduanera**

| Campo | Tipo | Descripción | Origen MSoft |
|-------|------|-------------|--------------|
| `oficina_destino` | Char | Oficina aduanas destino | `ExpDsOfCd` |

**Uso:** Información adicional para reportes.

---

## 🔧 Sistema de Importación Creado

### Archivos Creados:

1. **`aduanas_transport/models/msoft_import.py`**
   - Wizard de importación
   - Métodos de búsqueda/creación de partners
   - Métodos de búsqueda/creación de camiones
   - Mapeo de estados, incoterms, divisas, países
   - Formateo de oficinas aduaneras

2. **`aduanas_transport/wizards/msoft_import_views.xml`**
   - Vista del wizard de importación
   - Menú "Importar desde MSoft"

### Funcionalidades Implementadas:

✅ **Búsqueda/Creación de Partners:**
- Buscar por código (`ref`)
- Buscar por NIF/CIF (`vat`)
- Crear automáticamente si no existe
- Actualizar datos si existe

✅ **Búsqueda/Creación de Camiones:**
- Buscar por matrícula
- Crear automáticamente si no existe

✅ **Mapeo Automático:**
- Estados MSoft → Odoo
- Incoterms MSoft → Códigos ISO
- Divisas MSoft → Códigos ISO
- Países MSoft → Códigos ISO
- Formato de oficinas aduaneras

✅ **Opciones de Importación:**
- Modo completo
- Modo incremental (solo cambios)
- Solo nuevos
- Filtros por fecha
- Opciones de creación/actualización

---

## 📋 Lo que Falta para Completar la Importación

### 1. **Conexión Real a Base de Datos MSoft** ⭐ CRÍTICO

**Falta:**
- Instalar `pyodbc` o `pymssql` para SQL Server
- Implementar conexión real en `_get_msoft_connection()`
- Ejecutar el SQL de `MAPEO_COMPLETO_MSOFT_ODOO.md`

**Código necesario:**
```python
import pyodbc  # o pymssql

def _connect_msoft(self):
    conn_params = self._get_msoft_connection()
    conn = pyodbc.connect(
        f"DSN={conn_params['dsn']};"
        f"DATABASE={conn_params['database']};"
        f"UID={conn_params['user']};"
        f"PWD={conn_params['password']}"
    )
    return conn
```

---

### 2. **Procesamiento de Expedientes** ⭐ CRÍTICO

**Falta implementar en `action_import_expedientes()`:**
```python
def action_import_expedientes(self):
    # 1. Conectar a MSoft
    conn = self._connect_msoft()
    cursor = conn.cursor()
    
    # 2. Ejecutar SQL (de MAPEO_COMPLETO_MSOFT_ODOO.md)
    sql = "SELECT ... FROM [TablaExpedientes] WHERE ..."
    cursor.execute(sql)
    
    # 3. Para cada expediente:
    for row in cursor.fetchall():
        # 3.1. Buscar/crear remitente
        remitente = self._get_or_create_partner(...)
        
        # 3.2. Buscar/crear consignatario
        consignatario = self._get_or_create_partner(...)
        
        # 3.3. Buscar/crear camión
        camion = self._get_or_create_camion(...)
        
        # 3.4. Buscar expediente existente por msoft_codigo
        expediente = self.env["aduana.expediente"].search([
            ("msoft_codigo", "=", row.expediente_code)
        ], limit=1)
        
        # 3.5. Crear o actualizar expediente
        if expediente:
            # Actualizar
            expediente.write({...})
        else:
            # Crear nuevo
            expediente = self.env["aduana.expediente"].create({...})
        
        # 3.6. Importar líneas de mercancía
        self._import_lineas(expediente, row.expediente_code)
    
    # 4. Cerrar conexión
    conn.close()
```

---

### 3. **Importación de Líneas de Mercancía** ⭐ CRÍTICO

**Falta:**
```python
def _import_lineas(self, expediente, exp_codigo):
    # 1. Conectar y leer líneas
    # 2. Eliminar líneas existentes (opcional)
    # 3. Crear nuevas líneas
    for linea_data in lineas_msoft:
        self.env["aduana.expediente.line"].create({
            "expediente_id": expediente.id,
            "item_number": linea_data.item_number,
            "partida": linea_data.partida_arancelaria,
            "descripcion": linea_data.descripcion,
            "peso_bruto": linea_data.peso_bruto,
            "peso_neto": linea_data.peso_neto,
            "unidades": linea_data.unidades,
            "bultos": linea_data.bultos,
            "valor_linea": linea_data.valor_linea,
            "pais_origen": linea_data.pais_origen,
        })
```

---

### 4. **Validación de Datos** ⭐ ALTA PRIORIDAD

**Falta:**
- Validar campos obligatorios antes de crear
- Validar formato de oficinas (4 dígitos)
- Validar formato de partidas (10 dígitos)
- Validar NIFs/CIFs
- Reporte de errores

**Implementar:**
```python
def _validate_expediente(self, datos):
    errors = []
    if not datos.get('remitente'):
        errors.append("Remitente obligatorio")
    if not datos.get('oficina') or len(datos['oficina']) != 4:
        errors.append("Oficina aduanera debe tener 4 dígitos")
    # ... más validaciones
    return errors
```

---

### 5. **Manejo de Duplicados** ⭐ ALTA PRIORIDAD

**Falta:**
- Lógica para decidir qué hacer si existe expediente:
  - ¿Actualizar siempre?
  - ¿Solo si MSoft es más reciente?
  - ¿Mantener datos de Odoo si fueron modificados?

**Implementar:**
```python
def _should_update(self, expediente_odoo, datos_msoft):
    # Comparar fechas de modificación
    if datos_msoft['msoft_fecha_modificacion'] > expediente_odoo.msoft_fecha_modificacion:
        return True
    return False
```

---

### 6. **Reporte de Importación** ⭐ MEDIA PRIORIDAD

**Falta:**
- Resumen de importación
- Lista de errores
- Expedientes omitidos y razón

**Ya está parcialmente implementado** en `resultado_importacion`, solo falta completar con datos reales.

---

## 🎯 Resumen de lo Implementado vs. lo que Falta

### ✅ Implementado:
1. ✅ Campos de trazabilidad MSoft
2. ✅ Campos de fechas adicionales
3. ✅ Campos de control y validación
4. ✅ Campos de transporte adicionales
5. ✅ Campos de documentación
6. ✅ Wizard de importación (estructura)
7. ✅ Métodos de búsqueda/creación de partners
8. ✅ Métodos de búsqueda/creación de camiones
9. ✅ Mapeo de estados, incoterms, divisas, países
10. ✅ Vistas actualizadas con nuevos campos

### ⚠️ Falta Implementar:
1. ⚠️ Conexión real a base de datos MSoft (pyodbc/pymssql)
2. ⚠️ Procesamiento completo de expedientes
3. ⚠️ Importación de líneas de mercancía
4. ⚠️ Validación de datos antes de crear
5. ⚠️ Manejo de duplicados y conflictos
6. ⚠️ Reporte completo de importación

---

## 📝 Próximos Pasos Recomendados

1. **Instalar dependencias:**
   ```bash
   pip install pyodbc  # o pymssql
   ```

2. **Actualizar `__manifest__.py`:**
   ```python
   "external_dependencies": {
       "python": ["requests", "pyodbc"],  # o pymssql
   },
   ```

3. **Completar `action_import_expedientes()`** con el código de procesamiento real

4. **Probar con un subconjunto pequeño** de datos primero

5. **Implementar validaciones** antes de crear registros

6. **Añadir manejo de errores** robusto

