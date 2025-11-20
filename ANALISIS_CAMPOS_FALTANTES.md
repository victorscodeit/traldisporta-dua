# Análisis de Campos Faltantes y Requisitos de Importación

## 📋 Campos Recomendados para Agregar al Modelo

### 1. **Campos de Trazabilidad y Referencias MSoft** ⭐ ALTA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `msoft_codigo` | Char | Código original MSoft | `ExpCod` | Referencia para sincronización |
| `msoft_recepcion_num` | Integer | Número recepción MSoft | `ExpRecNum` | Identificación única |
| `msoft_fecha_recepcion` | Datetime | Fecha recepción en MSoft | `ExpDatRec` | Trazabilidad |
| `msoft_fecha_modificacion` | Datetime | Última modificación MSoft | `ExpModFec` | Sincronización incremental |
| `msoft_usuario_modificacion` | Char | Usuario que modificó en MSoft | `ExpModUsu` | Auditoría |
| `msoft_sincronizado` | Boolean | Si está sincronizado | - | Control de sincronización |
| `msoft_ultima_sincronizacion` | Datetime | Última sincronización | - | Control de sincronización |

**Razón:** Necesarios para:
- Sincronización bidireccional
- Identificar expedientes ya importados
- Sincronización incremental (solo cambios)
- Resolver conflictos

---

### 2. **Campos de Fechas Adicionales** ⭐ MEDIA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `fecha_levante` | Datetime | Fecha levante aduanero | `ExpDatLev` | Actualizar estado automáticamente |
| `fecha_recepcion` | Datetime | Fecha recepción | `ExpDatRec` | Información adicional |
| `fecha_registro_msoft` | Datetime | Fecha registro en MSoft | `ExpDatReg` | Trazabilidad |

**Razón:** 
- `fecha_levante` puede usarse para actualizar automáticamente el estado a 'released'
- Útiles para reportes y seguimiento

---

### 3. **Campos de Control y Validación** ⭐ MEDIA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `flag_confirmado` | Boolean | Expediente confirmado | `ExpConf = 'S'` | Validación |
| `flag_origen_ok` | Boolean | Origen validado | `ExpOriOk = 'S'` | Validación |
| `flag_destino_ok` | Boolean | Destino validado | `ExpDesOk = 'S'` | Validación |
| `flag_anulado` | Boolean | Expediente anulado | `ExpFlgAnu = 'S'` | **NO importar si True** |

**Razón:**
- Validar expedientes antes de enviar a AEAT
- Filtrar expedientes anulados
- Control de calidad

---

### 4. **Campos de Documentación** ⭐ BAJA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `numero_albaran_remitente` | Char | Albarán remitente | `ExpAlbRem` | Documentación |
| `numero_albaran_destinatario` | Char | Albarán destinatario | `ExpAlbDes` | Documentación |
| `codigo_orden` | Char | Código orden | `ExpOrdCod` | Referencia comercial |
| `descripcion_orden` | Char | Descripción orden | `ExpOrdDes` | Información adicional |
| `referencia_proveedor` | Char | Referencia proveedor | `ExpProRef` | Referencia comercial |

**Razón:**
- Referencias comerciales importantes
- Trazabilidad de documentos
- Búsqueda y filtrado

---

### 5. **Campos de Transporte Adicionales** ⭐ MEDIA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `remolque` | Char | Matrícula remolque | `ExpRemol` | Información transporte |
| `codigo_transporte` | Char | Código transporte | `TraCod` | Referencia |
| `tipo_transporte` | Selection | Tipo transporte | - | Clasificación |

**Razón:**
- Información completa del transporte
- Puede ser requerida por aduanas

---

### 6. **Campos de Oficina Aduanera Detallados** ⭐ BAJA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `oficina_destino` | Char | Oficina aduanas destino | `ExpDsOfCd` | Información adicional |
| `zona_origen` | Char | Zona origen | `ExpOrZoCd` | Clasificación |
| `zona_destino` | Char | Zona destino | `ExpDsZoCd` | Clasificación |

**Razón:**
- Información adicional para reportes
- Puede ser requerida en algunos casos

---

### 7. **Campos de Seguimiento** ⭐ ALTA PRIORIDAD

| Campo Propuesto | Tipo | Descripción | Origen MSoft | Uso |
|----------------|------|-------------|--------------|-----|
| `estado_msoft` | Integer | Estado original MSoft | `ExpSit` | Mapeo y debugging |
| `usuario_creacion_msoft` | Char | Usuario creación MSoft | `ExpAltUsu` | Auditoría |
| `fecha_creacion_msoft` | Datetime | Fecha creación MSoft | `ExpAltFec` | Auditoría |

**Razón:**
- Debugging y resolución de problemas
- Auditoría completa
- Mapeo de estados

---

## 🔧 Datos y Funcionalidades Faltantes para Importación

### 1. **Sistema de Importación desde MSoft** ⭐ CRÍTICO

**Falta:**
- Modelo/script para importar desde MSoft
- Conexión a base de datos MSoft (ODBC/SQL Server)
- Mapeo automático de partners
- Mapeo automático de camiones
- Manejo de duplicados
- Sincronización incremental

**Necesario crear:**
```python
# aduanas_transport/models/msoft_import.py
class MsoftImport(models.TransientModel):
    _name = "aduanas.msoft.import"
    
    def import_expedientes(self):
        # Conectar a MSoft
        # Leer expedientes
        # Crear/actualizar partners
        # Crear/actualizar camiones
        # Crear/actualizar expedientes
        # Crear líneas
```

---

### 2. **Mapeo y Búsqueda de Partners** ⭐ CRÍTICO

**Falta:**
- Campo `ref` o `code` en partners para buscar por `ExpRemCod`/`ExpDesCod`
- Lógica de búsqueda/creación automática de partners
- Validación de NIF/CIF antes de crear
- Actualización de datos de partners existentes

**Necesario:**
```python
def _get_or_create_partner(self, codigo, nombre, nif, datos):
    # Buscar por código (ref)
    # Si no existe, buscar por NIF
    # Si no existe, crear nuevo
    # Actualizar datos si existe
```

---

### 3. **Mapeo y Búsqueda de Camiones** ⭐ ALTA PRIORIDAD

**Falta:**
- Modelo de camión (ya lo creamos pero fue eliminado)
- Búsqueda/creación automática de camiones por matrícula
- Asignación automática de camión a expediente

**Necesario:**
```python
def _get_or_create_camion(self, matricula, transportista, conductor):
    # Buscar camión por matrícula
    # Si no existe, crear nuevo
    # Asignar transportista y conductor
```

---

### 4. **Validación de Datos antes de Importar** ⭐ ALTA PRIORIDAD

**Falta:**
- Validar que campos obligatorios estén presentes
- Validar formato de oficinas aduaneras
- Validar formato de partidas arancelarias
- Validar NIFs/CIFs
- Reporte de errores de validación

**Necesario:**
```python
def _validate_expediente_data(self, datos):
    errors = []
    if not datos.get('remitente_vat'):
        errors.append("Remitente sin NIF")
    if not datos.get('oficina') or len(datos['oficina']) != 4:
        errors.append("Oficina aduanera inválida")
    # ... más validaciones
    return errors
```

---

### 5. **Manejo de Líneas de Mercancía** ⭐ CRÍTICO

**Falta:**
- Importación de líneas desde tabla separada
- Validación de líneas (pesos, valores)
- Relación correcta con expediente

**Necesario:**
- SQL para leer líneas
- Crear líneas después de crear expediente
- Validar que haya al menos una línea

---

### 6. **Sincronización Incremental** ⭐ ALTA PRIORIDAD

**Falta:**
- Identificar expedientes ya importados
- Solo importar cambios nuevos o modificados
- Manejo de conflictos (¿qué hacer si cambió en ambos sistemas?)

**Necesario:**
```python
def _should_import(self, msoft_expediente):
    # Buscar por msoft_codigo
    # Si existe:
    #   - Comparar fecha_modificacion
    #   - Si MSoft es más reciente, actualizar
    # Si no existe, crear nuevo
```

---

### 7. **Mapeo de Estados** ⭐ MEDIA PRIORIDAD

**Falta:**
- Tabla/configuración de mapeo de estados MSoft → Odoo
- Lógica para mapear `ExpSit` a estados de Odoo
- Manejo de estados especiales

**Necesario:**
```python
ESTADO_MAP = {
    0: 'draft',
    1: 'predeclared',
    2: 'presented',
    3: 'accepted',
    4: 'released',
    5: 'exited',
    6: 'closed',
    7: 'error',
}
```

---

### 8. **Mapeo de Incoterms** ⭐ MEDIA PRIORIDAD

**Falta:**
- Tabla/configuración de mapeo de incoterms
- Validación de incoterms válidos

**Necesario:**
```python
INCOTERM_MAP = {
    1: 'DAP',
    2: 'EXW',
    3: 'FOB',
    4: 'CIF',
    5: 'DDP',
    # ... más
}
```

---

### 9. **Mapeo de Divisas** ⭐ BAJA PRIORIDAD

**Falta:**
- Validación de divisas válidas
- Mapeo de códigos MSoft a códigos ISO

**Ya existe pero puede mejorarse:**
- Actualmente solo EUR y USD
- MSoft usa códigos numéricos (900=EUR, 840=USD)

---

### 10. **Reporte de Importación** ⭐ MEDIA PRIORIDAD

**Falta:**
- Resumen de importación (cuántos importados, errores, etc.)
- Log de errores
- Expedientes que no se pudieron importar y por qué

**Necesario:**
```python
def import_expedientes(self):
    resultados = {
        'importados': 0,
        'actualizados': 0,
        'errores': [],
        'omitidos': 0,
    }
    # ... proceso de importación
    return resultados
```

---

## 📊 Resumen de Prioridades

### ⭐ CRÍTICO (Implementar primero)
1. ✅ Sistema de importación desde MSoft
2. ✅ Mapeo y búsqueda de partners
3. ✅ Manejo de líneas de mercancía
4. ✅ Campos de trazabilidad MSoft (`msoft_codigo`, `msoft_recepcion_num`, etc.)

### ⭐ ALTA PRIORIDAD
5. ✅ Mapeo y búsqueda de camiones
6. ✅ Validación de datos antes de importar
7. ✅ Sincronización incremental
8. ✅ Campos de seguimiento (`estado_msoft`, etc.)

### ⭐ MEDIA PRIORIDAD
9. ✅ Campos de fechas adicionales (`fecha_levante`)
10. ✅ Campos de control (`flag_confirmado`, etc.)
11. ✅ Campos de transporte adicionales (`remolque`)
12. ✅ Mapeo de estados e incoterms
13. ✅ Reporte de importación

### ⭐ BAJA PRIORIDAD
14. ✅ Campos de documentación (albaranes, órdenes)
15. ✅ Campos de oficina aduanera detallados
16. ✅ Mapeo de divisas mejorado

---

## 🎯 Recomendación de Implementación

### Fase 1: Campos Esenciales
Agregar al modelo:
- `msoft_codigo` (Char, index=True)
- `msoft_recepcion_num` (Integer)
- `msoft_fecha_modificacion` (Datetime)
- `msoft_sincronizado` (Boolean)
- `fecha_levante` (Datetime)
- `flag_confirmado` (Boolean)
- `flag_anulado` (Boolean)

### Fase 2: Sistema de Importación
Crear:
- Modelo `aduanas.msoft.import`
- Métodos de búsqueda/creación de partners
- Métodos de búsqueda/creación de camiones
- Validación de datos
- Importación de expedientes y líneas

### Fase 3: Mejoras
- Sincronización incremental
- Campos adicionales
- Reportes y estadísticas

