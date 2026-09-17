"""Carga datos de ejemplo en la base de datos local, para explorarla a mano
(pgAdmin, DBeaver, psql) mientras no hay un pipeline ETL real todavía.

NO es un fixture de pruebas automatizadas (para eso están `tests/fabricas.py`
y la fixture `sesion` de `tests/conftest.py`, que usan SQLite en memoria).
Este script escribe en la base real configurada por DATABASE_URL — pensado
para correr una vez contra el Postgres local de `docker compose up -d`.

Uso (desde `backend/`, con el venv activo):

    python scripts/cargar_datos_ejemplo.py

Es idempotente por rechazo: si ya hay un corte cargado, no inserta nada más
y avisa — corre `TRUNCATE` manualmente si de verdad quieres repetir la carga.

Los códigos y valores no son inventados al azar: son los mismos casos de
prueba ya documentados en `tests/fabricas.py` y en los docstrings de
`shared/codigos.py` / `persistence/models.py` (el código que empieza en
cero, el BPIN de ejemplo, etc.), para que lo que se vea en la BD combine con
lo que ya se explicó en el resto del proyecto.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.modules.cortes.domain.entidades import EstadoCorte, TipoArchivoFuente
from app.modules.cortes.persistence.models import (
    ArchivoFuenteORM,
    ContratoORM,
    CorteORM,
    MetaORM,
    MetaProgramacionFisicaORM,
    ProgramacionFinancieraORM,
    ProyectoIndicadorORM,
    ProyectoORM,
    RegistroPresupuestalORM,
    RubroORM,
)

# Mismos códigos que tests/fabricas.py, para que el ejemplo manual y las
# pruebas automatizadas hablen del mismo caso.
COD_A = "170202300"
COD_B = "040110500"  # empieza en cero: el caso que rompe un dtype numérico
COD_C = "330105300"
BPIN_1 = "202500000050132"
BPIN_2 = "202500000050299"


def main() -> None:
    sesion = SessionLocal()
    try:
        if sesion.query(CorteORM).count() > 0:
            print("Ya hay al menos un corte cargado. No se insertó nada nuevo.")
            print("Si quieres repetir la carga, vacía las tablas manualmente primero.")
            return

        corte = CorteORM(
            id=uuid.uuid4(),
            vigencia=2026,
            fecha_corte=date(2026, 6, 30),
            estado=EstadoCorte.REGISTRADO,
        )
        sesion.add(corte)
        # flush: ninguna de las tablas de abajo tiene relationship() hacia
        # CorteORM (solo archivo_fuente la tiene, y aquí no se usa), así que
        # el ordenamiento automático de inserts de SQLAlchemy no sabe que
        # dependen de "corte" — sin este flush, Postgres rechaza el INSERT
        # de "contrato"/"rubro"/etc. con FK violation porque corte_id todavía
        # no existe en la tabla corte.
        sesion.flush()

        for tipo, nombre, filas in (
            (TipoArchivoFuente.PDT, "plan_indicativo_2026.xlsx", 144),
            (TipoArchivoFuente.EJECUCION, "ejecucion_presupuestal_2026.xlsx", 485),
            (TipoArchivoFuente.PROYECTOS, "proyectos_bpin_2026.xlsx", 38),
        ):
            sesion.add(
                ArchivoFuenteORM(
                    id=uuid.uuid4(),
                    corte_id=corte.id,
                    tipo=tipo,
                    nombre_archivo=nombre,
                    filas_reconocidas=filas,
                )
            )

        # --- Metas del PDT (dos, una con el código que empieza en cero) ----
        meta_a = MetaORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            cod_indicador_producto=COD_A,
            cod_indicador_sistp="IP-63",
            nombre_producto="Vías terciarias mantenidas",
            unidad_medida="Kilómetros",
            meta_cuatrienio=Decimal("40.0000"),
            es_principal=True,
            bpin_relacionados=BPIN_1,
        )
        meta_b = MetaORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            cod_indicador_producto=COD_B,
            cod_indicador_sistp="IP-40",
            nombre_producto="Entidades asistidas técnicamente",
            unidad_medida="Número",
            meta_cuatrienio=Decimal("5.0000"),
            es_principal=True,
            bpin_relacionados=BPIN_2,
        )
        sesion.add_all([meta_a, meta_b])
        sesion.flush()  # meta_programacion_fisica/programacion_financiera referencian meta_id
        sesion.add_all(
            [
                MetaProgramacionFisicaORM(
                    id=uuid.uuid4(), meta_id=meta_a.id, anio=2026, valor_programado=Decimal("10.0")
                ),
                MetaProgramacionFisicaORM(
                    id=uuid.uuid4(), meta_id=meta_b.id, anio=2026, valor_programado=Decimal("2.0")
                ),
            ]
        )
        sesion.add_all(
            [
                ProgramacionFinancieraORM(
                    id=uuid.uuid4(),
                    meta_id=meta_a.id,
                    fuente="SGP",
                    anio=2026,
                    valor_programado=Decimal("1218264452.00"),
                ),
                ProgramacionFinancieraORM(
                    id=uuid.uuid4(),
                    meta_id=meta_b.id,
                    fuente="Recursos propios",
                    anio=2026,
                    valor_programado=Decimal("230000000.00"),
                ),
            ]
        )

        # --- Ejecución presupuestal: un subtotal y sus dos hojas -----------
        rubro_subtotal = RubroORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            codigo_rubro_nivel="2.3.2",
            codigo_rubro_completo="2.3.2-Actual-ALCALDIA-1",
            ultimo_nivel=False,
            apropiacion_definitiva=Decimal("2000000000.00"),
        )
        rubro_hoja_a = RubroORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            codigo_rubro_nivel="2.3.2.1",
            codigo_rubro_completo="2.3.2.1-Actual-ALCALDIA-1",
            cod_indicador_producto=COD_A,
            ultimo_nivel=True,
            apropiacion_definitiva=Decimal("1218264452.00"),
            disponibilidad_acumulada=Decimal("1218264452.00"),
            compromiso_acumulado=Decimal("900000000.00"),
            obligacion_acumulada=Decimal("700000000.00"),
            pago_acumulado=Decimal("700000000.00"),
        )
        rubro_hoja_b = RubroORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            codigo_rubro_nivel="2.3.2.2",
            codigo_rubro_completo="2.3.2.2-Actual-ALCALDIA-1",
            cod_indicador_producto=COD_B,
            ultimo_nivel=True,
            apropiacion_definitiva=Decimal("230000000.00"),
            disponibilidad_acumulada=Decimal("230000000.00"),
            compromiso_acumulado=Decimal("180000000.00"),
            obligacion_acumulada=Decimal("100000000.00"),
            pago_acumulado=Decimal("100000000.00"),
        )
        sesion.add_all([rubro_subtotal, rubro_hoja_a, rubro_hoja_b])
        sesion.flush()  # registro_presupuestal referencia rubro_id

        # --- Contratación: un contrato con dos registros presupuestales ----
        contrato = ContratoORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            numero_contrato="C-2026-001",
            objeto="Mantenimiento de vías terciarias",
            nit_contratista="900123456-7",
            nombre_contratista="Construcciones del Cauca SAS",
            valor_contrato=Decimal("900000000.00"),
            valor_pagado=Decimal("700000000.00"),
            bpin=BPIN_1,
            cod_indicador_producto=COD_A,
        )
        sesion.add(contrato)
        sesion.flush()  # registro_presupuestal referencia contrato_id
        sesion.add_all(
            [
                RegistroPresupuestalORM(
                    id=uuid.uuid4(),
                    contrato_id=contrato.id,
                    rubro_id=rubro_hoja_a.id,
                    numero_cdp="CDP-001",
                    fecha_cdp=date(2026, 2, 1),
                    valor_cdp=Decimal("900000000.00"),
                    numero_registro="RP-001",
                    fecha_registro=date(2026, 2, 5),
                    valor_registro_ptal=Decimal("900000000.00"),
                    valor_pagos=Decimal("700000000.00"),
                ),
                RegistroPresupuestalORM(
                    id=uuid.uuid4(),
                    contrato_id=contrato.id,
                    rubro_id=rubro_hoja_a.id,
                    numero_cdp="CDP-002",
                    fecha_cdp=date(2026, 5, 10),
                    valor_cdp=Decimal("50000000.00"),
                    numero_registro="RP-002",
                    fecha_registro=date(2026, 5, 12),
                    valor_registro_ptal=Decimal("50000000.00"),
                    valor_pagos=Decimal("0.00"),
                ),
            ]
        )

        # --- Plantilla de proyectos BPIN, con indicadores separados --------
        proyecto = ProyectoORM(
            id=uuid.uuid4(),
            corte_id=corte.id,
            bpin=BPIN_1,
            nombre_proyecto="Mejoramiento de vías terciarias del municipio",
            indicador_producto_raw=f"{COD_A}\n{COD_C}",
        )
        proyecto.indicadores.append(
            ProyectoIndicadorORM(id=uuid.uuid4(), cod_indicador_producto=COD_A)
        )
        proyecto.indicadores.append(
            ProyectoIndicadorORM(id=uuid.uuid4(), cod_indicador_producto=COD_C)
        )
        sesion.add(proyecto)

        sesion.commit()
        print(f"Corte {corte.id} (vigencia {corte.vigencia}) cargado con datos de ejemplo:")
        print("  - 2 metas del PDT (una con código que empieza en cero: 040110500)")
        print("  - 1 rubro subtotal + 2 hojas de ejecución")
        print("  - 1 contrato con 2 registros presupuestales")
        print("  - 1 proyecto BPIN con 2 indicadores asociados")
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


if __name__ == "__main__":
    main()
