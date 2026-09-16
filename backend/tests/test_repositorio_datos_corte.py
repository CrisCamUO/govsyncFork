"""Pruebas de RepositorioDatosCorteSQL::copiar_datos contra SQLite real.

TARJETA: [BD-03]
CUBRE: la copia física de PDT (meta + su programación física/financiera) y de
PROYECTOS (proyecto + sus indicadores) al crear un corte que reutiliza al
anterior (HU-01/CA-5) — el bug activo que motivó la tarjeta: `copiar_datos`
lanzaba `NotImplementedError` contra Postgres real.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.cortes.domain.entidades import TipoArchivoFuente
from app.modules.cortes.persistence.models import (
    CorteORM,
    MetaORM,
    MetaProgramacionFisicaORM,
    ProgramacionFinancieraORM,
    ProyectoIndicadorORM,
    ProyectoORM,
)
from app.modules.cortes.persistence.repositorios import RepositorioDatosCorteSQL


def _crear_corte(sesion, *, vigencia: int = 2026, fecha: date = date(2026, 1, 1)) -> uuid.UUID:
    corte_id = uuid.uuid4()
    sesion.add(CorteORM(id=corte_id, vigencia=vigencia, fecha_corte=fecha))
    sesion.flush()
    return corte_id


@pytest.fixture()
def repo(sesion) -> RepositorioDatosCorteSQL:
    return RepositorioDatosCorteSQL(sesion)


def test_copiar_datos_pdt_duplica_meta_y_su_programacion(sesion, repo) -> None:
    origen_id = _crear_corte(sesion, vigencia=2025)
    destino_id = _crear_corte(sesion, vigencia=2026)

    meta_id = uuid.uuid4()
    sesion.add(
        MetaORM(
            id=meta_id,
            corte_id=origen_id,
            cod_indicador_producto="040110500",
            nombre_producto="Meta X",
            es_principal=True,
        )
    )
    sesion.add(
        MetaProgramacionFisicaORM(
            id=uuid.uuid4(), meta_id=meta_id, anio=2026, valor_programado=Decimal("10.5")
        )
    )
    sesion.add(
        ProgramacionFinancieraORM(
            id=uuid.uuid4(),
            meta_id=meta_id,
            fuente="SGP",
            anio=2026,
            valor_programado=Decimal("1000000.00"),
        )
    )
    sesion.flush()

    filas = repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.PDT)

    assert filas == 1

    metas_destino = sesion.scalars(select(MetaORM).where(MetaORM.corte_id == destino_id)).all()
    assert len(metas_destino) == 1
    nueva_meta = metas_destino[0]
    assert nueva_meta.id != meta_id
    assert nueva_meta.cod_indicador_producto == "040110500"
    assert nueva_meta.nombre_producto == "Meta X"
    assert nueva_meta.es_principal is True

    prog_destino = sesion.scalars(
        select(MetaProgramacionFisicaORM).where(MetaProgramacionFisicaORM.meta_id == nueva_meta.id)
    ).all()
    assert len(prog_destino) == 1
    assert prog_destino[0].valor_programado == Decimal("10.5")

    fin_destino = sesion.scalars(
        select(ProgramacionFinancieraORM).where(ProgramacionFinancieraORM.meta_id == nueva_meta.id)
    ).all()
    assert len(fin_destino) == 1
    assert fin_destino[0].fuente == "SGP"

    # El corte origen queda intacto: cada corte es una fotografía independiente.
    metas_origen = sesion.scalars(select(MetaORM).where(MetaORM.corte_id == origen_id)).all()
    assert [m.id for m in metas_origen] == [meta_id]


def test_copiar_datos_proyectos_duplica_proyecto_e_indicadores(sesion, repo) -> None:
    origen_id = _crear_corte(sesion, vigencia=2025)
    destino_id = _crear_corte(sesion, vigencia=2026)

    proyecto_id = uuid.uuid4()
    proyecto = ProyectoORM(
        id=proyecto_id, corte_id=origen_id, bpin="202500000050132", nombre_proyecto="Vías"
    )
    proyecto.indicadores.append(
        ProyectoIndicadorORM(id=uuid.uuid4(), cod_indicador_producto="040110500")
    )
    proyecto.indicadores.append(
        ProyectoIndicadorORM(id=uuid.uuid4(), cod_indicador_producto="040600400")
    )
    sesion.add(proyecto)
    sesion.flush()

    filas = repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.PROYECTOS)

    assert filas == 1

    proyectos_destino = sesion.scalars(
        select(ProyectoORM).where(ProyectoORM.corte_id == destino_id)
    ).all()
    assert len(proyectos_destino) == 1
    nuevo = proyectos_destino[0]
    assert nuevo.id != proyecto_id
    assert nuevo.bpin == "202500000050132"

    indicadores_destino = sesion.scalars(
        select(ProyectoIndicadorORM).where(ProyectoIndicadorORM.proyecto_id == nuevo.id)
    ).all()
    assert {i.cod_indicador_producto for i in indicadores_destino} == {"040110500", "040600400"}

    proyectos_origen = sesion.scalars(
        select(ProyectoORM).where(ProyectoORM.corte_id == origen_id)
    ).all()
    assert [p.id for p in proyectos_origen] == [proyecto_id]


def test_copiar_datos_sin_filas_de_origen_devuelve_cero(sesion, repo) -> None:
    origen_id = _crear_corte(sesion, vigencia=2025)
    destino_id = _crear_corte(sesion, vigencia=2026)

    assert repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.PDT) == 0
    assert repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.PROYECTOS) == 0


def test_copiar_datos_con_tipo_no_copiable_lanza_value_error(sesion, repo) -> None:
    origen_id = _crear_corte(sesion, vigencia=2025)
    destino_id = _crear_corte(sesion, vigencia=2026)

    with pytest.raises(ValueError):
        repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.EJECUCION)


def test_copiar_datos_no_hace_commit(sesion, repo) -> None:
    origen_id = _crear_corte(sesion, vigencia=2025)
    destino_id = _crear_corte(sesion, vigencia=2026)
    sesion.add(
        MetaORM(
            id=uuid.uuid4(),
            corte_id=origen_id,
            cod_indicador_producto="040110500",
            es_principal=False,
        )
    )
    sesion.flush()

    repo.copiar_datos(origen_id, destino_id, TipoArchivoFuente.PDT)
    sesion.rollback()

    assert sesion.scalars(select(MetaORM)).all() == []
