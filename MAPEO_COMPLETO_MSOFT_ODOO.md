# Mapeo Completo MSoft → Odoo Expedientes Aduaneros

## Índice
1. [Campos Principales del Expediente](#campos-principales)
2. [Remitente (Origen)](#remitente)
3. [Consignatario (Destino)](#consignatario)
4. [Datos Aduaneros](#datos-aduaneros)
5. [Transporte y Vehículo](#transporte)
6. [Facturación](#facturación)
7. [Incoterm](#incoterm)
8. [Líneas de Mercancía](#líneas)
9. [Estados y Control](#estados)
10. [Fechas y Horas](#fechas)
11. [Observaciones y Textos](#observaciones)
12. [SQL de Importación](#sql)

---

## Campos Principales del Expediente {#campos-principales}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpCod` | INT/VARCHAR | Código del expediente | `name` | Char | **PRINCIPAL** - Referencia única |
| `ExpRecNum` | INT | Número de recepción | - | - | Usar para name compuesto si ExpCod no es único |
| `HolCod` | INT | Código hol | - | - | No mapeado |
| `SecCod` | INT | Código sección | - | - | No mapeado |
| `ExpCtrCod` | INT | Código control | - | - | No mapeado |
| `ExpDatRec` | DATETIME | Fecha recepción | - | - | Información adicional |
| `ExpDatReg` | DATETIME | Fecha registro | `create_date` | Datetime | Automático en Odoo, usar como referencia |
| `ExpDatEtd` | DATETIME | Fecha prevista salida | `fecha_prevista` | Datetime | **IMPORTANTE** |
| `ExpDatLle` | DATETIME | Fecha llegada | `fecha_entrada_real` | Datetime | Fecha real de entrada |
| `ExpDatLev` | DATETIME | Fecha levante | - | - | Usar para actualizar estado a 'released' |
| `ExpDatSel` | DATETIME | Fecha selección | - | - | No mapeado |
| `ExpDatDoc` | DATETIME | Fecha documento | - | - | No mapeado |
| `ExpDatRTD` | DATETIME | Fecha RTD | - | - | No mapeado |
| `ExpDatRTA` | DATETIME | Fecha RTA | - | - | No mapeado |

**SQL para name:**
```sql
-- Opción 1: Solo ExpCod
CAST(ExpCod AS VARCHAR) AS name

-- Opción 2: ExpCod + ExpRecNum (más único)
CONCAT(CAST(ExpCod AS VARCHAR), '-', CAST(ExpRecNum AS VARCHAR)) AS name
```

---

## Remitente (Origen) {#remitente}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpRemCod` | INT/VARCHAR | Código remitente | `remitente` | Many2one | **Buscar partner por código** |
| `ExpRemDes` | VARCHAR | Nombre remitente | `remitente.name` | Char | Nombre completo |
| `ExpRemNif` | VARCHAR | NIF/CIF remitente | `remitente.vat` | Char | **Usar para buscar si no existe código** |
| `ExpRemDom` | VARCHAR | Domicilio remitente | `remitente.street` | Char | Dirección completa |
| `ExpRemTel` | VARCHAR | Teléfono remitente | `remitente.phone` | Char | Teléfono |
| `ExpRemPai` | INT | País remitente | `remitente.country_id.code` | Char | **11=ES, 43=AD** |
| `ExpRemNem` | VARCHAR | Código postal | `remitente.zip` | Char | Código postal |
| `ExpRemPob` | VARCHAR | Población | `remitente.city` | Char | Ciudad |
| `ExpRemRep` | VARCHAR | Representante | - | - | No mapeado |
| `ExpRemPos` | INT | Posición | - | - | No mapeado |
| `ExpReDpCod` | INT | Código departamento | - | - | No mapeado |
| `ExpReDpDes` | VARCHAR | Descripción departamento | - | - | No mapeado |
| `ExpRecPai` | INT | País recepción | - | - | No mapeado |
| `ExpRecNem` | VARCHAR | CP recepción | - | - | No mapeado |
| `ExpRecPos` | INT | Pos recepción | - | - | No mapeado |
| `ExpRecRep` | VARCHAR | Rep recepción | - | - | No mapeado |
| `ExpRecPob` | VARCHAR | Pob recepción | - | - | No mapeado |
| `ExpRecTel` | VARCHAR | Tel recepción | - | - | No mapeado |
| `ExpRecCon` | VARCHAR | Contacto recepción | - | - | No mapeado |
| `ExpRecFax` | VARCHAR | Fax recepción | - | - | No mapeado |
| `ExpRecMail` | VARCHAR | Email recepción | - | - | No mapeado |

**Lógica de búsqueda/creación Partner:**
1. Buscar por `ExpRemCod` (campo `ref` o `code` en partner)
2. Si no existe, buscar por `ExpRemNif` (campo `vat`)
3. Si no existe, crear nuevo partner con todos los datos

**Mapeo País:**
- `11` → `ES` (España)
- `43` → `AD` (Andorra)
- Otros → Verificar código

---

## Consignatario (Destino) {#consignatario}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpDesCod` | INT/VARCHAR | Código consignatario | `consignatario` | Many2one | **Buscar partner por código** |
| `ExpDesDes` | VARCHAR | Nombre consignatario | `consignatario.name` | Char | Nombre completo |
| `ExpDesNif` | VARCHAR | NIF/CIF consignatario | `consignatario.vat` | Char | **Usar para buscar si no existe código** |
| `ExpDesDom` | VARCHAR | Domicilio consignatario | `consignatario.street` | Char | Dirección completa |
| `ExpDesTel` | VARCHAR | Teléfono consignatario | `consignatario.phone` | Char | Teléfono |
| `ExpDesPai` | INT | País consignatario | `consignatario.country_id.code` | Char | **11=ES, 43=AD** |
| `ExpDesNem` | VARCHAR | Código postal | `consignatario.zip` | Char | Código postal |
| `ExpDesPob` | VARCHAR | Población | `consignatario.city` | Char | Ciudad |
| `ExpDeDpCod` | INT | Código departamento | - | - | No mapeado |
| `ExpDeDpDes` | VARCHAR | Descripción departamento | - | - | No mapeado |
| `ExpDesRep` | VARCHAR | Representante | - | - | No mapeado |
| `ExpDesPos` | INT | Posición | - | - | No mapeado |
| `ExpDsCtDs` | VARCHAR | Descripción ciudad destino | - | - | No mapeado |

**Lógica de búsqueda/creación Partner:**
Igual que remitente: buscar por código o NIF, crear si no existe.

---

## Datos Aduaneros {#datos-aduaneros}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpOrOfCd` | INT | Oficina aduanas origen | `oficina` | Char | **Formato: 4 dígitos (ej: 0801)** |
| `ExpDsOfCd` | INT | Oficina aduanas destino | - | - | Información adicional |
| `ExpOrZoCd` | INT | Zona origen | - | - | No mapeado |
| `ExpOrRdCd` | INT | Ruta origen | - | - | No mapeado |
| `ExpOrEmCd` | INT | Empresa origen | - | - | No mapeado |
| `ExpOrCtCd` | INT | Centro origen | - | - | No mapeado |
| `ExpTrEmCd` | INT | Empresa transporte | - | - | No mapeado |
| `ExpTrCtCd` | INT | Centro transporte | - | - | No mapeado |
| `ExpDsZoCd` | INT | Zona destino | - | - | No mapeado |
| `ExpDsRdCd` | INT | Ruta destino | - | - | No mapeado |
| `ExpDsEmCd` | INT | Empresa destino | - | - | No mapeado |
| `ExpDsCtCd` | INT | Centro destino | - | - | No mapeado |
| `ExpOriNac` | INT | País origen nacional | `pais_origen` | Char | **1=ES, 43=AD** |
| `ExpOriT1` | VARCHAR | Tipo origen 1 | - | - | No mapeado |
| `ExpOriT2` | VARCHAR | Tipo origen 2 | - | - | No mapeado |
| `ExpOriOk` | CHAR | Origen OK | - | - | Flag validación |
| `ExpDesOk` | CHAR | Destino OK | - | - | Flag validación |
| `ExpOriSec` | INT | Sección origen | - | - | No mapeado |
| `ExpOriCtr` | INT | Control origen | - | - | No mapeado |
| `ExpOriExp` | INT | Expediente origen | - | - | No mapeado |
| `ExpDesSec` | INT | Sección destino | - | - | No mapeado |
| `ExpDesCtr` | INT | Control destino | - | - | No mapeado |
| `ExpDesExp` | INT | Expediente destino | - | - | No mapeado |
| `ExpOriAge` | VARCHAR | Agente origen | - | - | No mapeado |
| `ExpOriTip` | VARCHAR | Tipo origen | - | - | No mapeado |
| `ExpDesAge` | VARCHAR | Agente destino | - | - | No mapeado |
| `ExpDesTip` | VARCHAR | Tipo destino | - | - | No mapeado |
| `ExpAgeAdu` | VARCHAR | Agente aduanas | - | - | No mapeado |
| `ExpAg2Adu` | VARCHAR | Agente 2 aduanas | - | - | No mapeado |
| `ExpAgeTip` | VARCHAR | Tipo agente | - | - | No mapeado |
| `ExpAg2Tip` | VARCHAR | Tipo agente 2 | - | - | No mapeado |
| `ExpNpiGac` | VARCHAR | NPI GAC | - | - | No mapeado |
| `ExpNpiAdu` | VARCHAR | NPI Aduanas | - | - | No mapeado |
| `ExpADTGEn` | VARCHAR | ADTG Entrada | - | - | No mapeado |
| `ExpADTGSa` | VARCHAR | ADTG Salida | - | - | No mapeado |
| `ExpADTAEn` | VARCHAR | ADTA Entrada | - | - | No mapeado |
| `ExpADTASa` | VARCHAR | ADTA Salida | - | - | No mapeado |
| `ExpADRNro` | VARCHAR | ADR Número | - | - | No mapeado |
| `ExpADTNro` | VARCHAR | ADT Número | - | - | No mapeado |
| `ExpAdtGNr` | VARCHAR | ADT G Número | - | - | No mapeado |
| `ExpDocAdu` | VARCHAR | Documento aduanas | - | - | No mapeado |

**Formato Oficina Aduanera:**
```sql
CASE 
    WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 1 THEN '000' + CAST(ExpOrOfCd AS VARCHAR) + '1'
    WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 2 THEN '00' + CAST(ExpOrOfCd AS VARCHAR) + '1'
    WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 3 THEN '0' + CAST(ExpOrOfCd AS VARCHAR)
    ELSE CAST(ExpOrOfCd AS VARCHAR)
END AS oficina
```

**Mapeo Países:**
- `ExpOriNac = 1` → `pais_origen = "ES"`
- `ExpOriNac = 43` → `pais_origen = "AD"`
- `ExpDesPai = 11` → `pais_destino = "ES"`
- `ExpDesPai = 43` → `pais_destino = "AD"`

---

## Dirección del Expediente {#dirección}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpExpDua` | INT/CHAR | Exportación DUA | `direction` | Selection | **Si = 1 → "export"** |
| `ExpImpDua` | INT/CHAR | Importación DUA | `direction` | Selection | **Si = 1 → "import"** |

**Lógica:**
```sql
CASE 
    WHEN ExpExpDua = 1 THEN 'export'
    WHEN ExpImpDua = 1 THEN 'import'
    WHEN ExpOriNac = 1 AND ExpDesPai = 43 THEN 'export'  -- España → Andorra
    WHEN ExpOriNac = 43 AND ExpDesPai = 1 THEN 'import'   -- Andorra → España
    ELSE 'export'  -- Por defecto
END AS direction
```

---

## Transporte y Vehículo {#transporte}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `TraCod` | INT/VARCHAR | Código transporte | `camion_id` (buscar) | Many2one | Buscar camión por código |
| `ExpTrac` | VARCHAR | Matrícula | `camion_id.matricula` | Char | **Buscar camión por matrícula** |
| `ExpRemol` | VARCHAR | Remolque | - | - | No mapeado actualmente |
| `ExpProCod` | INT/VARCHAR | Código proveedor | `referencia_transporte` | Char | Referencia transporte |
| `ExpProDes` | VARCHAR | Descripción proveedor | - | - | No mapeado |
| `ExpProRef` | VARCHAR | Referencia proveedor | - | - | No mapeado |
| `ExpCon1` | VARCHAR | Conductor 1 | `conductor_nombre` | Char | Nombre conductor |
| `ExpCon2` | VARCHAR | Conductor 2 | `conductor_dni` | Char | DNI o conductor 2 |
| `TipConCod` | VARCHAR | Tipo conductor | - | - | No mapeado |
| `ExpTxt01` a `ExpTxt09` | VARCHAR | Textos adicionales | - | - | No mapeados (pueden concatenarse en observaciones) |

**Lógica de búsqueda/creación Camión:**
1. Buscar camión por `ExpTrac` (matrícula)
2. Si no existe, crear camión con:
   - `matricula` = `ExpTrac`
   - `transportista` = `TraCod` (si existe)
   - `conductor_nombre` = `ExpCon1` (si existe)
   - `conductor_dni` = `ExpCon2` (si es DNI)

---

## Facturación {#facturación}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpValFra` | DECIMAL | Valor factura | `valor_factura` | Float | **IMPORTANTE** |
| `ExpValDiv` | INT | Divisa | `moneda` | Selection | **900=EUR, 840=USD** |
| `ExpValNem` | DECIMAL | Valor en nem | - | - | No mapeado |
| `ExpVasDiv` | INT | Divisa adicional | - | - | No mapeado |
| `ExpVasNem` | DECIMAL | Valor adicional nem | - | - | No mapeado |
| `ExpSuFra` | DECIMAL | Subtotal factura | - | - | No mapeado |
| `ExpAlbOrd` | VARCHAR | Albarán orden | `numero_factura` | Char | Número factura/albarán |
| `ExpAlbRem` | VARCHAR | Albarán remitente | - | - | No mapeado |
| `ExpAlbDes` | VARCHAR | Albarán destinatario | - | - | No mapeado |
| `ExpOrdCod` | INT | Código orden | - | - | No mapeado |
| `ExpOrdDes` | VARCHAR | Descripción orden | - | - | No mapeado |

**Mapeo Divisas:**
- `900` = `EUR`
- `840` = `USD`
- `978` = `EUR` (código ISO alternativo)
- Otros → `EUR` por defecto

**SQL:**
```sql
CAST(ExpValFra AS DECIMAL(18,2)) AS valor_factura,
CASE ExpValDiv
    WHEN 900 THEN 'EUR'
    WHEN 840 THEN 'USD'
    WHEN 978 THEN 'EUR'
    ELSE 'EUR'
END AS moneda
```

---

## Incoterm {#incoterm}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `IcoCod` | INT | Código incoterm | `incoterm` | Char | **Mapear códigos** |
| `ExpIcoDes` | VARCHAR | Descripción incoterm | - | - | Información adicional |

**Mapeo Incoterms (ajustar según tu sistema):**
- `1` = `DAP` (Porte Pagado)
- `2` = `EXW` (En Fábrica)
- `3` = `FOB` (Libre a Bordo)
- `4` = `CIF` (Coste, Seguro y Flete)
- `5` = `DDP` (Entregado con Derechos Pagados)
- `6` = `FCA` (Franco Transportista)
- `7` = `CPT` (Transporte Pagado Hasta)
- `8` = `CIP` (Transporte y Seguro Pagados Hasta)
- Otros → Usar `ExpIcoDes` directamente si es texto

**SQL:**
```sql
CASE IcoCod
    WHEN 1 THEN 'DAP'
    WHEN 2 THEN 'EXW'
    WHEN 3 THEN 'FOB'
    WHEN 4 THEN 'CIF'
    WHEN 5 THEN 'DDP'
    WHEN 6 THEN 'FCA'
    WHEN 7 THEN 'CPT'
    WHEN 8 THEN 'CIP'
    ELSE LTRIM(RTRIM(ISNULL(ExpIcoDes, '')))
END AS incoterm
```

---

## Líneas de Mercancía {#líneas}

**NOTA:** Las líneas están en una tabla separada relacionada con `ExpCod`.

| Campo MSoft (Líneas) | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|---------------------|------|-------------|------------|-----------|-------|
| `ExpCod` | INT | Código expediente | `expediente_id` | Many2one | **Relación con expediente** |
| `ExpSegMer` | INT | Segmento mercancía | `item_number` | Integer | Número de línea |
| `MerCod` | VARCHAR | Código mercancía | `partida` | Char | **Partida arancelaria (10 dígitos)** |
| `ExpMerDes` | VARCHAR | Descripción mercancía | `descripcion` | Char | Descripción |
| Peso bruto | DECIMAL | Peso bruto | `peso_bruto` | Float | En kg |
| Peso neto | DECIMAL | Peso neto | `peso_neto` | Float | En kg |
| Unidades | DECIMAL | Unidades | `unidades` | Float | Cantidad |
| Bultos | INT | Número bultos | `bultos` | Integer | Número de bultos |
| Valor línea | DECIMAL | Valor línea | `valor_linea` | Float | Valor de la línea |
| País origen línea | INT | País origen | `pais_origen` | Char | Por línea |

**SQL para líneas:**
```sql
SELECT 
    ExpCod AS expediente_code,
    ExpSegMer AS item_number,
    MerCod AS partida_arancelaria,
    LTRIM(RTRIM(ExpMerDes)) AS descripcion,
    -- Ajustar según campos reales de tu tabla
    PesoBruto AS peso_bruto,
    PesoNeto AS peso_neto,
    Unidades AS unidades,
    Bultos AS bultos,
    ValorLinea AS valor_linea,
    CASE PaisOrigen 
        WHEN 1 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'ES'
    END AS pais_origen
FROM [TuTablaLineasExpedientes]
WHERE ExpCod IN (SELECT ExpCod FROM [TuTablaExpedientes] WHERE ...)
ORDER BY ExpCod, ExpSegMer
```

---

## Estados y Control {#estados}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpSit` | INT | Estado | `state` | Selection | **Mapear según lógica** |
| `ExpConf` | CHAR | Confirmado | - | - | Flag confirmación |
| `ExpFlgAnu` | CHAR | Flag anulado | - | - | **Si = 'S' → NO importar** |
| `ExpFlgMan` | CHAR | Flag manual | - | - | No mapeado |
| `ExpFlgAbo` | CHAR | Flag abonado | - | - | No mapeado |
| `ExpRetAut` | CHAR | Retorno automático | - | - | No mapeado |
| `ExpExeIva` | CHAR | Exento IVA | - | - | No mapeado |
| `ExpPteTas` | CHAR | Pendiente tasas | - | - | No mapeado |
| `ExpCnsFlg` | CHAR | Flag consigna | - | - | No mapeado |
| `ExpComFlg` | CHAR | Flag comercial | - | - | No mapeado |
| `ExpFrio` | CHAR | Frío | - | - | No mapeado |
| `ExpFrioSN` | CHAR | Frío S/N | - | - | No mapeado |
| `ExpFrioMax` | DECIMAL | Frío máximo | - | - | No mapeado |
| `ExpSeg` | VARCHAR | Segmento | - | - | No mapeado |
| `ExpClaAdr` | VARCHAR | Clasificación ADR | - | - | No mapeado |
| `ExpCrgAsi` | CHAR | Carga asignada | - | - | No mapeado |
| `ExpPonEnt` | DECIMAL | Peso entrada | - | - | No mapeado |
| `ExpNumHoj` | INT | Número hojas | - | - | No mapeado |
| `ExpNumEti` | INT | Número etiquetas | - | - | No mapeado |
| `ExpTipEti` | INT | Tipo etiqueta | - | - | No mapeado |
| `ExpCntCod` | INT | Código contenedor | - | - | No mapeado |
| `ExpCntCtr` | INT | Control contenedor | - | - | No mapeado |
| `ExpCtrHoj` | INT | Control hojas | - | - | No mapeado |
| `ExpFlgAnu` | CHAR | Anulado | - | - | **CRÍTICO: Excluir si = 'S'** |

**Mapeo Estados (ajustar según tu lógica):**
```sql
CASE ExpSit
    WHEN 0 THEN 'draft'           -- Borrador
    WHEN 1 THEN 'predeclared'     -- Predeclarado
    WHEN 2 THEN 'presented'       -- Presentado
    WHEN 3 THEN 'accepted'        -- Aceptado (con MRN)
    WHEN 4 THEN 'released'        -- Levante
    WHEN 5 THEN 'exited'          -- Salida/Entrada confirmada
    WHEN 6 THEN 'closed'          -- Cerrado
    WHEN 7 THEN 'error'           -- Error
    ELSE 'draft'
END AS state
```

**Filtro SQL para excluir anulados:**
```sql
WHERE (ExpFlgAnu IS NULL OR ExpFlgAnu != 'S')
```

---

## Fechas y Horas {#fechas}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpDatEtd` | DATETIME | Fecha/hora ETD | `fecha_prevista` | Datetime | Fecha prevista salida |
| `ExpDatLle` | DATETIME | Fecha/hora llegada | `fecha_entrada_real` | Datetime | Fecha real entrada |
| `ExpDatLev` | DATETIME | Fecha/hora levante | - | - | Usar para estado 'released' |
| `ExpHorEtd` | TIME | Hora ETD | - | - | No mapeado (solo fecha) |
| `ExpHorLev` | TIME | Hora levante | - | - | No mapeado |
| `ExpHorLle` | TIME | Hora llegada | - | - | No mapeado |
| `ExpHorReg` | TIME | Hora registro | - | - | No mapeado |
| `ExpHorEtdF` | TIME | Hora ETD formato | - | - | No mapeado |
| `ExpHorLleF` | TIME | Hora llegada formato | - | - | No mapeado |
| `ExpHorEtdH` | TIME | Hora ETD hora | - | - | No mapeado |
| `ExpHorLleH` | TIME | Hora llegada hora | - | - | No mapeado |

**Nota:** Odoo maneja fechas con hora, así que si solo tienes fecha, se usará 00:00:00.

---

## Observaciones y Textos {#observaciones}

| Campo MSoft | Tipo | Descripción | Campo Odoo | Tipo Odoo | Notas |
|------------|------|-------------|------------|-----------|-------|
| `ExpObs1` | VARCHAR | Observaciones 1 | `observaciones` | Text | **Concatenar** |
| `ExpObs2` | VARCHAR | Observaciones 2 | `observaciones` | Text | **Concatenar** |
| `ExpTxt01` | VARCHAR | Texto 01 | - | - | Opcional: concatenar |
| `ExpTxt02` | VARCHAR | Texto 02 | - | - | Opcional: concatenar |
| `ExpTxt03` | VARCHAR | Texto 03 | - | - | Opcional: concatenar |
| `ExpTxt04` | VARCHAR | Texto 04 | - | - | Opcional: concatenar |
| `ExpTxt05` | VARCHAR | Texto 05 | - | - | Opcional: concatenar |
| `ExpTxt06` | VARCHAR | Texto 06 | - | - | Opcional: concatenar |
| `ExpTxt07` | VARCHAR | Texto 07 | - | - | Opcional: concatenar |
| `ExpTxt08` | VARCHAR | Texto 08 | - | - | Opcional: concatenar |
| `ExpTxt09` | VARCHAR | Texto 09 | - | - | Opcional: concatenar |

**SQL para concatenar observaciones:**
```sql
LTRIM(RTRIM(
    ISNULL(ExpObs1, '') + 
    CASE WHEN ExpObs2 IS NOT NULL AND ExpObs2 != '' 
        THEN ' | ' + ExpObs2 
        ELSE '' 
    END +
    CASE WHEN ExpTxt01 IS NOT NULL AND ExpTxt01 != '' 
        THEN ' | ' + ExpTxt01 
        ELSE '' 
    END
    -- Añadir más ExpTxt si es necesario
)) AS observaciones
```

---

## Campos de Barras y Códigos {#barras}

Los campos `ExpBar1` a `ExpBar99` son códigos de barras y referencias. No se mapean directamente pero pueden ser útiles para búsquedas o referencias.

| Campo MSoft | Tipo | Descripción | Uso |
|------------|------|-------------|-----|
| `ExpBar1` a `ExpBar99` | VARCHAR | Códigos de barras | No mapeados, pueden usarse para búsqueda |

---

## SQL de Importación Completo {#sql}

```sql
-- ============================================
-- EXPEDIENTES PRINCIPALES
-- ============================================
SELECT 
    -- IDENTIFICACIÓN
    CONCAT(CAST(ExpCod AS VARCHAR), '-', CAST(ExpRecNum AS VARCHAR)) AS name,
    ExpCod AS expediente_code,
    ExpRecNum AS expediente_num,
    
    -- DIRECCIÓN
    CASE 
        WHEN ExpExpDua = 1 THEN 'export'
        WHEN ExpImpDua = 1 THEN 'import'
        WHEN ExpOriNac = 1 AND ExpDesPai = 43 THEN 'export'
        WHEN ExpOriNac = 43 AND ExpDesPai = 1 THEN 'import'
        ELSE 'export'
    END AS direction,
    
    -- FECHAS
    ExpDatEtd AS fecha_prevista,
    ExpDatLle AS fecha_entrada_real,
    ExpDatReg AS fecha_registro,
    
    -- REMITENTE (buscar/crear partner)
    ExpRemCod AS remitente_code,
    LTRIM(RTRIM(ExpRemDes)) AS remitente_name,
    LTRIM(RTRIM(ExpRemNif)) AS remitente_vat,
    LTRIM(RTRIM(ExpRemDom)) AS remitente_street,
    LTRIM(RTRIM(ExpRemTel)) AS remitente_phone,
    CASE ExpRemPai 
        WHEN 11 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'ES'
    END AS remitente_country_code,
    LTRIM(RTRIM(ExpRemNem)) AS remitente_zip,
    LTRIM(RTRIM(ExpRemPob)) AS remitente_city,
    
    -- CONSIGNATARIO (buscar/crear partner)
    ExpDesCod AS consignatario_code,
    LTRIM(RTRIM(ExpDesDes)) AS consignatario_name,
    LTRIM(RTRIM(ExpDesNif)) AS consignatario_vat,
    LTRIM(RTRIM(ExpDesDom)) AS consignatario_street,
    LTRIM(RTRIM(ExpDesTel)) AS consignatario_phone,
    CASE ExpDesPai 
        WHEN 11 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'AD'
    END AS consignatario_country_code,
    LTRIM(RTRIM(ExpDesNem)) AS consignatario_zip,
    LTRIM(RTRIM(ExpDesPob)) AS consignatario_city,
    
    -- ADUANAS
    CASE 
        WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 1 THEN '000' + CAST(ExpOrOfCd AS VARCHAR) + '1'
        WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 2 THEN '00' + CAST(ExpOrOfCd AS VARCHAR) + '1'
        WHEN LEN(CAST(ExpOrOfCd AS VARCHAR)) = 3 THEN '0' + CAST(ExpOrOfCd AS VARCHAR)
        ELSE CAST(ExpOrOfCd AS VARCHAR)
    END AS oficina,
    CASE ExpOriNac 
        WHEN 1 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'ES'
    END AS pais_origen,
    CASE ExpDesPai 
        WHEN 11 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'AD'
    END AS pais_destino,
    
    -- TRANSPORTE
    LTRIM(RTRIM(ExpTrac)) AS matricula,
    TraCod AS transportista_code,
    ExpProCod AS referencia_transporte,
    LTRIM(RTRIM(ExpCon1)) AS conductor_nombre,
    LTRIM(RTRIM(ExpCon2)) AS conductor_dni,
    
    -- FACTURACIÓN
    CAST(ExpValFra AS DECIMAL(18,2)) AS valor_factura,
    CASE ExpValDiv
        WHEN 900 THEN 'EUR'
        WHEN 840 THEN 'USD'
        WHEN 978 THEN 'EUR'
        ELSE 'EUR'
    END AS moneda,
    LTRIM(RTRIM(ExpAlbOrd)) AS numero_factura,
    
    -- INCOTERM
    CASE IcoCod
        WHEN 1 THEN 'DAP'
        WHEN 2 THEN 'EXW'
        WHEN 3 THEN 'FOB'
        WHEN 4 THEN 'CIF'
        WHEN 5 THEN 'DDP'
        WHEN 6 THEN 'FCA'
        WHEN 7 THEN 'CPT'
        WHEN 8 THEN 'CIP'
        ELSE LTRIM(RTRIM(ISNULL(ExpIcoDes, '')))
    END AS incoterm,
    
    -- OBSERVACIONES
    LTRIM(RTRIM(
        ISNULL(ExpObs1, '') + 
        CASE WHEN ExpObs2 IS NOT NULL AND ExpObs2 != '' 
            THEN ' | ' + ExpObs2 
            ELSE '' 
        END
    )) AS observaciones,
    
    -- ESTADO
    CASE ExpSit
        WHEN 0 THEN 'draft'
        WHEN 1 THEN 'predeclared'
        WHEN 2 THEN 'presented'
        WHEN 3 THEN 'accepted'
        WHEN 4 THEN 'released'
        WHEN 5 THEN 'exited'
        WHEN 6 THEN 'closed'
        WHEN 7 THEN 'error'
        ELSE 'draft'
    END AS state,
    
    -- FLAGS
    ExpFlgAnu AS flag_anulado,
    ExpConf AS flag_confirmado,
    ExpOriOk AS flag_origen_ok,
    ExpDesOk AS flag_destino_ok,
    
    -- METADATOS
    ExpModFec AS fecha_modificacion,
    ExpModUsu AS usuario_modificacion,
    ExpAltFec AS fecha_alta,
    ExpAltUsu AS usuario_alta
    
FROM [TuTablaExpedientes]  -- REEMPLAZAR
WHERE (ExpFlgAnu IS NULL OR ExpFlgAnu != 'S')  -- Excluir anulados
  -- AND ExpDatReg >= DATEADD(month, -3, GETDATE())  -- Últimos 3 meses (opcional)
ORDER BY ExpDatReg DESC, ExpCod DESC

-- ============================================
-- LÍNEAS DE MERCADERÍA
-- ============================================
SELECT 
    ExpCod AS expediente_code,
    ExpSegMer AS item_number,
    MerCod AS partida_arancelaria,
    LTRIM(RTRIM(ExpMerDes)) AS descripcion,
    -- Ajustar según campos reales:
    PesoBruto AS peso_bruto,
    PesoNeto AS peso_neto,
    Unidades AS unidades,
    Bultos AS bultos,
    ValorLinea AS valor_linea,
    CASE PaisOrigen 
        WHEN 1 THEN 'ES'
        WHEN 43 THEN 'AD'
        ELSE 'ES'
    END AS pais_origen
FROM [TuTablaLineasExpedientes]  -- REEMPLAZAR
WHERE ExpCod IN (
    SELECT ExpCod FROM [TuTablaExpedientes]
    WHERE (ExpFlgAnu IS NULL OR ExpFlgAnu != 'S')
)
ORDER BY ExpCod, ExpSegMer
```

---

## Orden de Importación Recomendado

1. **Partners (Remitentes y Consignatarios)**
   - Buscar por código o NIF
   - Crear si no existen
   - Actualizar datos si existen

2. **Camiones**
   - Buscar por matrícula (`ExpTrac`)
   - Crear si no existen
   - Asignar transportista y conductor

3. **Expedientes**
   - Crear con referencias a partners y camiones
   - Validar datos antes de crear

4. **Líneas de Mercancía**
   - Crear después de expedientes
   - Relacionar con expediente por `ExpCod`

---

## Notas Importantes

1. **Reemplazar nombres de tablas** en el SQL:
   - `[TuTablaExpedientes]` → Nombre real de tu tabla
   - `[TuTablaLineasExpedientes]` → Nombre real de tabla de líneas

2. **Ajustar mapeos** según tu lógica de negocio:
   - Estados (`ExpSit`)
   - Incoterms (`IcoCod`)
   - Divisas (`ExpValDiv`)

3. **Validar campos de líneas** según tu estructura real

4. **Probar con subconjunto** de datos antes de importación masiva

5. **Manejar duplicados** - verificar si `ExpCod` es único o usar combinación `ExpCod-ExpRecNum`

