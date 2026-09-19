# Decisiones de diseño y alcance — GovSync

Registro de decisiones tomadas por el equipo, con su evidencia y su estado.
Formato por entrada: **Decisión**, **Motivo/Evidencia**, **Alternativas consideradas**,
**Estado**, **Quién y cuándo**.

---

## D1 · La migración de Alembic es la única fuente de verdad del esquema

**Decisión:** el esquema vigente es el que resulta de las migraciones en
`backend/alembic/versions/`. Los archivos `govsync_schema.sql`,
`govsync_schema2.sql` y `govsync_schema_con_auditoria.sql` quedan como material
histórico de diseño, no como fuente ejecutable.

**Motivo:** circulaban tres `.sql` distintos más un diagrama E/R paralelo sin
reconciliar (señalado en `PLANDETRABAJO.md`, D1). Mientras no se decida, dos
personas pueden construir sobre esquemas distintos sin darse cuenta.

**Alternativas consideradas:** mantener uno de los `.sql` como fuente y
generar la migración a partir de él — descartada porque el equipo ya tiene el
hábito de trabajar con `alembic revision --autogenerate`, y mantener dos
fuentes sincronizadas a mano es más frágil que tener una sola.

**Estado:** RATIFICADA — el equipo confirmó la propuesta (`[REF-01]`, tarjeta
movida a "Tareas hechas" en Trello).

**Registrado:** 2026-09-08 (propuesta, a partir del análisis de `PLANDETRABAJO.md`).
**Ratificado:** 2026-09-08 por el equipo.

---

## D2 · Autenticación (E-01) diferida al Sprint 2

**Decisión:** las Historias de Usuario de la épica E-01 (Gestión de Acceso y
Roles) no entran al Sprint 1. El esqueleto no incluye módulo de identidad ni
JWT. Las filas "Autenticación" y "Autorización" de la Tabla 4 (OWASP) de la
rúbrica del Sprint 1 quedan como **N/A con esta justificación**, no vacías.

**Motivo:** el Sprint Backlog comprometido en la Entrega 1 (Tabla 8 del
documento de Entrega 1) ya fijó 5 Historias de Usuario con story points
específicos (8, 3, 8, 13, 5 = 37 SP), ninguna de la épica E-01. Agregar
autenticación ahora significa sumar alcance no comprometido con el docente
sin haber replanificado la capacidad del equipo.

**Alternativas consideradas:** adelantar E-01 al Sprint 1 — evaluada y
descartada por ahora; ver la nota siguiente.

**Si se revierte esta decisión:** es una tarjeta nueva (`[HU-E01-01]`,
~5 SP) que entra en Fase 2 y toca `core/dependencias.py` más un módulo
nuevo `modules/identidad/`. Además, `Levantamiento de Requisitos.md` ya
tiene el enunciado de E-01/HU-01 y HU-02, pero **no tiene Criterios de
Aceptación escritos para ninguna de las dos** — habría que escribirlos antes
de estimar la tarjeta.

**Estado:** VIGENTE — responsable: Juan Esteban (`[REF-05]`).

**Registrado:** 2026-09-08.

---

## D3 · Qué archivo es "el archivo del municipio" en HU-01/CA-5

**Decisión (supuesto de trabajo, no confirmado):** "el archivo del
municipio" que se reutiliza junto con el PDT (HU-01/CA-5) es la plantilla de
proyectos BPIN (`TipoArchivoFuente.PROYECTOS`), por ser la única de las tres
fuentes que el municipio diligencia a mano en vez de exportarla de una
plataforma nacional.

**Motivo:** CA-5 dice literalmente "el PDT y el archivo del municipio se
reutilizan", y existen tres tipos de archivo (PDT, EJECUCION, PROYECTOS). Por
descarte, y por el patrón de diligenciamiento manual, se interpretó que es
PROYECTOS.

**Riesgo si el supuesto es incorrecto:** si en realidad es un cuarto archivo
distinto a los tres ya modelados, falta una tabla en el esquema y cambia
`[HU-01][BE-04]` (regla de reutilización).

**Estado:** SUPUESTO — PENDIENTE de confirmar con la clienta (Emilse). No
convertir en requisito hasta confirmar. Responsable de la pregunta: equipo
completo, antes de cerrar Fase 4 de `PLANDETRABAJO.md`.

**Registrado:** 2026-09-08.

---

## D4 · Corte de referencia para medir los atributos de rendimiento (Tabla 7, Entrega 1)

**Decisión:** el corte de referencia contra el que se miden los umbrales de
rendimiento declarados en la Entrega 1 (procesamiento completo de un corte en
menos de 60 s, carga de vistas en menos de 4 s) es el corte real de la
vigencia usada durante el desarrollo del Sprint 1, con los siguientes
volúmenes verificados contra los archivos reales de la clienta:

| Magnitud                                                            | Valor                                    |
| ------------------------------------------------------------------- | ---------------------------------------- |
| Metas totales (Plan Indicativo)                                     | 144                                      |
| Metas con ejecución presupuestal asociada                           | 119                                      |
| Metas con BPIN asociado                                             | 67                                       |
| Metas sin ningún cruce (alerta de trazabilidad)                     | 24                                       |
| Subtotales de ejecución excluidos del cruce (`ultimo_nivel = true`) | 111                                      |
| Proyectos BPIN en la plantilla del municipio                        | 38 (de 134 filas, por celdas combinadas) |

**Motivo:** el docente advirtió explícitamente en la revisión de la Entrega 1
que "un umbral sin caso de prueba no es un atributo de calidad" y pidió fijar
el volumen del corte de prueba antes de la Entrega 2. Estos números ya eran el
resultado esperado documentado en `PLANDETRABAJO.md` (Fase 5, HU-07) y en el
docstring de `backend/app/modules/trazabilidad/persistence/consultas.py`; esta
entrada los deja registrados formalmente como la decisión que responde a la
observación del docente.

**Cómo se usa:** las pruebas de rendimiento y las pruebas de integración de
HU-07 (`[HU-07][BE-02]` y siguientes) deben ejecutarse contra este corte —
no contra datos sintéticos ni contra un subconjunto arbitrario — para que la
medición de los 60 s / 4 s sea comparable entre sprints.

**Estado:** VIGENTE.

**Registrado:** 2026-09-08.

---

## D5 · Reconciliación de numeración de CA entre Excel y Trello (HU-01, HU-07)

**Hallazgo:** `Levantamiento de Requisitos.md` tenía menos Criterios de
Aceptación de los que ya estaban definidos y en uso: HU-01 llegaba solo hasta
CA-7 y HU-07 solo tenía CA-1 y CA-4, mientras que el checklist "Criterios de
aceptación" de las tarjetas de Trello ya tenía el contenido completo (8 CA
para HU-01, 8 CA para HU-07) y `PLANDETRABAJO.md` y el código-esqueleto
(`casos_uso.py`, `consultas.py`, `trazabilidad/api/router.py`) ya referencian
esa numeración completa. No eran criterios inventados: existían en Trello,
solo nunca se habían volcado al documento de requisitos.

**Decisión:** Trello es la fuente más completa y `Levantamiento de
Requisitos.md` se corrigió para reconciliarse con él — se agregaron
HU01-CA08 y HU07-CA02, CA03, CA05, CA06, CA07, CA08 con el texto ya escrito en
los checklists de Trello. La única fila sin equivalente en Trello es
HU07-CA04 original (unificación de nombres de columna de indicador al
construir la matriz), que se conservó renumerada como **HU07-CA09**.

**Decisión sobre HU07-CA09 (2026-09-08):** el equipo confirmó que NO se
mantiene como Criterio independiente. Es la misma regla que HU03-CA03
(equivalencia de nombres de columna de indicador), aplicada en un momento
posterior del pipeline: para cuando la matriz se construye, la unificación
ya ocurrió en la ingesta y persiste como una sola columna — la consulta de
HU-07 no unifica nada, solo lee un dato ya unificado. Mantenerla como CA
propia duplicaba la regla en dos Historias de Usuario sin comportamiento
nuevo verificable (sobreingeniería de especificación). Se retiró de
`Levantamiento de Requisitos.md`; el caso de prueba concreto queda como nota
de regresión bajo HU07-CA02 en `docs/TRAZABILIDAD.md`. El Trello no cambia:
nunca tuvo tarjeta ni ítem de checklist para esta regla.

**Estado:** VIGENTE — decisión tomada, sin pendientes.

**Registrado:** 2026-09-08.

---

## D6 · Reconciliación de numeración de CA entre Excel, Trello y PLANDETRABAJO.md (HU-02, HU-03, HU-04)

**Hallazgo:** al revisar un export actualizado de Trello, se encontró el mismo
patrón que motivó D5, ahora en HU-02, HU-03 y HU-04: el checklist de Trello
tiene un primer criterio de acceso/carga del archivo ("la administradora
puede seleccionar/cargar el archivo X correspondiente al corte") que
`Levantamiento de Requisitos.md` nunca capturó. `PLANDETRABAJO.md` ya asigna
`CA-1` a las tarjetas de acceso de las tres historias (`casos_uso.py::
cargar_archivo` y `cortes/api/router.py`), y el código ya escrito confirma la
misma numeración: `pdt.py` cubre "CA-2, CA-3, CA-4, CA-6" (salta CA-1 y CA-5),
`ejecucion.py` cubre "CA-2, CA-4, CA-5, CA-7" (salta CA-1, CA-3 y CA-6),
`_comun.py::mapear_columnas` cita explícitamente "(HU-03/CA-3, HU-07)", y
`proyectos.py` cubre "CA-2, CA-3, CA-4, CA-5" (salta CA-1). Las tres fuentes
(Trello, PLANDETRABAJO.md, código) coincidían entre sí; solo el documento de
requisitos estaba desactualizado.

**Decisión:** se agregó CA-1 (acceso) a HU-02, HU-03 y HU-04 en
`Levantamiento de Requisitos.md`, y se renumeraron los CA existentes para
que coincidan con Trello/PLANDETRABAJO.md/código:

- **HU-02** (antes 5 CA, ahora 6): CA-1 acceso (nuevo) · CA-2 reconoce
  pestaña (antes CA-1) · CA-3 rechazo columnas faltantes (antes CA-2) · CA-4
  rechazo archivo incorrecto (antes CA-4, sin cambio) · CA-5 confirmación
  visual (antes CA-3) · CA-6 alimenta matriz (antes CA-5).
- **HU-03** (antes 6 CA, ahora 7): CA-1 acceso (nuevo) · CA-2 procesa ambas
  pestañas (antes CA-1) · CA-3 equivalencia de nombres (antes CA-2) · CA-4
  rechazo pestaña faltante (antes CA-4, sin cambio) · CA-5 rechazo archivo
  incorrecto (antes CA-5, sin cambio) · CA-6 alimenta matriz (antes CA-6,
  sin cambio) · CA-7 preserva ceros a la izquierda (antes CA-3, se mueve al
  final).
- **HU-04** (antes 4 CA, ahora 5): CA-1 acceso (nuevo) · CA-2 carga tal cual
  (antes CA-1) · CA-3 extracción acotada (antes CA-2) · CA-4 separación
  multivalor (antes CA-3) · CA-5 alimenta matriz (antes CA-4).

Se ajustaron `docs/TRAZABILIDAD.md` (HU-02 reescrita completa; HU-04 con la
fila CA-5 agregada, faltaba) y `docs/ESPECIFICACIONES_TECNICAS.md` en
consecuencia. `docs/SEGURIDAD.md` no cita estos CA, no requirió cambios. El
Trello no se modifica: ya tenía la numeración correcta.

**Estado:** VIGENTE — decisión tomada, sin pendientes.

**Registrado:** 2026-09-08.

---

## D7 · La entidad Corte tiene dos estados: BORRADOR y REGISTRADO

**Decisión:** `Corte` modela explícitamente dos estados — `BORRADOR` (creado
solo con vigencia y fecha, acepta cargas de archivos) y `REGISTRADO` (las
tres fuentes obligatorias presentes, entra al histórico). El paso de uno a
otro es la transición que exige HU-01/CA-4.

**Motivo:** sin un estado explícito, HU-01/CA-3 ("no se registra sin
archivos completos") y las cargas de HU-02/HU-03/HU-04 ("subir archivos
contra un corte que ya existe") son incompatibles entre sí — no se puede
exigir que el corte esté completo para existir, y a la vez que exista antes
de estar completo. El estado resuelve la contradicción.

**Origen:** este supuesto se identificó como `S-1` en una consolidación
anterior del plan de Trello (`SUPUESTO — confirmar en la próxima reunión`,
marcado explícitamente como algo que **afecta el esquema de BD**). No existía
ninguna entrada en este documento que lo ratificara, aunque el esqueleto de
código (`backend/app/modules/cortes/domain/entidades.py`, con
`EstadoCorte.BORRADOR`/`REGISTRADO`) y `PLANDETRABAJO.md` ya lo dan por
sentado, sin marcarlo como pendiente. Se ratifica aquí para cerrar esa
inconsistencia entre lo que el código ya asume y lo que estaba documentado
como abierto.

**Alternativas consideradas:** ninguna evaluada aparte — el propio código ya
estaba construido sobre este diseño antes de que se detectara el vacío
documental.

**Estado:** RATIFICADA.

**Registrado:** 2026-09-08.

---

## D8 · Reconciliación de CA-8 entre PLANDETRABAJO.md/TRAZABILIDAD.md y CASOS_DE_PRUEBA.md (HU-01)

**Hallazgo:** `docs/CASOS_DE_PRUEBA.md` (CP-HU01-08) marcaba CA-8 como "✅
Probado" con evidencia de `test_casos_uso_cortes.py` (capa de aplicación,
sin superficie HTTP), mientras que `PLANDETRABAJO.md` §2.7 y
`docs/TRAZABILIDAD.md` (fila CA-8) coinciden en que CA-8 es "el endpoint"
(`cortes/api/router.py`) y lo marcaban "Pendiente" hasta que
`[HU-01][FE-01]` existiera. Las tres fuentes no pueden estar en lo correcto
a la vez.

**Decisión:** se corrige `docs/CASOS_DE_PRUEBA.md` para alinearse con las
otras dos fuentes (que además asignan explícitamente la tarjeta que cierra
el CA). CP-HU01-08 pasa de "✅ Probado" a "🟡 En progreso": la prueba
existente verifica una precondición necesaria de aplicación, no la
referenciabilidad por API que el CA describe literalmente ("el corte queda
disponible como referencia... para asociarle archivos fuente").
`[HU-01][FE-01]` cierra CA-8 por completo, al exponer `GET /cortes` y
`GET /cortes/{id}`.

**Motivo:** mismo patrón que D5/D6 — un documento derivado se adelantó a
marcar un CA como cerrado con una prueba que cubre solo una parte de lo que
el CA exige.

**Alternativas consideradas:** corregir `PLANDETRABAJO.md`/`TRAZABILIDAD.md`
en vez de `CASOS_DE_PRUEBA.md` — descartada porque esas dos fuentes ya
asignan explícitamente la tarjeta que cierra el CA, más específico y
verificable que la descripción de `CASOS_DE_PRUEBA.md`.

**Estado:** VIGENTE.

**Registrado:** 2026-09-11.

---

## D9 · Qué hace que dos cortes se consideren duplicados

**Decisión:** se rechaza la creación de un corte si ya existe otro con la
misma vigencia y la misma fecha_corte exacta. Con D11 (un solo corte en
BORRADOR activo a la vez), este conflicto solo puede darse entre cortes ya
REGISTRADO.

**Motivo:** HU-07 necesita identificar "el corte actual" sin ambigüedad
(GET /matriz-relacion/actual). Dos cortes con la misma fecha lo impiden.

**Alternativas consideradas:** unicidad solo por vigencia (D-03 en
`docs/ESPECIFICACIONES_TECNICAS.md`, sección HU-01) — descartada: impediría
más de un corte por año, contradice el uso esperado (revisiones periódicas).

**Nota:** no confundir con "D-09" en `docs/ESPECIFICACIONES_TECNICAS.md`,
sección HU-03 — es un tema distinto (filas de ejecución reconocidas),
coincidencia de número entre dos sistemas de numeración diferentes.

**Estado:** RATIFICADA.

**Registrado:** 2026-09-13.
**Ratificado:** 2026-09-13 por el equipo.

---

## D10 · La creación del corte requiere una acción explícita

**Decisión:** `POST /cortes` se dispara solo con un clic explícito (ej.
"Continuar") al cerrar el paso de vigencia/fecha, nunca porque la
validación del formulario pase mientras se escribe.

**Motivo:** en el mockup actual, el checkmark "Datos del corte
configurados" se enciende con validación en tiempo real; si disparara la
creación, cada corrección de una fecha ya válida crearía un BORRADOR nuevo.

**Riesgo si no se ratifica:** Karold puede implementar cualquiera de los
dos sin saber cuál se espera.

**Estado:** PROPUESTA — pendiente de confirmar antes de construir
`pages/NuevoCorte.jsx` (`[HU-01][FE-02]`, tarjeta 2.8).

**Registrado:** 2026-09-13.

---

## D11 · Solo un corte en BORRADOR activo a la vez

**Decisión:** al crear un corte, se rechaza si ya existe otro en BORRADOR.
Corregirlo requiere `PATCH /cortes/{id}`, que no existe hoy.

**Motivo:** el proceso real de la clienta es secuencial; simplifica D9.

**A qué afecta (no implementar aún, solo dejar constancia):** `crear_corte`
en `casos_uso.py`, método nuevo en `puertos.py`, endpoint `PATCH` sin
dueño, mapeo 409 en `core/errores.py`, migración de Alembic / `models.py`
— índice único parcial sobre `estado = 'BORRADOR'` (a lo sumo un corte en
ese estado en toda la tabla).

**Estado:** RATIFICADA.

**Registrado:** 2026-09-13.
**Ratificado:** 2026-09-13 por el equipo.
**Aclaración posterior (2026-09-18):** Cristhian y Juan David confirmaron
que D11 también requiere el índice de BD como respaldo contra condiciones
de carrera (dos peticiones casi simultáneas), no solo la validación de
aplicación. La ratificación original del 2026-09-13 no dejó esto
explícito — este PR lo cierra.

---

## D12 · Límite de tamaño de archivo verificado en el cliente

**Decisión:** el frontend rechaza, antes de intentar subir, cualquier
archivo mayor a 2.097.152 bytes (2 MB) — aviso inmediato en
`CargaDeArchivo.jsx`, sin llamar a `onCargar`.

**Motivo:** los archivos reales de la clienta hoy pesan menos de 200 KB;
2 MB da un margen ~10x para crecimiento sin retrasar el aviso de error
hasta después de un viaje de red completo. Coherente con el límite real de
`[SEC-03]` (`backend/app/core/config.py::max_upload_bytes`, 25 MB) — el del
cliente es más conservador, no lo reemplaza ni lo duplica.

**Estado:** RATIFICADA.

**Registrado:** 2026-09-15.
**Ratificado:** 2026-09-15, acordado con Cristhian.

## D13 · `[HU-04][BE-03]` reabierta y corregida: separadores y descartes registrados

**Hallazgo (2026-09-19, Juan David + verificación cruzada):** el texto
literal de la tarjeta Trello `[HU-04][BE-03]` exige, en "casos borde
obligatorios en los tests", dos cosas que la implementación original de
`CodigoIndicadorProducto.extraer_todos` (probada con 6 tests, solo
`split("\n")`) no cumplía:

1. Reconocer coma, punto y coma, guion y espacio como separadores además
   de salto de línea, incluyendo códigos pegados sin separador
   (segmentar de a 9 dígitos SOLO si el total es múltiplo de 9).
2. "Todo código descartado queda registrado con su motivo" — la versión
   original simplemente omitía el candidato inválido de la lista, sin
   dejar rastro.

Verificado contra la CA-4 oficial (`Levantamiento de Requisitos.md`,
`HU04-CA04`) y contra `Sprint1_Decisiones_de_Diseno.md`/
`GovSync_Guia_Tecnica.md`: ninguno de esos documentos menciona los
separadores adicionales ni el registro de descartes — solo la tarjeta de
Trello los exige explícitamente. Es la tarjeta, no la documentación
derivada, la fuente correcta aquí (jerarquía del proyecto: CA aprobados
> reglas de negocio > documentación).

**Decisión:** se reabre y corrige `[HU-04][BE-03]` en esta misma tarjeta
(no se crea TRANS-02, para no duplicar trabajo ya comprometido).

**Cambio de contrato (deliberado, no oculto):** `extraer_todos` cambia su
tipo de retorno de `list[CodigoIndicadorProducto]` a
`ResultadoExtraccionIndicadores(codigos, descartes)`. Es un cambio de API
de dominio, justificado porque el descarte con motivo es parte del
contrato exigido por la propia tarjeta, no un detalle de presentación.
Único call site afectado: `LectorProyectos.leer()`, que ahora vuelca
`descartes` al mecanismo de `advertencias` ya existente (no se construye
infraestructura nueva).

**Limitación conocida, aceptada y documentada (no bloqueante):** un monto
con coma decimal en formato colombiano (`$230.000.000,00`) produce un
candidato residual de 2 dígitos (`00`) que SÍ se registra como descarte
(cumple el texto literal de la tarjeta: cualquier candidato numérico de
longitud distinta de 9 se reporta). No fabrica un código falso ni afecta
`codigos`, solo agrega ruido a la lista de revisión manual. Pendiente de
que el equipo confirme si esto debe filtrarse en una iteración futura.

**Fuera de alcance, explícitamente (PENDIENTE S-3 de la propia tarjeta):**
verificar que cada código exista en el PDT ya cargado. La tarjeta lo
marca PENDIENTE y, de confirmarse, dependería de HU-02 — no se convierte
en requisito sin esa confirmación.

**Evidencia:** `test_codigos.py` (16 pruebas, antes 6) + actualización de
`test_lectores_proyectos.py::test_indicador_no_reconocible_...` (fixture
ajustada: contenía un "9" suelto en la prosa que ahora se registra como
descarte válido de 1 dígito — coincidencia del texto de prueba, no un
bug). 258 passed en local (2026-09-19).

**Estado:** Corregida.
**Quién y cuándo:** Juan Esteban, 2026-09-19.

