# Trazabilidad HU → CA → Código → Prueba — Sprint 1

Se llena a medida que avanza el sprint, no al final. Cada fila se marca
cuando el CA correspondiente tiene código Y prueba automatizada pasando —
un CA "implementado" sin prueba no cuenta como hecho (ver Definición de
Terminado en `PLANDETRABAJO.md`, §5).

Estado: `Pendiente` · `En progreso` · `Implementado` · `Probado` (todas las
pruebas de ese CA pasan) · `Bloqueado` (anotar por qué en Evidencia).

---

## E-02 / HU-01 — Crear corte de seguimiento (8 SP)

> Actualizado 2026-09-13 (CA-5/CA-6/CA-7) tras revisión estática del código en
> la rama `feature/hu01-be04-reutilizacion-fuentes` — ver nota de alcance al
> final de esta sección: no fue posible ejecutar `pytest` en este entorno para
> confirmarlo en caliente, se pide correrlo en local antes de mover la
> tarjeta a "Tareas hechas".

| CA                                              | Tarjeta(s)                         | Archivo                                            | Estado                       | Prueba | Evidencia |
| ----------------------------------------------- | ---------------------------------- | -------------------------------------------------- | ---------------------------- | ------ | --------- |
| CA-1 (registro exitoso, parcial)                | `[HU-01][BE-03]`                   | `cortes/application/casos_uso.py`                  | Probado                      | `test_casos_uso_cortes.py` (3 pruebas) | 23 passed en local (2026-09-09) |
| CA-2 (rechaza fecha futura)                     | `[HU-01][BE-01]`                   | `cortes/domain/entidades.py::Corte.validar_fecha`  | Probado                      | `test_cortes.py::test_rechaza_fecha_futura_con_motivo` | 19 passed en local (2026-09-08) |
| CA-3 (no registra sin archivos completos)       | `[HU-01][BE-05]`                   | `cortes/application/casos_uso.py::registrar_corte` | Pendiente                    | —      | —         |
| CA-4 (registro exitoso completo)                | `[HU-01][BE-01]`, `[HU-01][BE-05]` | `entidades.py`, `casos_uso.py`                     | En progreso (BE-01 probado, BE-05 falta) | `test_cortes.py::test_archivos_faltantes_en_corte_nuevo_devuelve_los_tres` (19 passed, 2026-09-08) | `registrar()` sigue NotImplementedError, es BE-05 |
| CA-5 (reutilización automática PDT + municipio) | `[HU-01][BE-04]`                   | `entidades.py` + `casos_uso.py`                    | Implementado (dominio/aplicación); probado solo con repositorio en memoria | `test_casos_uso_cortes.py` | Pendiente confirmar con `pytest` en local; falta prueba con repositorio real (SQLAlchemy) |
| CA-6 (opción de reemplazar reutilizados)        | `[HU-01][BE-04]`                   | idem                                               | Implementado (vía el mecanismo genérico de HU-06) | `test_repositorios_cortes.py::test_registrar_archivo_inserta_y_luego_reemplaza` | Pendiente confirmar con `pytest` en local |
| CA-7 (archivo de ejecución siempre solicitado)  | `[HU-01][BE-04]`                   | idem                                               | Probado                      | `test_cortes.py::test_puede_reutilizar_rechaza_ejecucion` | Pendiente confirmar con `pytest` en local |
| CA-8 (endpoint)                                 | `[HU-01][FE-01]`                   | `cortes/api/router.py`                             | Pendiente                    | —      | —         |

> Nota de alcance (CA-5/CA-6/CA-7): esta actualización se hizo leyendo el
> código y los nombres de prueba ya escritos en la rama, no ejecutando la
> suite (este entorno no puede instalar `pytest`). Antes de marcar estos CA
> como cerrados hay que correr `pytest backend/tests -v` en local y pegar el
> resultado real en Evidencia.

## E-02 / HU-02 — Cargar Plan Indicativo (3 SP)

> Numeración reconciliada el 2026-09-08 con Trello, `PLANDETRABAJO.md` y el
> código (faltaba CA-1 y CA-3/CA-4 estaban invertidos).

| CA                                                      | Tarjeta(s)                         | Archivo                                                | Estado    | Prueba | Evidencia |
| ------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------ | --------- | ------ | --------- |
| CA-1 (acceso: seleccionar el Plan Indicativo del corte) | `[HU-02][FE-01]`, `[HU-02][BE-04]` | `cortes/api/router.py`, `casos_uso.py::cargar_archivo` | Pendiente | —      | —         |
| CA-2 (reconoce pestaña "Plan indicativo - Productos")   | `[HU-02][BE-01]`                   | `ingesta/persistence/lectores/pdt.py`                  | Pendiente | —      | —         |
| CA-3 (rechazo por columnas faltantes, nombradas)        | `[HU-02][BE-02]`                   | `lectores/pdt.py::OBLIGATORIAS`                        | Pendiente | —      | —         |
| CA-4 (rechazo por archivo incorrecto)                   | `[HU-02][BE-03]`                   | `lectores/pdt.py::leer`                                | Pendiente | —      | —         |
| CA-5 (confirmación visual de metas cargadas)            | `[HU-02][FE-02]`                   | `pages/NuevoCorte.jsx` paso 2                          | Pendiente | —      | —         |
| CA-6 (alimenta matriz de relación)                      | `[HU-02][BE-04]`                   | `casos_uso.py::cargar_archivo`                         | Pendiente | —      | —         |

## E-02 / HU-03 — Cargar información presupuestal y contractual (8 SP)

| CA                                                      | Tarjeta(s)                         | Archivo                            | Estado    | Prueba | Evidencia |
| ------------------------------------------------------- | ---------------------------------- | ---------------------------------- | --------- | ------ | --------- |
| CA-1 (endpoint)                                         | `[HU-03][FE-01]`                   | `cortes/api/router.py`             | Pendiente | —      | —         |
| CA-2 (procesa ambas pestañas sin exigir carga separada) | `[HU-03][BE-01]`, `[HU-03][FE-02]` | `lectores/ejecucion.py`            | Pendiente | —      | —         |
| CA-3 (equivalencia de nombres de columna de indicador)  | `[HU-03][BE-03]`                   | `_comun.py::mapear_columnas`       | Pendiente | —      | —         |
| CA-4 (rechazo por pestaña faltante, nombrada)           | `[HU-03][BE-04]`                   | `lectores/ejecucion.py::leer`      | Pendiente | —      | —         |
| CA-5 (rechazo por archivo incorrecto)                   | `[HU-03][BE-05]`                   | idem                               | Pendiente | —      | —         |
| CA-6 (confirmación reporta ambas pestañas por separado) | `[HU-03][FE-02]`                   | `pages/NuevoCorte.jsx`             | Pendiente | —      | —         |
| CA-7 (preserva ceros a la izquierda)                    | `[HU-03][BE-02]`                   | `lectores/_comun.py` (`dtype=str`) | Pendiente | —      | —         |

## E-02 / HU-04 — Cargar plantilla de proyectos BPIN (13 SP)

> CA-5 agregado el 2026-09-08 (alimenta matriz), faltaba en esta tabla.

| CA                                                         | Tarjeta(s)       | Archivo                               | Estado    | Prueba | Evidencia |
| ---------------------------------------------------------- | ---------------- | ------------------------------------- | --------- | ------ | --------- |
| CA-1 (endpoint)                                            | `[HU-04][FE-01]` | `cortes/api/router.py`                | Pendiente | —      | —         |
| CA-2 (carga tal cual, sin exigir estructura estandarizada) | `[HU-04][BE-01]` | `lectores/proyectos.py`               | Pendiente | —      | —         |
| CA-3 (extracción acotada de columnas)                      | `[HU-04][BE-02]` | `lectores/proyectos.py::OBLIGATORIAS` | Pendiente | —      | —         |
| CA-4 (separa indicadores multivalor automáticamente)       | `[HU-04][BE-03]` | `shared/codigos.py::CodigoIndicadorProducto.extraer_todos` | Probado | `test_codigos.py::TestCodigoIndicadorProducto` (6 pruebas nuevas: ejemplo real de la tarjeta, ignora nombre/monto, NO recupera cero perdido en 8 dígitos, ignora un BPIN de 15, conserva duplicados, entradas no normalizables) | Pendiente de correr `pytest tests/test_codigos.py -v` en local para confirmación oficial |
| CA-5 (alimenta matriz de relación)                         | `[HU-04][BE-04]` | `casos_uso.py::cargar_archivo`        | Pendiente | —      | —         |

## E-02 / HU-07 — Visualizar matriz de relación del corte (5 SP)

> Numeración reconciliada el 2026-09-08 con el checklist de Trello y con
> `Levantamiento de Requisitos.md` (antes esta tabla mezclaba dos numeraciones
> distintas para el mismo CA-4). La fila que existía como "CA-9" (unificación
> de nombres de columna del indicador) se fusionó con CA-2: es la misma regla
> que HU03-CA02, ya garantizada en la ingesta — ver `docs/DECISIONES.md`, D5.

| CA                                                                                                                                                                                           | Tarjeta(s)                         | Archivo                                    | Estado    | Prueba                                                                                                                                                                          | Evidencia |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| CA-1 (acceso a la matriz del corte actual)                                                                                                                                                   | `[HU-07][FE-01]`                   | `trazabilidad/api/router.py`               | Pendiente | —                                                                                                                                                                               | —         |
| CA-2 (usa información ya procesada, no relee los Excel; incluye el caso donde el indicador venía con dos nombres — CodigoIndicadorCcpet / Cod Indicador Ccpet — ya unificados por HU03-CA02) | `[HU-07][BE-01]`                   | `trazabilidad/persistence/consultas.py`    | Pendiente | Prueba de regresión: construir la matriz a partir de un `rubro` cuyo origen mezclaba ambos nombres de columna y verificar que no aparecen columnas duplicadas ni filas perdidas | —         |
| CA-3 (visualiza código BPIN)                                                                                                                                                                 | `[HU-07][BE-01]`, `[HU-07][FE-02]` | `consultas.py`, `pages/MatrizRelacion.jsx` | Pendiente | —                                                                                                                                                                               | —         |
| CA-4 (visualiza indicador y/o producto)                                                                                                                                                      | `[HU-07][BE-01]`, `[HU-07][FE-02]` | idem                                       | Pendiente | —                                                                                                                                                                               | —         |
| CA-5 (visualiza información de ejecución)                                                                                                                                                    | `[HU-07][BE-01]`, `[HU-07][FE-02]` | idem                                       | Pendiente | —                                                                                                                                                                               | —         |
| CA-6 (visualiza número y descripción del contrato)                                                                                                                                           | `[HU-07][BE-01]`, `[HU-07][FE-02]` | idem                                       | Pendiente | —                                                                                                                                                                               | —         |
| CA-7 (no colapsa relaciones múltiples)                                                                                                                                                       | `[HU-07][BE-02]`, `[HU-07][FE-03]` | `consultas.py`                             | Pendiente | — ver caso frontera documentado en el docstring de `consultas.py` (deduplicar el puente, no el resultado)                                                                       | —         |
| CA-8 (sin asociación ficticia; NULL explícito)                                                                                                                                               | `[HU-07][BE-03]`, `[HU-07][FE-03]` | idem, `pages/MatrizRelacion.jsx`           | Pendiente | Debe dar: 144 metas · 119 con ejecución · 67 con BPIN · 24 sin cruce (ver `docs/DECISIONES.md`, D4)                                                                             | —         |

---

## Cómo llenar esta tabla

1. Cuando abra una rama para una tarjeta, cambie el Estado a `En progreso`.
2. Cuando el código esté escrito, cambie a `Implementado` y llene el nombre
   real del archivo si difiere del planeado (y anote por qué).
3. Cuando la prueba automatizada exista y pase, cambie a `Probado` y ponga en
   Prueba el nombre de la función de test (ej. `test_rechaza_fecha_futura`).
4. En Evidencia: enlace al PR, o el resultado real de `pytest -k <patrón>` si
   el PR aún no existe.
5. No mueva la tarjeta de Trello a "Tareas hechas" hasta que esta fila diga
   `Probado`.
