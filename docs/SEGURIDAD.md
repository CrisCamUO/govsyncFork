# Seguridad — checklist OWASP y específico de GovSync

Checklist a completar a medida que se implementa cada tarjeta con superficie
de seguridad. No marcar "Verificado" sin una prueba o evidencia concreta —
ocultar una opción en el frontend no cuenta como verificación (regla del
proyecto).

## Tabla 4 de la rúbrica — OWASP Top 10

| Verificación                | Estado          | Evidencia / tarjeta responsable                                                                                                                                                                                                                                                                                                                                                   |
| --------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SQL Injection               | Verificado      | Auditado 2026-09-18: todo el acceso a datos pasa por el ORM de SQLAlchemy (`repositorios.py`, `consultas.py`). Único uso de `sa.text()` en el repo es una cadena estática en `models.py` (`postgresql_where=sa.text("estado = 'BORRADOR'")`, cláusula de un índice parcial), sin dato de usuario interpolado. Ningún `execute()`/`.format()`/f-string con SQL crudo en el backend |
| XSS (Cross-Site Scripting)  | Verificado      | Auditado 2026-09-18: React escapa por defecto; `grep -rn "dangerouslySetInnerHTML" frontend/src/` no encuentra ningún uso en todo el frontend                                                                                                                                                                                                                                     |
| CSRF                        | N/A por ahora   | La API es stateless (Bearer JWT, no cookies de sesión) — CSRF aplica a autenticación basada en cookies, que no existe en Sprint 1 (ver `docs/DECISIONES.md`, D2). Revisar de nuevo si Sprint 2 introduce cookies                                                                                                                                                                  |
| Autenticación               | N/A este sprint | Diferida a Sprint 2 — ver `docs/DECISIONES.md`, D2                                                                                                                                                                                                                                                                                                                                |
| Autorización                | N/A este sprint | Diferida a Sprint 2 — ver `docs/DECISIONES.md`, D2                                                                                                                                                                                                                                                                                                                                |
| Datos sensibles encriptados | Pendiente       | TLS depende del despliegue (`[DEV-07]`, aún no hecho). No verificable sin ambiente desplegado                                                                                                                                                                                                                                                                                     |

## Específico de GovSync — validación de archivos cargados (`[SEC-03]`)

La superficie de ataque real de este sprint no es login (que no existe
todavía) sino la carga de archivos Excel. Checklist de `[SEC-03]`:

- [x] Extensión declarada vs. tipo MIME real del contenido (no confiar en la
      extensión del nombre de archivo) — `validacion_archivos.py::_verificar_extension` + `_verificar_estructura_y_macros` valida la firma real de ZIP (`PK\x03\x04`),
      no solo el sufijo del nombre
- [x] Tamaño máximo verificado **antes** de leer el archivo completo en
      memoria — `_verificar_tamano`, revalidado como defensa en profundidad
      (el corte por streaming vive en el router)
- [x] Sanitización del nombre de archivo (rechazar path traversal, ej.
      `../../etc/passwd`) — `validacion_archivos.py::sanitizar_nombre`
- [x] Rechazo explícito de libros con macros (`.xlsm`) — `_verificar_estructura_y_macros`
      inspecciona el ZIP en busca de `xl/vbaProject.bin` y la marca `macroEnabled`;
      un `.xlsm` renombrado a `.xlsx` no lo engaña
- [x] Verificación de que las hojas obligatorias existen antes de procesar
      (no leer estructuras parciales) — `_verificar_estructura_y_macros` exige
      al menos una hoja real (`xl/worksheets/*.xml`); el nombre concreto de
      cada pestaña lo resuelve el lector de cada fuente (HU-02/03/04)
- [x] Los mensajes de error no exponen rutas internas del servidor ni trazas
      completas de excepción al cliente — ver sección siguiente

Evidencia: `test_validacion_archivos.py` (16 pruebas), 170 passed en local
(2026-09-18). Consumido por `[HU-02][BE-04]`, `[HU-03][BE-06]`, `[HU-04][BE-04]`
(los tres casos de uso `cargar_archivo`, todavía `NotImplementedError`).

## Manejo de secretos

- [x] Ningún archivo `.env` real llegó al repositorio (`[SEC-02]`) — verificado
      2026-09-18 con `git ls-files | grep -i "\.env"`: solo `backend/.env.example`
      y `frontend/.env.example` están trackeados; `.gitignore` cubre `.env`,
      `.env.local` y `backend/.env`
- [x] Variables de entorno documentadas en `.env.example` sin valores reales —
      `SECRET_KEY=dev-only-insecure-key-change-me` es explícitamente un
      placeholder; `config.py` tiene un `field_validator` que **lanza excepción**
      si `environment=="production"` y el secreto sigue empezando por `dev-only`
- [ ] `SONAR_TOKEN` y credenciales de despliegue viven en GitHub Secrets, no
      en el código ni en `docker-compose.yml` — **no verificable desde el
      repositorio local** (son ajustes de GitHub, no de código); además
      `[DEV-06]` (SonarCloud/CodeQL) todavía no está implementado, así que este
      secreto ni siquiera existe todavía

## Exposición de errores internos

- [x] Las excepciones de dominio (`app/shared/errors.py`) llegan al cliente
      como mensajes de negocio (ej. "falta el archivo de ejecución"), nunca
      como traceback de Python ni detalle de SQLAlchemy — `app/core/errores.py`
      tiene un manejador genérico (`_manejar_error_no_previsto`) que registra
      la excepción completa solo en el log del servidor y responde al cliente
      con un mensaje fijo ("Ocurrió un error inesperado...", HTTP 500), sin
      exponer la traza ni el mensaje interno

## CORS

- [x] CORS restringido a orígenes explícitos, nunca `*` — `main.py` usa
      `CORSMiddleware(allow_origins=settings.cors_origins_list)`, configurable
      por `CORS_ORIGINS` (por defecto solo `http://localhost:5173` en desarrollo)
- [ ] Confirmar el dominio real de producción cuando `[DEV-07]` despliegue
      (hoy solo se verificó el valor de desarrollo local)

---

**Cómo se llena:** cada tarjeta que toque una de estas filas debe, al
cerrarse, actualizar el Estado y dejar el enlace al PR o a la prueba que lo
demuestra. Antes del cierre del Sprint 1, esta tabla debe copiarse (ya
resuelta) a la Tabla 4 del documento de entrega, tal como pide
`PlantillaSprint1.md` §4.3.
