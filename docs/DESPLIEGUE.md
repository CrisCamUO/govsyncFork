# Despliegue — GovSync

## Migraciones manuales contra la base de datos real de Render

`[DEV-07]` corre migraciones **manualmente**, no automáticamente en cada
deploy — decisión explícita: una migración con error no debe tumbar el
Web Service en producción sin aviso previo. El `Start Command` de Render
NO encadena `alembic upgrade head`; solo levanta `uvicorn`.

Esto significa que, cada vez que se fusiona una migración nueva a
`develop`/`main`, alguien tiene que aplicarla a mano contra la base de
datos de Render. Pasos:

### 1. Conseguir la URL externa de la base de datos

En el dashboard de Render, la base de datos Postgres → pestaña **Connect**
→ **External Database URL** (no la "Internal Database URL": esa solo es
alcanzable desde dentro de la red de Render, no desde tu máquina).

### 2. Corregir el prefijo del driver

La URL que Render genera viene como `postgresql://...`. El proyecto usa
`psycopg3` (`backend/requirements.txt`, ver también
`backend/.env.example`), así que hay que agregar `+psycopg` a mano:

```
postgresql://usuario:clave@host/basededatos          ← como la da Render
postgresql+psycopg://usuario:clave@host/basededatos  ← lo que hay que usar
```

### 3. Pasarla como variable de entorno temporal — nunca guardarla en archivo

```bash
cd backend
DATABASE_URL="postgresql+psycopg://usuario:clave@host/basededatos" \
  alembic upgrade head
```

En PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:clave@host/basededatos"
alembic upgrade head
Remove-Item Env:DATABASE_URL
```

**No la pegues en `.env`, ni en ningún archivo del repo, ni en un script
que quede guardado.** Es la contraseña real de la base de datos de
producción — mismo principio que `docs/SEGURIDAD.md` (§Manejo de
secretos): vive en la sesión de terminal, nada más, y solo mientras dura
el comando.

### 4. Nunca repetir esto sobre una base con datos reales sin respaldo previo

Antes de correr `alembic upgrade head` (o `downgrade`) contra la base de
Render una vez ya tenga datos reales de la clienta cargados: **tomar un
respaldo primero** (Render permite backups manuales desde el dashboard de
la base de datos, o `pg_dump` contra la External Database URL). Una
migración mal escrita contra una base vacía es un problema de desarrollo;
la misma migración contra datos reales sin respaldo es una pérdida de
información irreversible.

El job automático `migrate-render` (`ci.yml`) NO hace respaldo antes de
migrar — riesgo aceptado conscientemente dado el volumen de datos
actual. Si una futura migración borra o transforma datos de forma
irreversible, quien la escriba es responsable de respaldar manualmente
ANTES de fusionar a `main`, no confiar en el job automático para eso.

Antes de aprobar un PR que modifique una migración de forma
destructiva (`DROP COLUMN`, `ALTER TYPE` que pueda truncar datos,
`DELETE`), quien revisa debe exigir evidencia de un respaldo manual
reciente en la descripción del PR — el job automático no lo hace por
ustedes.
