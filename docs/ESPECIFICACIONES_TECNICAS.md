# Especificaciones técnicas — Historias de Usuario del Sprint 1

Responde a la recomendación del profesor en la revisión de Entrega 1:

> «Escribir la especificación técnica de las cinco historias de usuario del
> Sprint 1: endpoint y método, esquema de entrada y de salida, tablas que
> toca, reglas de validación y comportamiento ante error.»

**Fuente de esta especificación, en orden:** los Criterios de Aceptación
aprobados en `Levantamiento de Requisitos.md`, las Reglas de negocio y
Decisiones de Diseño en `claude/Sprint1_Decisiones_de_Diseno.md` (D1–D14), y
el código-esqueleto ya existente en el repositorio (routers, `casos_uso.py`,
`errors.py`, `models.py`, lectores de `ingesta/persistence/lectores/`,
`trazabilidad/persistence/consultas.py`). No se inventa ningún endpoint,
columna ni regla que no esté ya en alguna de esas fuentes: donde el código
referencia algo que no existe en los CA aprobados, se marca explícitamente
como **GAP** en vez de completarlo por cuenta propia.

Cada historia sigue el mismo esquema: endpoint y método, esquema de entrada,
esquema de salida, tablas que toca, reglas de validación, comportamiento ante
error.

---

## HU-01 — Crear un corte de seguimiento

**CA cubiertos (aprobados):** HU01-CA01 a CA08.
**Tarjetas:** `[HU-01][BE-03]` `crear_corte`, `[HU-01][BE-04]` reutilización de
fuentes, `[HU-01][BE-05]` registro/transición a REGISTRADO.

### Endpoint y método

| Operación              | Método | Ruta                     | Código éxito  |
| ---------------------- | ------ | ------------------------ | ------------- |
| Crear corte (borrador) | `POST` | `/cortes`                | `201 Created` |
| Listar histórico       | `GET`  | `/cortes`                | `200 OK`      |
| Ver detalle            | `GET`  | `/cortes/{id}`           | `200 OK`      |
| Registrar (confirmar)  | `POST` | `/cortes/{id}/registrar` | `200 OK`      |

Fuente: TODO del router `cortes/api/router.py`, ya escrito en el esqueleto.

### Esquema de entrada

`POST /cortes`

```json
{ "vigencia": 2026, "fecha_corte": "2026-08-14" }
```

`POST /cortes/{id}/registrar`: sin cuerpo (opera sobre el `id` de la ruta).

### Esquema de salida (`Corte` DTO — no la entidad ORM)

```json
{
  "id": "uuid",
  "vigencia": 2026,
  "fecha_corte": "2026-08-14",
  "estado": "BORRADOR",
  "archivos": [
    { "tipo": "PDT", "reutilizado": true, "corte_origen_id": "uuid" },
    { "tipo": "EJECUCION", "reutilizado": false, "corte_origen_id": null },
    { "tipo": "PROYECTOS", "reutilizado": true, "corte_origen_id": "uuid" }
  ]
}
```

`estado` es `BORRADOR` o `REGISTRADO` — decisión ya **RATIFICADA** como D7 en
`docs/DECISIONES.md`: el CA exige que un corte incompleto no quede registrado
(CA-3), pero CA-1/CA-3 de HU-02/03/04 asumen que ya existe un corte
identificable antes de cargarle archivos. El estado explícito resuelve la
contradicción.

### Tablas que toca

`corte` (INSERT / UPDATE de `estado`), `archivo_fuente` (INSERT al registrar,
lectura al reutilizar). Ver `cortes/persistence/models.py`.

### Reglas de validación

| Regla                                                                                                                                                                                                              | CA                                                                                                                                                                                                         | Dónde vive                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `fecha_corte` no puede ser futura                                                                                                                                                                                  | CA-2                                                                                                                                                                                                       | Dominio: `Corte.validar_fecha`                                                                             |
| No se registra si falta algún archivo obligatorio (nuevo o reutilizado)                                                                                                                                            | CA-3                                                                                                                                                                                                       | Dominio: `Corte.archivos_faltantes` / `esta_completo`                                                      |
| PDT y Proyectos (**D-04, PENDIENTE DE RATIFICAR con la clienta**: «archivo del municipio» = plantilla de Proyectos BPIN) se reutilizan automáticamente si ya existen en un corte anterior de la **misma vigencia** | CA-5, CA-6                                                                                                                                                                                                 | Aplicación: `ServicioCortes` (D-05: reutilizar es _copiar_ filas con `corte_id` nuevo, nunca compartirlas) |
| El archivo de EJECUCIÓN nunca se reutiliza, se solicita siempre                                                                                                                                                    | CA-7                                                                                                                                                                                                       | Aplicación                                                                                                 |
| A lo sumo un borrador por vigencia                                                                                                                                                                                 | SUPERADA por `docs/DECISIONES.md` D9 (RATIFICADA, 2026-09-13): el criterio de unicidad es vigencia + fecha_corte exacta, no vigencia sola. Ver también D11 (RATIFICADA): un solo BORRADOR activo a la vez. | —                                                                                                          |

### Comportamiento ante error

| Caso                                                       | Código | Excepción de dominio                                                                                        |
| ---------------------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------- |
| Fecha futura                                               | `422`  | `ReglaDeNegocioViolada` (mensaje indica qué regla)                                                          |
| Falta un archivo obligatorio al registrar                  | `409`  | `OperacionNoPermitida` (estado inválido para la transición) — el mensaje debe indicar **cuál** falta (CA-3) |
| Corte no existe (`GET /cortes/{id}`, `POST .../registrar`) | `404`  | `RecursoNoEncontrado`                                                                                       |

---

## HU-02 — Cargar el Plan Indicativo (PDT)

**CA cubiertos (aprobados):** HU02-CA01 a CA06 (renumerados el 2026-09-08 —
CA-1 es nuevo, ver `docs/DECISIONES.md`, D6).
**Tarjetas:** `[HU-02][FE-01]`/`[BE-04]` acceso y carga (CA-1), `[BE-01]`
localización de pestaña (CA-2), `[BE-02]` validación de columnas (CA-3),
`[BE-03]` detección de archivo incorrecto (CA-4).

### Endpoint y método

`POST /cortes/{id}/archivos/PDT` — carga o reemplaza (HU-06) el archivo PDT
del corte. `multipart/form-data`, campo `archivo`. Éxito: `200 OK` (reemplazo)
o `201 Created` (primera carga).

### Esquema de entrada

Archivo `.xlsx` (`multipart/form-data`); nombre de archivo no se usa como
identificador funcional, solo se sanitiza por seguridad ([SEC-03]).

### Esquema de salida

```json
{
  "tipo": "PDT",
  "metas_reconocidas": 144,
  "advertencias": []
}
```

`metas_reconocidas` es el número que CA-5 exige mostrar («confirma
visualmente cuántas metas fueron reconocidas»).

### Tablas que toca

`meta` (INSERT, `corte_id`, `cod_indicador_producto` **VARCHAR(9)**, nunca
INTEGER — D-02), columna `es_principal BOOLEAN NOT NULL` (D-06, **pendiente
de confirmar con la clienta qué significa "Principal" en el dominio**).

### Reglas de validación

| Regla                                                                                                                                               | CA                                               | Dónde vive                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| La administradora puede seleccionar el Plan Indicativo del corte                                                                                    | CA-1                                             | `cortes/api/router.py`, `casos_uso.py::cargar_archivo`                                             |
| Reconocer específicamente la pestaña **"Plan indicativo - Productos"** entre las 6 que trae el archivo real; no interpretar las otras 5             | CA-2                                             | `lectores/_comun.resolver_hoja` + `pdt.ALIAS_HOJA`                                                 |
| El encabezado real está en una fila variable (fila 2 en el archivo medido); localizarlo buscando las columnas requeridas, no un número de fila fijo | Regla de negocio (peculiaridad 1 de `_comun.py`) | `_comun.localizar_fila_encabezado`                                                                 |
| Columnas mínimas: código de indicador (MGA), meta programada por vigencia, marca "Principal"                                                        | CA-3                                             | `pdt.OBLIGATORIAS` (**pendiente de completar en código** — hoy es `{}`) + `_comun.exigir_columnas` |
| Toda lectura de columnas de código con `dtype=str` (preserva ceros a la izquierda: 4 códigos reales empiezan en 0)                                  | D-02                                             | `_comun` (lector)                                                                                  |

### Comportamiento ante error

| Caso                                                                   | CA       | Código        | Excepción                                                                                             |
| ---------------------------------------------------------------------- | -------- | ------------- | ----------------------------------------------------------------------------------------------------- |
| Falta alguna columna mínima                                            | CA-3     | `422`         | `ArchivoInvalido` — mensaje indica **qué columna(s)** faltan; rechazo **total**, sin datos parciales  |
| El archivo no es un PDT (p. ej. suben el de ejecución)                 | CA-4     | `422`         | `ArchivoInvalido` — mensaje indica que no corresponde al formato esperado, **sin adivinar contenido** |
| Extensión/firma de archivo inválida, tamaño excedido, macros (`.xlsm`) | [SEC-03] | `422`         | `ArchivoInvalido`                                                                                     |
| Corte no existe o no está en `BORRADOR`                                | —        | `404` / `409` | `RecursoNoEncontrado` / `OperacionNoPermitida`                                                        |

---

## HU-03 — Cargar el archivo presupuestal (ejecución + contratación)

**CA cubiertos (aprobados):** HU03-CA01 a CA07 (renumerados el 2026-09-08 —
CA-1 es nuevo, `CA-7` [ceros a la izquierda] se movió al final; ver
`docs/DECISIONES.md`, D6).
**Tarjetas:** `[HU-03][BE-06]`/`[FE-01]` acceso y carga (CA-1), `[BE-01]` lector
de dos pestañas (CA-2), `[BE-03]` unificación de nombres de columna (CA-3),
`[BE-04]` validación de ambas pestañas (CA-4), `[BE-05]` archivo incorrecto
(CA-5), `[BE-02]` ceros a la izquierda (CA-7).

### Endpoint y método

`POST /cortes/{id}/archivos/EJECUCION` — `multipart/form-data`, campo
`archivo`. Un solo archivo con dos pestañas, **no dos endpoints** (CA-2: "sin
exigir que se carguen por separado"). Éxito: `200`/`201` igual que HU-02.

### Esquema de entrada

Archivo `.xlsx` con las pestañas `EJECUCION` (nombre real en archivo medido:
`Formato Resumido Ejecucion Gast`, truncado por Excel a 31 caracteres — D-14)
y `CONTRATACION`.

### Esquema de salida

```json
{
  "tipo": "EJECUCION",
  "filas_ejecucion_reconocidas": 374,
  "filas_contratacion_reconocidas": 270,
  "advertencias": []
}
```

`filas_ejecucion_reconocidas` cuenta solo hojas (`ultimo_nivel = true`);
los 111 subtotales medidos se excluyen de este conteo igual que del cruce
(D-09), para no sugerir un volumen de datos inflado.

### Tablas que toca

`rubro` (INSERT, `codigo_rubro_nivel` como llave real — D-10 — y
`ultimo_nivel BOOLEAN NOT NULL`), `contrato` (INSERT, 270 contratos únicos —
no duplicar por cada registro presupuestal) y `registro_presupuestal` (INSERT,
puente N:1 hacia `contrato`; **D-11, deuda técnica documentada**: sin
restricción UNIQUE, 45 filas repetidas `(numero_contrato, numero_registro)`
con rubros distintos en el archivo real — pendiente de confirmar con
Tesorería/clienta si es un defecto de origen o un caso válido).

### Reglas de validación

| Regla                                                                                                                      | CA                                | Dónde vive                             |
| -------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | -------------------------------------- |
| La administradora puede cargar el archivo presupuestal del corte                                                           | CA-1                              | `cortes/api/router.py`, `casos_uso.py` |
| Procesar EJECUCION y CONTRATACION como conjuntos independientes, en la misma carga                                         | CA-2                              | `ejecucion.py`                         |
| Tratar `CodigoIndicadorCcpet` (ejecución) y `Cod Indicador Ccpet` (contratación) como el mismo dato, sin duplicar columnas | CA-3                              | `_comun.mapear_columnas` por alias     |
| Preservar ceros a la izquierda del código de indicador (9 dígitos)                                                         | CA-7                              | `dtype=str` en toda la lectura (D-02)  |
| Resolver la pestaña de ejecución por alias/prefijo, no por nombre exacto (el archivo real trunca a 31 caracteres)          | D-14                              | `_comun.resolver_hoja`                 |
| Montos en formato colombiano (`$ 1.218.264.452`, `133200000`) se parsean a `Decimal`, nunca `float`                        | Regla de negocio (peculiaridad 5) | `_comun.numero`                        |

### Comportamiento ante error

| Caso                                                           | CA   | Código        | Excepción                                            |
| -------------------------------------------------------------- | ---- | ------------- | ---------------------------------------------------- |
| Falta la pestaña EJECUCION o CONTRATACION                      | CA-4 | `422`         | `ArchivoInvalido` — indica **cuál** de las dos falta |
| Archivo no corresponde al presupuestal (suben PDT o Proyectos) | CA-5 | `422`         | `ArchivoInvalido`                                    |
| Corte no existe / no está en `BORRADOR`                        | —    | `404` / `409` | `RecursoNoEncontrado` / `OperacionNoPermitida`       |

---

## HU-04 — Cargar la plantilla de proyectos BPIN

**CA cubiertos (aprobados):** HU04-CA01 a CA05 (renumerados el 2026-09-08 —
CA-1 es nuevo; ver `docs/DECISIONES.md`, D6).
**Tarjetas:** `[HU-04][FE-01]`/`[BE-04]` acceso y carga (CA-1), `[BE-01]`
almacenamiento tal cual (CA-2), `[BE-02]` extracción acotada (CA-3), `[BE-03]`
separación de celdas combinadas (CA-4).

Este lector es **deliberadamente más permisivo** que los otros dos: CA-2 exige
almacenar el archivo «tal cual», «incluso si su estructura interna no está
completamente estandarizada», y CA-3 acota la extracción a BPIN + indicador de
producto «sin validar el resto». La tarjeta lleva la etiqueta _"Pendiente de
estandarización de fuente"_ — esto es una regla de negocio confirmada, no una
laxitud accidental del lector.

### Endpoint y método

`POST /cortes/{id}/archivos/PROYECTOS` — `multipart/form-data`, campo
`archivo`. Éxito: `200`/`201`.

### Esquema de entrada

Archivo `.xlsx`, una sola pestaña sin nombre estándar (en el archivo real:
`"2026"`); se prueba cada hoja y se toma la primera que tenga las columnas
requeridas.

### Esquema de salida

```json
{
  "tipo": "PROYECTOS",
  "proyectos_reconocidos": 38,
  "indicadores_extraidos": 67,
  "descartes": [
    {
      "fragmento": "459903100\nEntidades... \n$ 1.218.264.452",
      "motivo": "..."
    }
  ]
}
```

`descartes` responde a `[HU-04][FE-03]`: la pantalla de vista previa necesita
saber qué se descartó y por qué — «los descartes son la información más
valiosa de esa pantalla» (comentario del propio lector).

### Tablas que toca

`proyecto` (INSERT, BPIN sin normalizar — uno de los 38 reales no cumple el
formato de 15 dígitos y se conserva tal cual, CA-2 — sin cambio, ya era CA-2 en
el código original) y `proyecto_indicador`
(INSERT, N:M entre proyecto e indicador — D-07: la separación de celdas
multivalor **no** es un `split("\n")` ingenuo, sino extracción por patrón de 9
dígitos aislados, para no confundir nombres/montos con códigos, ni un BPIN de
15 dígitos con un falso indicador de 9).

### Reglas de validación

| Regla                                                                                                              | CA                                               | Dónde vive                                                                           |
| ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ | ------------------------------------------------------------------------------------ |
| La administradora puede cargar la plantilla BPIN del corte                                                         | CA-1                                             | `cortes/api/router.py`, `casos_uso.py`                                               |
| Extraer solo BPIN e indicador de producto; no validar ni rechazar por el resto de columnas                         | CA-3                                             | `proyectos.OBLIGATORIAS` (ya declaradas en código: `bpin`, `indicador_producto_raw`) |
| Separar automáticamente indicadores multivalor de una celda                                                        | CA-4                                             | `_comun.rellenar_celdas_combinadas` + extracción por patrón (D-07)                   |
| Propagar hacia abajo el valor de celdas combinadas verticalmente (una fila de proyecto + N filas de solo-contrato) | Regla de negocio (221 rangos combinados medidos) | `_comun.rellenar_celdas_combinadas`                                                  |

### Comportamiento ante error

| Caso                                                            | CA                                                                  | Código        | Excepción                                      |
| --------------------------------------------------------------- | ------------------------------------------------------------------- | ------------- | ---------------------------------------------- |
| No se puede ubicar BPIN o indicador de producto en ninguna hoja | CA-2/CA-3 (implícito: sin esas dos columnas no hay «tal cual» útil) | `422`         | `ArchivoInvalido`                              |
| Corte no existe / no está en `BORRADOR`                         | —                                                                   | `404` / `409` | `RecursoNoEncontrado` / `OperacionNoPermitida` |

**Nota:** a diferencia de HU-02/HU-03, este archivo **no se rechaza** por
estructura interna no estandarizada (CA-2) — solo por no poder ubicar las dos
columnas mínimas. No se debe portar aquí la severidad de HU-02-CA04/HU-03-CA05
("archivo incorrecto"): no está en los CA aprobados para HU-04.

---

## HU-07 — Visualizar la matriz de relación del corte actual

**CA cubiertos: HU07-CA01 a CA08 (reconciliados el 2026-09-08 con el checklist
de Trello y con `Levantamiento de Requisitos.md`) — ver `docs/DECISIONES.md`,
D5.**

Antes de la reconciliación, `Levantamiento de Requisitos.md` solo tenía
HU07-CA01 y HU07-CA04, y el código (`consultas.py`, `trazabilidad/api/router.py`)
referenciaba "CA-2 a CA-8" como si ya existieran formalmente. No eran
criterios inventados: sí existían, en el checklist "Criterios de aceptación"
de la tarjeta de Trello de HU-07, solo que nunca se habían volcado al
documento de requisitos. Ya se corrigió esa numeración en las tres fuentes.
Lo que existía como "HU07-CA04" original (unificación de nombres de columna
del indicador) se fusionó con CA-2 por decisión del equipo: es la misma regla
que HU03-CA02, ya garantizada en la ingesta — la matriz solo lee un dato ya
unificado, no unifica nada por su cuenta.

### Endpoint y método

| Operación                     | Método | Ruta                                                 | Código éxito |
| ----------------------------- | ------ | ---------------------------------------------------- | ------------ |
| Matriz del corte actual       | `GET`  | `/matriz-relacion/actual?pagina=&tamano_pagina=`     | `200 OK`     |
| Matriz de un corte específico | `GET`  | `/matriz-relacion/{corte_id}?pagina=&tamano_pagina=` | `200 OK`     |

Implementa CA-1 (acceso a la matriz del corte actual). La paginación en sí
no tiene un CA propio, pero es la forma en que CA-1 se cumple sin romper
rendimiento: el cruce real produce miles de combinaciones (D-08).

### Esquema de entrada

Query params: `pagina` (default 1), `tamano_pagina` (default 50).

### Esquema de salida

```json
{
  "corte_id": "uuid",
  "pagina": 1,
  "tamano_pagina": 50,
  "total_filas": 187,
  "filas": [
    {
      "cod_bpin": "2026760010123",
      "cod_indicador_producto": "040600400",
      "nombre_producto": "...",
      "cod_indicador_ejecucion": "040600400",
      "numero_contrato": null,
      "descripcion_contrato": null
    }
  ]
}
```

Las seis columnas cubren CA-3 (BPIN), CA-4 (indicador/producto), CA-5
(ejecución) y CA-6 (contrato) por separado. `null` explícito (nunca `""`, `0`
ni `"N/A"`) cuando no hubo correspondencia — regla de CA-8, ya validada con
datos reales: de 144 metas, 119 tienen ejecución, 67 tienen proyecto con
BPIN, 40 tienen contrato, **24 no cruzan con ninguna fuente** (D-01) y deben
seguir apareciendo en la matriz.

### Tablas que toca (solo lectura — es una consulta, no una tabla, D-08)

`meta` JOIN `proyecto_indicador`/`proyecto` (por `cod_indicador_producto`),
LEFT JOIN `rubro` (filtrado por `ultimo_nivel = true`, D-09) LEFT JOIN
`registro_presupuestal` (deduplicado por `(rubro_id, contrato_id)`, no por
`DISTINCT` sobre el resultado final — ver regla de CA-7 más abajo) LEFT JOIN
`contrato`. Todo acotado a un `corte_id`. La lectura de las fuentes ya
procesadas (CA-2) implica que esta consulta nunca vuelve a abrir los archivos
Excel originales.

### Reglas de validación / construcción

| Regla                                                                                                                 | CA                                                     | Detalle                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Usar información ya procesada y persistida de las fuentes, sin releer los Excel                                       | CA-2                                                   | La consulta solo lee tablas ya cargadas por HU-02/03/04                                                                                                                                                                                                                                                                                                                                         |
| Filtrar `ultimo_nivel = true` en `rubro`                                                                              | Regla de negocio (D-09, confirmada con evidencia)      | Sin el filtro, cada meta se emparejaría también con el subtotal que la contiene — infla la matriz y el dinero en cualquier suma posterior                                                                                                                                                                                                                                                       |
| Todos los JOIN son LEFT                                                                                               | CA-8                                                   | Ninguna asociación ficticia; el `NULL` explícito es el insumo de las alertas de E-04/HU-05                                                                                                                                                                                                                                                                                                      |
| No colapsar relaciones múltiples (prohibido `DISTINCT`, `LIMIT 1`, `first()` sobre el resultado final)                | CA-7                                                   | Un indicador con 2 BPIN debe mostrar ambos; un BPIN con 3 indicadores, los tres. El _único_ `DISTINCT` permitido es sobre el puente `(rubro_id, contrato_id)` de `registro_presupuestal`, para no generar fan-out por los 1..N registros presupuestales de un mismo contrato (no es una violación de la regla: la deduplicación es sobre el puente, no sobre las columnas que expone la matriz) |
| Acotar `proyecto_indicador` al `corte_id` **dentro** de la subconsulta de proyectos, no encadenando LEFT JOIN sueltos | Regla de negocio (evita fila fantasma cruzando cortes) | `proyecto_indicador` no tiene `corte_id` propio; lo hereda de `proyecto`                                                                                                                                                                                                                                                                                                                        |
| Unificar `CodigoIndicadorCcpet`/`Cod Indicador Ccpet` sin duplicar columnas ni perder filas                           | CA-2 (fusionada con la unificación de HU03-CA02)       | Ya resuelto en la capa de ingesta (HU-03/CA-02, D-01); esta consulta solo lee la columna ya unificada — no vuelve a unificar nada                                                                                                                                                                                                                                                               |

### Comportamiento ante error

| Caso                                                    | Código | Excepción                                               |
| ------------------------------------------------------- | ------ | ------------------------------------------------------- |
| El corte no existe o no tiene ningún archivo registrado | `404`  | `RecursoNoEncontrado`                                   |
| `pagina`/`tamano_pagina` inválidos (≤0, no numéricos)   | `422`  | Validación Pydantic en la capa API (no llega a dominio) |

---

## Resumen — comportamiento ante error común a las 4 cargas de archivo (HU-02/03/04)

Regla transversal de `[SEC-03]`, capa de Aplicación (no en la API, no
repetida por caso de uso):

1. Extensión declarada vs. MIME/firma real del contenido (`.xlsx` = ZIP, debe
   empezar por `PK`).
2. Tamaño máximo configurable, verificado **antes** de leer el archivo
   completo en memoria.
3. Sanitización del nombre de archivo (path traversal).
4. Rechazo de libros con macros (`.xlsm`).
5. Verificación de que las hojas obligatorias existen **antes** de procesar.

Cualquier violación de estas reglas produce `422` con `ArchivoInvalido`, antes
de que el pipeline ETL intente leer el contenido. Nunca se expone el
traceback interno al cliente (mismo principio de `[SEC-03]` en
`docs/SEGURIDAD.md`).

---

## `[UX-02]` — Requisitos de interfaz del control de carga de archivo

`components/CargaDeArchivo.jsx`, compartido por `[HU-02][FE-02]`,
`[HU-03][FE-02]`, `[HU-04][FE-02]`. Contrato mínimo de interfaz (todo es
ayuda de UX; la validación real sigue siendo `[SEC-03]` en el backend):

1. Selección por clic (`<input type="file">`) **y** por arrastrar-soltar
   sobre la misma zona — el arrastre es un atajo adicional, nunca reemplaza
   el input ni rompe el uso por teclado.
2. Indicador de progreso durante la subida.
3. Límite de tamaño verificado en cliente: **2.097.152 bytes (2 MB)**,
   acordado con Cristhian sobre archivos reales hoy < 200 KB (ver
   `docs/DECISIONES.md` D12). Menor que el límite real del backend (25 MB,
   `config.py::max_upload_bytes`) — es un aviso más conservador, no la
   fuente de verdad.

---

## Gaps detectados al escribir esta especificación (no resueltos aquí)

| #   | Gap                                                                                                            | Por qué importa                                                                                                                                       | A quién le toca decidir                                                                                                                                   |
| --- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `pdt.OBLIGATORIAS` y las dos `OBLIGATORIAS_*` de `ejecucion.py` están declaradas vacías (`{}`) en el esqueleto | Sin completarlas, `exigir_columnas` no puede rechazar nada — HU02-CA02 y HU03-CA04 quedarían sin cumplir aunque el resto del lector esté implementado | Quien tome esas tarjetas (`[HU-02][BE-02]`, `[HU-03][BE-04]`) — completarlas con los alias reales documentados en los propios docstrings de esos archivos |

No quedan gaps abiertos sobre la numeración de CA de HU-01/HU-07: se
reconciliaron con Trello y la fila que existía como "HU07-CA04" original se
fusionó con CA-2 (ver `docs/DECISIONES.md`, D5). El gap 1 no es ambigüedad
CRÍTICA de esquema, seguridad o regla financiera, así que no bloquea empezar
a codificar, pero debe quedar resuelto antes de dar por terminadas HU-02 y
HU-03, según la Definición de Terminado del proyecto.
