# Manual de Uso — Cuaderno de Campo de Explotación (CUE)

> Manual para agricultores y técnicos de explotación. Explica el flujo de trabajo del cuaderno de campo digital conforme al RD 1054/2022 (SIEX).

## Índice

1. [Conceptos básicos](#conceptos-básicos)
2. [Flujo de trabajo](#flujo-de-trabajo)
3. [Operaciones paso a paso](#operaciones-paso-a-paso)
4. [Referencia de campos](#referencia-de-campos)
5. [Validaciones](#validaciones)
6. [Resolución de problemas](#resolución-de-problemas)

---

## Conceptos básicos

El Cuaderno de Explotación Único (CUE) es el registro digital obligatorio para toda explotación agrícola en España. Sustituye al antiguo cuaderno de campo en papel. Su estructura se organiza en cuatro niveles jerárquicos:

```
EXPLOTACIÓN AGRÍCOLA
  │
  ├── UNIDAD DE PRODUCCIÓN (parcela cultivable)
  │     │
  │     └── LÍNEA DE DECLARACIÓN (cultivo declarado por campaña)
  │           │
  │           └── RECINTO SIGPAC (superficie con geometría)
  │
  └── ... (más unidades de producción)
```

### Definiciones

- **Explotación agrícola** (`AgriFarm`): El conjunto de tierras, instalaciones y medios de producción gestionados por un mismo titular. Equivale a una "empresa agrícola". Se identifica por el NIF del titular y tiene una ubicación (coordenadas de la sede).

- **Unidad de producción** (`AgriParcel`): Cada parcela o grupo de parcelas cultivables dentro de la explotación. Tiene un cultivo principal, un sistema de riego y una superficie total.

- **Línea de declaración** (`AgriCropDeclaration`): El cultivo concreto declarado para una campaña (año agrícola). Una misma unidad de producción puede tener distintas declaraciones en distintas campañas.

- **Recinto SIGPAC** (`SigpacEnclosure`): La superficie geográfica concreta dentro de una línea de declaración. Cada recinto tiene una geometría (polígono), una referencia SIGPAC oficial y una superficie admisible (descontando elementos no cultivables como rocas, caminos, etc.).

### Jerarquía obligatoria

Para crear un recinto SIGPAC, debes tener creados previamente:
1. La explotación
2. La unidad de producción
3. La línea de declaración

No es posible saltarse niveles. El sistema valida que cada entidad referencie correctamente a su entidad padre.

---

## Flujo de trabajo

### Flujo típico de un agricultor

```
1. ALTA INICIAL (una sola vez por explotación)
   Crear explotación → Crear unidades de producción

2. CADA CAMPAÑA (anual)
   Crear líneas de declaración → Crear recintos SIGPAC → Registrar tratamientos*

3. MODIFICACIONES (bajo demanda)
   Rectificar datos erróneos → Versionar registros → Enviar a administración*
```

\* *Fases 2+ (no disponible en Fase 1)*

### Flujo recomendado para campaña nueva

La forma más eficiente de preparar una nueva campaña es:

1. **Duplicar** las líneas de declaración del año anterior (`POST /declaraciones/<id>/duplicar`)
2. **Revisar** los datos duplicados (cambios de cultivo, ajustes de superficie)
3. **Crear en lote** los recintos SIGPAC (`POST /recintos/batch`)

---

## Operaciones paso a paso

### 1. Crear una explotación

```http
POST /api/modules/cue/explotaciones
Content-Type: application/json
Authorization: Bearer <jwt>
X-Tenant-ID: <tenant>

{
  "nombre": "Finca Los Olivos",
  "descripcion": "Explotación de olivar en secano, 15 ha",
  "municipio": "Tudela",
  "provincia": "Navarra",
  "nif": "12345678Z",
  "coordenadas": [-1.606, 42.065]
}
```

**Campos obligatorios:** `nombre`.
**Campos recomendados:** `municipio`, `provincia` (permiten filtrar en búsquedas).
**Coordenadas:** Formato `[longitud, latitud]` (EPSG:4326 / WGS84).

### 2. Crear unidades de producción

Para cada parcela cultivable de la explotación:

```http
POST /api/modules/cue/parcelas
Content-Type: application/json

{
  "nombre": "Parcela Norte - Olivar",
  "explotacion_id": "<id_de_la_explotacion>",
  "cultivo": "olivo",
  "area_ha": 5.2,
  "riego": "goteo",
  "estado": "activo"
}
```

**Campos obligatorios:** `nombre`, `explotacion_id` (el ID devuelto al crear la explotación).

**Sistemas de riego recomendados:** `secano`, `goteo`, `aspersion`, `inundacion`, `enterrado`.

### 3. Crear líneas de declaración

Una por cada cultivo y campaña:

```http
POST /api/modules/cue/declaraciones
Content-Type: application/json

{
  "parcela_id": "<id_de_la_parcela>",
  "campanya": 2026,
  "cultivo": "OLV",
  "superficie_ha": 4.8
}
```

**Campaña:** Año agrícola (número entero). La campaña 2026 corresponde a la temporada 2025-2026.

**Cultivo:** Se recomienda usar el código oficial SIGPAC (ej. `OLV` para olivar, `TRG` para trigo).

### 4. Duplicar declaración de una campaña anterior

```http
POST /api/modules/cue/declaraciones/<id_declaracion_2025>/duplicar
Content-Type: application/json

{
  "campanya": 2026
}
```

Esto crea una copia exacta de la declaración para la nueva campaña, conservando el cultivo, la superficie y la relación con la parcela. Si no se especifica `campanya`, se usa automáticamente el año siguiente al de la declaración original.

### 5. Crear recintos SIGPAC

**Individual:**

```http
POST /api/modules/cue/recintos
Content-Type: application/json

{
  "declaracion_id": "<id_de_la_declaracion>",
  "referencia_sigpac": "31:230:0:0:0:243:9003",
  "superficie_admisible_ha": 4.5,
  "geometria": {
    "type": "Polygon",
    "coordinates": [[
      [-1.606, 42.065],
      [-1.604, 42.065],
      [-1.604, 42.067],
      [-1.606, 42.067],
      [-1.606, 42.065]
    ]]
  }
}
```

**En lote (recomendado para >5 recintos):**

```http
POST /api/modules/cue/recintos/batch
Content-Type: application/json

{
  "recintos": [
    {
      "declaracion_id": "<id>",
      "referencia_sigpac": "31:230:0:0:0:243:9003",
      "superficie_admisible_ha": 4.5,
      "geometria": { "type": "Polygon", "coordinates": [...] }
    },
    {
      "declaracion_id": "<id>",
      "referencia_sigpac": "31:230:0:0:0:243:9004",
      "superficie_admisible_ha": 3.2,
      "geometria": { "type": "Polygon", "coordinates": [...] }
    }
  ]
}
```

La respuesta indica cuántos se crearon correctamente y detalla los errores individuales:

```json
{
  "total": 2,
  "created": 2,
  "errors": 0,
  "results": [
    {"id": "abc123", "status": "created"},
    {"id": "def456", "status": "created"}
  ],
  "error_details": null
}
```

### 6. Consultar recintos con geometrías

```http
GET /api/modules/cue/declaraciones/<id>/recintos
```

Devuelve la lista de recintos enriquecida con geometrías GeoJSON desde la caché espacial PostGIS.

### 7. Filtrar explotaciones

```http
GET /api/modules/cue/explotaciones?municipio=Tudela&nombre=Olivos
```

Filtros disponibles:
- `municipio` — coincidencia exacta con el municipio de la explotación
- `nombre` — búsqueda por patrón (coincidencia parcial)

### 8. Actualizar y eliminar

Todas las entidades soportan:
- **PUT** para modificación parcial (solo los campos enviados se actualizan)
- **DELETE** para baja lógica (la entidad se marca como inactiva pero no se borra físicamente — trazabilidad legal)

---

## Referencia de campos

### Explotación (AgriFarm)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `nombre` | string | Sí | Nombre de la explotación |
| `descripcion` | string | No | Descripción libre |
| `contacto` | string | No | Datos de contacto del titular |
| `municipio` | string | Recomendado | Municipio donde radica la explotación |
| `provincia` | string | Recomendado | Provincia |
| `nif` | string | Recomendado | NIF del titular (genera relación `ownedBy`) |
| `coordenadas` | [lng, lat] | No | Coordenadas de la sede (WGS84) |

### Unidad de producción (AgriParcel)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `nombre` | string | Sí | Nombre descriptivo de la parcela |
| `explotacion_id` | string | Sí | ID de la explotación a la que pertenece |
| `cultivo` | string | Recomendado | Cultivo principal (ej. "olivo", "trigo") |
| `area_ha` | number | Recomendado | Superficie total en hectáreas |
| `riego` | string | No | Sistema de riego |
| `estado` | string | No | Estado del cultivo ("activo" por defecto) |

### Línea de declaración (AgriCropDeclaration)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `parcela_id` | string | Sí | ID de la unidad de producción |
| `campanya` | integer | Sí | Año de la campaña (ej. 2026) |
| `cultivo` | string | Recomendado | Código de cultivo (preferiblemente código SIGPAC) |
| `superficie_ha` | number | Recomendado | Superficie declarada en hectáreas |

### Recinto SIGPAC (SigpacEnclosure)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `declaracion_id` | string | Sí | ID de la línea de declaración |
| `geometria` | GeoJSON Polygon | Sí | Polígono en formato GeoJSON (EPSG:4326) |
| `referencia_sigpac` | string | Recomendado | Referencia catastral SIGPAC (formato REFCATAST) |
| `superficie_admisible_ha` | number | Recomendado | Superficie elegible en hectáreas (descuenta elementos no cultivables) |

### Formato REFCATAST

La referencia SIGPAC sigue el formato: `provincia:mun:agreg:zona:pol:parc:rec`

Ejemplo: `31:230:0:0:0:243:9003`

- `31` — Código de provincia (Navarra)
- `230` — Código de municipio
- `0:0:0` — Agregado, zona, polígono
- `243` — Parcela
- `9003` — Recinto

---

## Validaciones

### Geometría de recinto

Todo polígono GeoJSON enviado al sistema se valida con las siguientes reglas:

1. **Tipo correcto:** Debe ser `"Polygon"` (no se admiten MultiPolygon, Point, etc.)
2. **Anillo cerrado:** El primer y último punto del anillo exterior deben ser idénticos
3. **Mínimo de puntos:** El anillo exterior debe tener al menos 4 puntos
4. **Coordenadas numéricas:** Todos los valores deben ser números (no texto, no nulos)
5. **Latitud dentro de [-90, 90]**, **longitud dentro de [-180, 180]**

### Jerarquía de entidades

- No se puede crear un recinto sin línea de declaración
- No se puede crear una línea de declaración sin unidad de producción
- No se puede crear una unidad de producción sin explotación
- La API devuelve error si la entidad referenciada no existe en Orion-LD

### Tenencia de datos

- Cada entidad pertenece a un tenant (definido por `X-Tenant-ID`)
- Un tenant no puede ver ni modificar las entidades de otro tenant
- Las consultas siempre filtran por `isActive=true` (las entidades eliminadas no aparecen)

---

## Resolución de problemas

### "Falta cabecera de autorización o es inválida" (401)

Causa: El token JWT no se ha enviado o ha expirado.
Solución: Renovar la sesión (logout/login) y reenviar la petición con el nuevo token.

### "No se encontró el ID del tenant" (401)

Causa: Falta la cabecera `X-Tenant-ID` o el token JWT no contiene `tenant_id`.
Solución: Asegurar que la petición incluye `X-Tenant-ID` con el identificador de la explotación.

### "Geometría inválida: ..." (400)

Causa: El polígono enviado no cumple las reglas de validación.
Soluciones frecuentes:
- Verificar que el polígono está cerrado (primer punto = último punto)
- Verificar que las coordenadas son números (no strings)
- Verificar que latitud y longitud están en los rangos correctos
- El formato correcto es `{"type": "Polygon", "coordinates": [[[lng, lat], ...]]]}` (doble array)

### "El token ha expirado" (401)

Causa: La sesión JWT ha caducado.
Solución: Cerrar sesión y volver a autenticarse.

### "Orion-LD inaccesible" (502)

Causa: El Context Broker no responde (problema de infraestructura).
Solución: Reintentar en unos minutos. Si persiste, contactar con soporte técnico.

### Los recintos se crean pero no aparecen sus geometrías

Causa: La sincronización Orion-LD → PostGIS es asíncrona. Puede tardar unos segundos.
Solución: Esperar 2-3 segundos y volver a consultar. Si tras 30 segundos sigue sin aparecer, verificar que la suscripción de Orion-LD está configurada.

---

## Glosario

| Término | Definición |
|---------|------------|
| **CUE** | Cuaderno de Explotación Único |
| **SIEX** | Sistema de Información de Explotaciones Agrícolas |
| **SIGPAC** | Sistema de Información Geográfica de Parcelas Agrícolas |
| **REFCATAST** | Formato de referencia catastral oficial |
| **Recinto** | Superficie continua de terreno dentro de una parcela SIGPAC con un uso único |
| **Superficie admisible** | Superficie elegible para ayudas PAC (descuenta rocas, caminos, etc.) |
| **Campaña** | Año agrícola. La campaña 2026 cubre desde otoño 2025 hasta verano 2026 |
| **ROPO** | Registro Oficial de Productos y Operadores (fitosanitarios) |
| **NGSI-LD** | Estándar ETSI para intercambio de datos de contexto (usado por FIWARE) |
| **SDM** | Smart Data Model — modelo de datos estandarizado de FIWARE |
| **EPSG:4326** | Sistema de coordenadas WGS84 (latitud/longitud), usado en GPS y mapas web |

---

## Cumplimiento normativo

Este módulo implementa los requisitos del **Real Decreto 1054/2022** de 27 de diciembre, por el que se establece el sistema de información de explotaciones agrícolas (SIEX) y se regula el cuaderno digital de explotación agrícola.

La arquitectura sigue el estándar **NGSI-LD** (ETSI ISG CIM) y utiliza modelos de datos **FIWARE Smart Data Models** para las entidades interoperables.

Organismo responsable en España: **FEGA** (Fondo Español de Garantía Agraria, MAPA).

---

*NKZ-MODULE-CUE — AGPL-3.0 — Nekazari / robotika.cloud*
