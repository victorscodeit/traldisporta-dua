# Sistema de Gestión de Incidencias AEAT

## 📋 Resumen

Se ha implementado un sistema completo para gestionar las incidencias que comunica la AEAT durante el proceso aduanero. El sistema detecta automáticamente incidencias desde las respuestas XML de AEAT y las registra para su seguimiento y resolución.

---

## ✅ Funcionalidades Implementadas

### 1. **Modelo de Incidencias** (`aduana.incidencia`)

**Campos principales:**
- `name` - Referencia única (secuencia automática: INC-000001)
- `expediente_id` - Expediente relacionado (Many2one)
- `mrn` - MRN del expediente (relacionado)
- `tipo_incidencia` - Tipo: Error, Advertencia, Solicitud Info, Rechazo, Suspensión, Requerimiento, Notificación, Otra
- `codigo_incidencia` - Código de error/incidencia de AEAT
- `titulo` - Título descriptivo
- `descripcion` - Descripción detallada
- `mensaje_aeat` - Mensaje original completo de AEAT
- `fecha_incidencia` - Fecha de la incidencia
- `fecha_deteccion` - Fecha en que se detectó
- `fecha_resolucion` - Fecha de resolución
- `state` - Estado: Pendiente, En Revisión, Resuelta, Cerrada, Rechazada
- `prioridad` - Prioridad: Baja, Media, Alta, Crítica
- `origen` - Origen: Bandeja, CC515C, CC511C, Importación, Manual
- `resolucion` - Descripción de cómo se resolvió
- `accion_tomada` - Acciones realizadas
- `usuario_resolucion` - Usuario que resolvió
- `attachment_ids` - Archivos adjuntos relacionados
- `dias_pendiente` - Días que lleva pendiente (compute)

---

### 2. **Detección Automática de Incidencias**

**Mejoras en el Parser XML:**
- ✅ Detecta diferentes tipos de incidencias en respuestas XML
- ✅ Extrae código, mensaje y tipo de incidencia
- ✅ Identifica: Requerimientos, Solicitudes, Advertencias, Rechazos, Suspensiones
- ✅ Mantiene compatibilidad con formato anterior de errores

**Orígenes de detección:**
- ✅ **Bandeja AEAT** - Consulta periódica automática
- ✅ **CC515C** - Respuestas de exportación
- ✅ **CC511C** - Presentación de exportación
- ✅ **Importación** - Declaraciones de importación
- ✅ **Manual** - Creación manual por usuarios

---

### 3. **Procesamiento Automático**

**Método `_procesar_incidencias()`:**
- Crea incidencias automáticamente desde datos parseados
- Asigna prioridad según tipo:
  - Error → Alta
  - Rechazo/Suspensión → Crítica
  - Requerimiento → Alta
  - Solicitud Info → Media
  - Advertencia/Notificación → Baja
- Notifica en el chatter del expediente
- Cambia estado del expediente a "error" si es crítica

---

### 4. **Vistas y Gestión**

**Vista Tree:**
- Lista de incidencias con colores según estado/prioridad
- Filtros: Pendientes, Críticas, Resueltas, Hoy, Esta Semana
- Agrupación por: Estado, Prioridad, Tipo, Origen, Expediente, Fecha

**Vista Form:**
- Información completa de la incidencia
- Botones de acción: Marcar como Resuelta, Cerrar, Ver Expediente
- Campos de resolución (visible cuando se resuelve)
- Archivos adjuntos
- Chatter integrado

**Integración en Expediente:**
- Botones estadísticos: Total incidencias, Pendientes
- Pestaña "Incidencias" con lista de incidencias del expediente
- Acceso directo desde el expediente

---

### 5. **Estados y Flujo de Trabajo**

**Estados:**
1. **Pendiente** - Incidencia recién detectada
2. **En Revisión** - Siendo revisada
3. **Resuelta** - Resuelta pero no cerrada
4. **Cerrada** - Cerrada definitivamente
5. **Rechazada** - Rechazada (no aplicable)

**Acciones:**
- `action_marcar_resuelta()` - Marca como resuelta y registra usuario/fecha
- `action_marcar_cerrada()` - Cierra la incidencia
- `action_ver_expediente()` - Abre el expediente relacionado

---

## 🔄 Flujo de Detección

```
1. AEAT envía respuesta XML
   ↓
2. Parser XML extrae incidencias
   ↓
3. _procesar_incidencias() crea registros
   ↓
4. Notificación en chatter del expediente
   ↓
5. Si es crítica → Cambia estado expediente a "error"
   ↓
6. Usuario gestiona incidencia
   ↓
7. Marca como resuelta/cerrada
```

---

## 📊 Tipos de Incidencias Detectadas

| Tipo | Descripción | Prioridad | Acción Expediente |
|------|-------------|-----------|-------------------|
| **Error** | Error en el proceso | Alta | Cambia a "error" |
| **Rechazo** | Rechazo de declaración | Crítica | Cambia a "error" |
| **Suspensión** | Suspensión del proceso | Crítica | Cambia a "error" |
| **Requerimiento** | Requerimiento de información | Alta | Notifica |
| **Solicitud Info** | Solicitud de información adicional | Media | Notifica |
| **Advertencia** | Advertencia sin bloqueo | Baja | Notifica |
| **Notificación** | Notificación informativa | Baja | Notifica |

---

## 🎯 Casos de Uso

### Caso 1: Error en CC515C
1. Se envía CC515C a AEAT
2. AEAT responde con error
3. Sistema detecta incidencia tipo "error"
4. Se crea incidencia con prioridad "alta"
5. Expediente cambia a estado "error"
6. Usuario recibe notificación
7. Usuario revisa y corrige
8. Usuario marca incidencia como resuelta

### Caso 2: Requerimiento desde Bandeja
1. Cron consulta bandeja periódicamente
2. Detecta requerimiento de información
3. Crea incidencia tipo "requerimiento" prioridad "alta"
4. Notifica en chatter
5. Usuario proporciona información
6. Usuario marca como resuelta

### Caso 3: Suspensión
1. AEAT suspende proceso
2. Sistema detecta tipo "suspension"
3. Crea incidencia prioridad "crítica"
4. Expediente cambia a "error"
5. Usuario toma acciones correctivas
6. Usuario resuelve y cierra incidencia

---

## 🔍 Búsqueda y Filtros

**Filtros disponibles:**
- Pendientes (pendiente, en_revision)
- Críticas (prioridad crítica)
- Resueltas
- Hoy
- Esta Semana

**Agrupaciones:**
- Por Estado
- Por Prioridad
- Por Tipo
- Por Origen
- Por Expediente
- Por Fecha

---

## 📈 Métricas y Seguimiento

**Campos calculados:**
- `dias_pendiente` - Días que lleva pendiente
- `incidencias_count` - Total de incidencias del expediente
- `incidencias_pendientes_count` - Incidencias pendientes del expediente

**Visualización:**
- Colores en vista tree según estado/prioridad
- Badges para prioridad y estado
- Botones estadísticos en expediente

---

## 🔔 Notificaciones

**Automáticas:**
- Notificación en chatter cuando se detecta incidencia
- Notificación cuando se resuelve/cierra
- Incluye información: Tipo, Código, Título

**Manuales:**
- Usuario puede añadir comentarios en chatter
- Seguimiento de actividades
- Archivos adjuntos

---

## 📝 Archivos Creados/Modificados

### Nuevos:
1. `aduanas_transport/models/aduana_incidencia.py` - Modelo de incidencias
2. `aduanas_transport/views/aduana_incidencia_views.xml` - Vistas
3. `aduanas_transport/data/ir_sequence.xml` - Secuencia para referencias

### Modificados:
1. `aduanas_transport/models/xml_parser.py` - Parser mejorado para detectar incidencias
2. `aduanas_transport/models/aduana_expediente.py` - Método `_procesar_incidencias()` y campos relacionados
3. `aduanas_transport/models/__init__.py` - Import del nuevo modelo
4. `aduanas_transport/security/ir.model.access.csv` - Permisos
5. `aduanas_transport/__manifest__.py` - Datos y vistas

---

## 🎉 Beneficios

1. ✅ **Trazabilidad completa** - Todas las incidencias quedan registradas
2. ✅ **Detección automática** - No se pierden incidencias
3. ✅ **Priorización** - Sistema asigna prioridad automáticamente
4. ✅ **Seguimiento** - Estados y flujo de trabajo claro
5. ✅ **Integración** - Totalmente integrado con expedientes
6. ✅ **Notificaciones** - Usuarios informados automáticamente
7. ✅ **Historial** - Chatter y archivos para documentación
8. ✅ **Métricas** - Conteo de incidencias por expediente

---

## 🚀 Próximos Pasos Recomendados

1. **Reportes** - Crear reportes de incidencias por tipo, prioridad, tiempo de resolución
2. **Alertas** - Alertas automáticas para incidencias críticas sin resolver
3. **Plantillas** - Plantillas de respuesta para tipos comunes de incidencias
4. **Integración Email** - Envío de emails cuando hay incidencias críticas
5. **Dashboard** - Dashboard con métricas de incidencias

---

## ✅ Estado: COMPLETADO

El sistema de gestión de incidencias está completamente implementado y funcional.

