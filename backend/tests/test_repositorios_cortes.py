"""Pruebas de RepositorioCortesSQL contra una base SQLite real.

TARJETA: [BD-02]
CUBRE: la prueba mínima de la tarjeta — «guardar y recuperar un corte; el ORM
no se filtra al dominio» — más la paridad de comportamiento con el repositorio
en memoria de test_casos_uso_cortes.py.

La fixture `sesion` (conftest.py) crea las tablas con `Base.metadata.create_all`
sobre SQLite en memoria. Las particularidades de PostgreSQL (índice único
parcial) las verifica el job de CI que aplica la migración.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import Base
from app.modules.cortes.domain.entidades import (
    ArchivoFuente,
    Corte,
    EstadoCorte,
    TipoArchivoFuente,
)
from app.modules.cortes.persistence.models import ArchivoFuenteORM
from app.modules.cortes.persistence.repositorios import RepositorioCortesSQL
from app.shared.errors import RecursoNoEncontrado


@pytest.fixture()
def repo(sesion) -> RepositorioCortesSQL:
    return RepositorioCortesSQL(sesion)


def test_guardar_y_obtener_hacen_round_trip(repo) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))

    guardado = repo.guardar(corte)
    recuperado = repo.obtener(corte.id)

    assert recuperado is not None
    assert recuperado.id == corte.id
    assert recuperado.vigencia == 2026
    assert recuperado.fecha_corte == date(2026, 6, 30)
    assert recuperado.estado == EstadoCorte.BORRADOR
    assert guardado.id == corte.id


def test_lo_recuperado_es_entidad_de_dominio_no_orm(repo) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    repo.guardar(corte)

    recuperado = repo.obtener(corte.id)

    assert isinstance(recuperado, Corte)
    assert not isinstance(recuperado, Base)


def test_obtener_corte_inexistente_devuelve_none(repo) -> None:
    assert repo.obtener(Corte(vigencia=2026, fecha_corte=date(2026, 6, 30)).id) is None


def test_listar_ordena_del_mas_reciente_al_mas_antiguo(repo) -> None:
    # Vigencias distintas: el índice único parcial solo admite un BORRADOR por vigencia.
    repo.guardar(Corte(vigencia=2024, fecha_corte=date(2024, 12, 31)))
    repo.guardar(Corte(vigencia=2025, fecha_corte=date(2025, 3, 31)))
    repo.guardar(Corte(vigencia=2026, fecha_corte=date(2026, 6, 30)))

    fechas = [c.fecha_corte for c in repo.listar()]

    assert fechas == [date(2026, 6, 30), date(2025, 3, 31), date(2024, 12, 31)]


def test_ultimo_registrado_ignora_los_borradores(repo, sesion) -> None:
    # El REGISTRADO se guarda y confirma primero; solo entonces cabe un BORRADOR
    # de la misma vigencia (índice único parcial WHERE estado='BORRADOR').
    registrado = Corte(vigencia=2026, fecha_corte=date(2026, 3, 31))
    repo.guardar(registrado)
    registrado.estado = EstadoCorte.REGISTRADO
    repo.confirmar_registro(registrado)
    repo.guardar(Corte(vigencia=2026, fecha_corte=date(2026, 6, 30)))

    ultimo = repo.ultimo_registrado()

    assert ultimo is not None
    assert ultimo.id == registrado.id


def test_ultimo_registrado_filtra_por_vigencia(repo) -> None:
    c2025 = Corte(vigencia=2025, fecha_corte=date(2025, 12, 31))
    c2026 = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    for c in (c2025, c2026):
        repo.guardar(c)
        c.estado = EstadoCorte.REGISTRADO
        repo.confirmar_registro(c)

    assert repo.ultimo_registrado(vigencia=2025).id == c2025.id
    assert repo.ultimo_registrado(vigencia=2024) is None


def test_registrar_archivo_inserta_y_luego_reemplaza(repo, sesion) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    repo.guardar(corte)

    repo.registrar_archivo(
        corte.id, ArchivoFuente(TipoArchivoFuente.PDT, "pdt_v1.xlsx", filas_reconocidas=10)
    )
    repo.registrar_archivo(
        corte.id, ArchivoFuente(TipoArchivoFuente.PDT, "pdt_v2.xlsx", filas_reconocidas=42)
    )

    filas = sesion.scalars(
        select(ArchivoFuenteORM).where(ArchivoFuenteORM.corte_id == corte.id)
    ).all()
    assert len(filas) == 1
    assert filas[0].nombre_archivo == "pdt_v2.xlsx"
    assert filas[0].filas_reconocidas == 42

    recuperado = repo.obtener(corte.id)
    assert recuperado.archivos[TipoArchivoFuente.PDT].nombre_archivo == "pdt_v2.xlsx"


def test_confirmar_registro_persiste_el_estado(repo) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    repo.guardar(corte)
    corte.estado = EstadoCorte.REGISTRADO

    repo.confirmar_registro(corte)

    assert repo.obtener(corte.id).estado == EstadoCorte.REGISTRADO


def test_confirmar_registro_de_corte_inexistente_lanza_recurso_no_encontrado(repo) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    corte.estado = EstadoCorte.REGISTRADO

    with pytest.raises(RecursoNoEncontrado) as exc:
        repo.confirmar_registro(corte)

    assert exc.value.detalles["motivo"] == "corte_no_encontrado"


def test_el_repositorio_no_hace_commit(repo, sesion) -> None:
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    repo.guardar(corte)

    sesion.rollback()

    assert repo.obtener(corte.id) is None
