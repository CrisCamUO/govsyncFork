# Estándar de Ramas

## Formato

```
<tipo>/<identificador-opcional>/<descripcion-corta>
```

## Tipos

| Tipo       | Propósito           | Ejemplo                          |
| ---------- | ------------------- | -------------------------------- |
| `feature`  | Nueva funcionalidad | `feature/crear-endpoint-ordenes` |
| `bugfix`   | Corrección de bug   | `bugfix/validacion-fecha`        |
| `refactor` | Mejora de código    | `refactor/simplificar-auth`      |
| `docs`     | Documentación       | `docs/actualizar-readme`         |
| `test`     | Tests               | `test/dashboard-filters`         |
| `chore`    | Mantenimiento       | `chore/actualizar-deps`          |

## Reglas

- Minúsculas, palabras separadas por guiones (`-`).
- Se crea siempre desde la rama de integración del equipo (`develop`).
- Nunca se commitea directo en la rama de integración ni en producción (`main`).
- El identificador de historia/issue (`E-XX-HU-XX`) es opcional pero recomendado.

```bash
<!-- ejemplo de flujo -->
git checkout develop
git pull origin develop
git checkout -b feature/nombre-de-la-tarea
```

---

# Formato de Commits

Basado en [Conventional Commits](https://www.conventionalcommits.org/).

## Estructura

```
<tipo>(<alcance opcional>): <descripción en presente, minúscula>
```

## Tipos permitidos

| Tipo       | Cuándo usarlo                                  |
| ---------- | ---------------------------------------------- |
| `feat`     | Nueva funcionalidad                            |
| `fix`      | Corrección de bug                              |
| `docs`     | Solo documentación                             |
| `style`    | Formato, sin cambio de lógica                  |
| `refactor` | Cambio de código sin alterar el comportamiento |
| `test`     | Agregar o corregir tests                       |
| `chore`    | Mantenimiento, dependencias, config            |
| `perf`     | Mejora de rendimiento                          |

## Ejemplo

```bash
<!-- ejemplo de commit -->
git commit -m "feat(orders): agregar endpoint de creación de orden"
```

---

# Cómo agregar o actualizar una dependencia del backend

Los archivos `backend/requirements.txt` y `backend/requirements-dev.txt` se **generan**
con el hash de cada paquete; la CI, el Dockerfile y Render instalan con
`pip install --require-hashes --only-binary ":all:"`, así que pip rechaza cualquier
archivo cuyo hash no coincida (ver `docs/SEGURIDAD.md`).

1. Edita solo los archivos fuente, con la versión fijada con `==`:
   - `backend/requirements.in`: dependencias directas de producción.
   - `backend/requirements-dev.in`: herramientas de desarrollo (pytest, ruff, bandit...).
2. Regenera los `.txt` desde `backend/` (`pip install uv` si no lo tienes):

   ```bash
   uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes -o requirements.txt
   uv pip compile requirements-dev.in -c requirements.txt --universal --python-version 3.12 --generate-hashes -o requirements-dev.txt
   ```

   `--universal` produce un solo archivo válido para Windows (equipo) y Linux (CI/Render).

3. Reinstala en tu venv:

   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

4. Commitea juntos el `.in` y el `.txt` regenerado.

**Regla:** nunca edites `requirements*.txt` a mano ni uses `pip freeze` para
generarlos: se pierden los hashes y los marcadores de plataforma.
