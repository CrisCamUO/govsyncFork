"""Pruebas del caso de uso CrearCorte (aplicacion), sin base de datos.

TARJETA: [HU-01][BE-03]
CUBRE: HU-01 / CA-1, CA-8

Usa repositorios en memoria (permitidos explicitamente por el docstring de
puertos.py para pruebas unitarias) en vez de la implementacion SQLAlchemy
real de [BD-01]/[BD-02], que todavia no existe.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from app.modules.cortes.application.casos_uso import ServicioCortes
from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, EstadoCorte, TipoArchivoFuente
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte
from app.shared.errors import ReglaDeNegocioViolada


class RepositorioCortesEnMemoria(RepositorioCortes):
    def __init__(self) -> None:
        self._cortes: dict[uuid.UUID, Corte] = {}

    def guardar(self, corte: Corte) -> Corte:
        self._cortes[corte.id] = corte
        return corte

    def obtener(self, corte_id: uuid.UUID) -> Corte | None:
        return self._cortes.get(corte_id)

    def ultimo_registrado(self, vigencia: int | None = None) -> Corte | None:
        candidatos = [c for c in self._cortes.values() if c.estado == EstadoCorte.REGISTRADO]
        if vigencia is not None:
            candidatos = [c for c in candidatos if c.vigencia == vigencia]
        return max(candidatos, key=lambda c: c.fecha_corte, default=None)

    def listar(self) -> list[Corte]:
        return sorted(self._cortes.values(), key=lambda c: c.fecha_corte, reverse=True)

    def registrar_archivo(self, corte_id: uuid.UUID, archivo: ArchivoFuente) -> None:
        self._cortes[corte_id].archivos[archivo.tipo] = archivo

    def confirmar_registro(self, corte: Corte) -> None:
        self._cortes[corte.id].estado = EstadoCorte.REGISTRADO


class RepositorioDatosCorteEnMemoria(RepositorioDatosCorte):
    """reemplazar_* no se ejercita aqui: crear_corte y listar_cortes no lo usan.

    copiar_datos SI se ejercita (HU-01/BE-04): registra cada llamada para que
    las pruebas verifiquen que crear_corte pide copiar exactamente lo que
    corresponde, y devuelve un conteo fijo simulando la copia real.
    """

    def __init__(self) -> None:
        self.llamadas_copiar_datos: list[tuple[uuid.UUID, uuid.UUID, TipoArchivoFuente]] = []

    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    def reemplazar_presupuesto(self, corte_id, rubros, contratos, registros) -> int:
        raise NotImplementedError

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    def copiar_datos(self, origen_id: uuid.UUID, destino_id: uuid.UUID, tipo) -> int:
        self.llamadas_copiar_datos.append((origen_id, destino_id, tipo))
        return 7  # valor arbitrario: aqui solo importa que se llamo y con que argumentos


@pytest.fixture()
def servicio():
    llamadas = {"commit": 0, "rollback": 0}
    servicio = ServicioCortes(
        repo_cortes=RepositorioCortesEnMemoria(),
        repo_datos=RepositorioDatosCorteEnMemoria(),
        confirmar_transaccion=lambda: llamadas.__setitem__("commit", llamadas["commit"] + 1),
        revertir_transaccion=lambda: llamadas.__setitem__("rollback", llamadas["rollback"] + 1),
        hoy=date(2026, 9, 8),
    )
    servicio.llamadas = llamadas  # type: ignore[attr-defined]
    return servicio


def test_crear_corte_queda_en_borrador_con_los_tres_archivos_faltantes(servicio):
    corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    assert corte.estado == EstadoCorte.BORRADOR
    assert set(corte.archivos_faltantes()) == {
        TipoArchivoFuente.PDT,
        TipoArchivoFuente.EJECUCION,
        TipoArchivoFuente.PROYECTOS,
    }
    assert servicio.llamadas["commit"] == 1
    assert servicio.llamadas["rollback"] == 0


def test_crear_corte_rechaza_fecha_futura_sin_persistir_nada(servicio):
    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 9))

    assert servicio.listar_cortes() == []
    assert servicio.llamadas["commit"] == 0


def test_listar_cortes_devuelve_lo_creado(servicio):
    servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
    servicio.crear_corte(vigencia=2025, fecha_corte=date(2025, 12, 1))

    cortes = servicio.listar_cortes()

    assert len(cortes) == 2
    assert {c.vigencia for c in cortes} == {2026, 2025}


def _crear_corte_registrado_con_archivos(servicio, *, vigencia: int, fecha_corte: date) -> Corte:
    """Helper: un corte REGISTRADO con los 3 archivos, para simular 'el corte
    anterior' del que HU-01/CA-5 debe reutilizar. Usa los repositorios en
    memoria directamente porque registrar_corte ([HU-01][BE-05]) todavia no
    existe en el caso de uso.
    """
    corte = servicio.crear_corte(vigencia=vigencia, fecha_corte=fecha_corte)
    for tipo, nombre, filas in (
        (TipoArchivoFuente.PDT, "pdt_2025.xlsx", 144),
        (TipoArchivoFuente.EJECUCION, "ejecucion_2025.xlsx", 485),
        (TipoArchivoFuente.PROYECTOS, "proyectos_2025.xlsx", 38),
    ):
        servicio._cortes.registrar_archivo(
            corte.id, ArchivoFuente(tipo=tipo, nombre_archivo=nombre, filas_reconocidas=filas)
        )
    corte.estado = EstadoCorte.REGISTRADO
    servicio._cortes.confirmar_registro(corte)
    return corte


def test_crear_corte_reutiliza_pdt_y_proyectos_del_ultimo_registrado_de_la_misma_vigencia(
    servicio,
):
    anterior = _crear_corte_registrado_con_archivos(
        servicio, vigencia=2026, fecha_corte=date(2026, 3, 31)
    )

    nuevo = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    pdt = nuevo.archivos[TipoArchivoFuente.PDT]
    proyectos = nuevo.archivos[TipoArchivoFuente.PROYECTOS]
    assert pdt.reutilizado is True
    assert pdt.corte_origen_id == anterior.id
    assert pdt.nombre_archivo == "pdt_2025.xlsx"
    assert proyectos.reutilizado is True
    assert proyectos.corte_origen_id == anterior.id
    # HU-01/CA-7: la ejecucion NUNCA se reutiliza, sin importar que el corte
    # anterior la tuviera cargada.
    assert TipoArchivoFuente.EJECUCION not in nuevo.archivos
    assert nuevo.archivos_faltantes() == [TipoArchivoFuente.EJECUCION]


def test_crear_corte_reutilizacion_copia_los_datos_de_origen(servicio):
    anterior = _crear_corte_registrado_con_archivos(
        servicio, vigencia=2026, fecha_corte=date(2026, 3, 31)
    )

    nuevo = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    llamadas = {
        (o, d, t) for o, d, t in servicio._datos.llamadas_copiar_datos
    }
    assert (anterior.id, nuevo.id, TipoArchivoFuente.PDT) in llamadas
    assert (anterior.id, nuevo.id, TipoArchivoFuente.PROYECTOS) in llamadas
    assert not any(t == TipoArchivoFuente.EJECUCION for _, _, t in llamadas)
    # El conteo de filas reutilizadas viene de copiar_datos, no del archivo origen.
    assert nuevo.archivos[TipoArchivoFuente.PDT].filas_reconocidas == 7


def test_crear_corte_no_reutiliza_de_otra_vigencia(servicio):
    _crear_corte_registrado_con_archivos(servicio, vigencia=2025, fecha_corte=date(2025, 12, 31))

    nuevo = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 3, 31))

    assert nuevo.archivos == {}
    assert servicio._datos.llamadas_copiar_datos == []


def test_crear_corte_sin_corte_anterior_no_reutiliza_nada(servicio):
    nuevo = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 3, 31))

    assert nuevo.archivos == {}
    assert servicio._datos.llamadas_copiar_datos == []
