# GovSync

Sistema de consolidación y validación cruzada de información de planeación, ejecución presupuestal y proyectos de inversión para municipios de categoría 6 en Colombia. Piloto: Santa Rosa (Cauca).

Consolida y cruza tres fuentes que hoy viven en Excels sueltos — el Plan Indicativo (PDT), el archivo presupuestal (Ejecución + Contratación) y la plantilla de proyectos BPIN — usando el código de indicador de producto (9 dígitos) como llave común, para que la administración pueda ver de un vistazo qué metas del plan de desarrollo tienen presupuesto y contrato asociado, y cuáles no.

## Stack

- **Backend:** FastAPI (Python 3.12+) — monolito modular por capas (`api` → `application` → `domain` ← `persistence`), ver [`CLAUDE.md`](./CLAUDE.md) para el detalle de la arquitectura.
- **Frontend:** React + Vite, Tailwind CSS.
- **Base de datos:** PostgreSQL 16, migraciones con Alembic.

## Estructura

Monorepo — [`backend/`](./backend) (API + lógica de negocio), [`frontend/`](./frontend) (React), `docs/` (decisiones, especificaciones, seguridad).

---

## Cómo correr el proyecto en local

### Requisitos previos

- **Docker Desktop** (para Postgres 16).
- **Node.js 18+** y **npm**.
- **Python 3.12+** con `venv`.

### 1. Variables de entorno

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Los valores por defecto de `backend/.env.example` ya apuntan al Postgres de Docker Compose (`govsync`/`govsync`/`localhost:5432`) — no hace falta cambiar nada para desarrollo local. **Ojo:** la URL usa el prefijo `postgresql+psycopg://` (psycopg3), no `postgresql://` a secas.

### 2. Base de datos (Postgres, vía Docker)

```bash
docker compose up -d
```

Esto **solo levanta Postgres** — backend y frontend corren localmente para tener recarga en caliente. Verifica que esté sano antes de seguir:

```bash
docker inspect --format='{{.State.Health.Status}}' govsync-postgres
```

Repite hasta que diga `healthy`.

### 3. Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash) — en Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head               # aplica todas las migraciones
uvicorn app.main:app --reload --port 8000
```

Esta terminal queda ocupada sirviendo el backend. Verifica en `http://localhost:8000/docs` (Swagger).

### 4. Frontend

En **otra terminal**, desde la raíz del repo:

```bash
npm install     # instala dependencias del workspace raíz + frontend (husky, lint-staged, React, Vite, Tailwind...)
npm run dev
```

`npm install` en la raíz también activa los hooks de Git (`commit-msg`/`pre-commit` vía husky) — hazlo una sola vez después de clonar.

Abre `http://localhost:5173`. La app parte en el histórico de cortes (`/cortes`); desde ahí se crea un corte nuevo (`/cortes/nuevo`), se cargan los tres archivos, se registra, y se navega a su matriz de relación (`/matriz/:corteId`).

### Apagar todo

```bash
docker compose down      # detiene y elimina el contenedor (los datos persisten en el volumen)
# Ctrl+C en las terminales de backend y frontend
```

---

## Comandos útiles (desde `backend/`, con el venv activo)

```bash
pytest                                    # suite completa, con cobertura
pytest tests/test_arquitectura.py         # verifica los límites entre capas — correr tras tocar cualquier módulo
ruff check .                              # lint
ruff check . --fix
ruff format .
alembic revision --autogenerate -m "mensaje"   # nueva migración tras cambiar un modelo
```

Desde la raíz (frontend):

```bash
npm run lint            # eslint sobre frontend/src
npm run format          # prettier --write .
npm run build           # build de producción del frontend
```

---

## Documentación

| Documento                                                                | Para qué sirve                                                                                                                                                                                     |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [CONTRIBUTING.md](./CONTRIBUTING.md)                                     | Flujo de trabajo: convención de ramas, formato de commits (Conventional Commits + commitlint), mecánica de sprints.                                                                                |
| [PLANDETRABAJO.md](./PLANDETRABAJO.md)                                   | Orden de implementación de las tarjetas del sprint, quién hace qué.                                                                                                                                |
| [docs/DECISIONES.md](./docs/DECISIONES.md)                               | Registro histórico de decisiones de arquitectura y alcance, con su motivo y estado (RATIFICADA/PROPUESTA/VIGENTE). Es la fuente de verdad cuando el código, un doc derivado y Trello no coinciden. |
| [docs/DATOS.md](./docs/DATOS.md)                                         | Anatomía real de los tres archivos fuente (PDT, Ejecución, Proyectos BPIN): qué columna se extrae, dónde se persiste, y qué llega a la matriz de relación.                                         |
| [docs/TRAZABILIDAD.md](./docs/TRAZABILIDAD.md)                           | Estado de cada Criterio de Aceptación por Historia de Usuario (implementado/probado/pendiente), con evidencia.                                                                                     |
| [docs/ESPECIFICACIONES_TECNICAS.md](./docs/ESPECIFICACIONES_TECNICAS.md) | Contratos técnicos detallados (endpoints, DTOs, reglas de validación).                                                                                                                             |
| [docs/CASOS_DE_PRUEBA.md](./docs/CASOS_DE_PRUEBA.md)                     | Casos de prueba por Criterio de Aceptación.                                                                                                                                                        |
| [docs/SEGURIDAD.md](./docs/SEGURIDAD.md)                                 | Consideraciones de seguridad (OWASP), manejo de secretos, validación de archivos cargados.                                                                                                         |
| [docs/DESPLIEGUE.md](./docs/DESPLIEGUE.md)                               | Cómo aplicar migraciones manualmente contra la base de datos de producción (Render).                                                                                                               |
| [docs/DESIGN_SPEC.md](./docs/DESIGN_SPEC.md)                             | Especificación de estilo visual (tokens, layout, componentes) usada como referencia para el frontend — ver D18/D19 en `docs/DECISIONES.md` para qué parte se adaptó realmente.                     |

## Estado del proyecto

Sprint 1 en curso — módulos de carga (PDT, Ejecución, Proyectos BPIN) y matriz de relación (HU-07) implementados y probados de punta a punta. Autenticación y control de acceso por rol están **deliberadamente fuera de alcance** de este sprint (ver D2 en `docs/DECISIONES.md`).
