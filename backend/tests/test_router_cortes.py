"""Pruebas de los endpoints de cortes (capa API), sin base de datos real.

TARJETA: [HU-01][FE-01]
CUBRE: HU-01 / CA-1, CA-2, CA-8

Prueba la traducción HTTP <-> DTO, no la persistencia: sobreescribe
`ServicioCortesDep` con un `ServicioCortes` construido sobre los mismos
repositorios en memoria que usa `test_casos_uso_cortes.py`, en vez de
`RepositorioCortesSQL` (incompleto en develop, ver [BD-02]).

Los dobles en memoria se redefinen aquí en vez de importarse de
`test_casos_uso_cortes.py` para no tocar ese archivo (es de Juan Esteban);
hay ~20 líneas de duplicación deliberada, señalada en el plan de esta
tarjeta.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.dependencias import obtener_servicio_cortes
from app.main import crear_app
from app.modules.cortes.application.casos_uso import ServicioCortes
from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, EstadoCorte
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte

HOY = date(2026, 9, 8)


class RepositorioCortesEnMemoria(RepositorioCortes):
    def __init__(self) -> None:
        self._cortes: dict[uuid.UUID, Corte] = {}

    def guardar(self, corte: Corte) -> Corte:
        self._cortes[corte.id] = corte
        return corte

    def existe_borrador_activo(self) -> bool:
        return any(c.estado == EstadoCorte.BORRADOR for c in self._cortes.values())

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
    """No se ejercita en estas pruebas: los endpoints cubiertos no lo usan."""

    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    def reemplazar_presupuesto(self, corte_id, rubros, contratos, registros) -> int:
        raise NotImplementedError

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    def copiar_datos(self, origen_id, destino_id, tipo) -> int:
        raise NotImplementedError


@pytest.fixture()
def cliente():
    repo_cortes = RepositorioCortesEnMemoria()
    servicio = ServicioCortes(
        repo_cortes=repo_cortes,
        repo_datos=RepositorioDatosCorteEnMemoria(),
        confirmar_transaccion=lambda: None,
        revertir_transaccion=lambda: None,
        hoy=HOY,
    )

    app = crear_app()
    app.dependency_overrides[obtener_servicio_cortes] = lambda: servicio
    with TestClient(app) as c:
        c.repo_cortes = repo_cortes  # D11: acceso directo para registrar cortes en pruebas
        yield c
    app.dependency_overrides.clear()


def test_post_cortes_crea_en_borrador_201(cliente):
    respuesta = cliente.post("/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"})

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "BORRADOR"
    assert cuerpo["vigencia"] == 2026
    assert cuerpo["archivos"] == []


def test_post_cortes_fecha_futura_devuelve_422_con_motivo(cliente):
    respuesta = cliente.post("/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-09"})

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "regla_de_negocio_violada"
    assert cuerpo["detalles"]["fecha_corte"] == "2026-09-09"


def test_get_cortes_devuelve_historico_200(cliente):
    primero = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()
    # D11: como máximo un BORRADOR a la vez — se registra el primero antes
    # de crear el segundo.
    corte = cliente.repo_cortes.obtener(uuid.UUID(primero["id"]))
    corte.estado = EstadoCorte.REGISTRADO
    cliente.repo_cortes.confirmar_registro(corte)
    cliente.post("/api/v1/cortes", json={"vigencia": 2025, "fecha_corte": "2025-12-01"})

    respuesta = cliente.get("/api/v1/cortes")

    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 2


def test_get_cortes_id_devuelve_detalle_200(cliente):
    creado = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()

    respuesta = cliente.get(f"/api/v1/cortes/{creado['id']}")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == creado["id"]


def test_get_cortes_id_inexistente_devuelve_404(cliente):
    respuesta = cliente.get(f"/api/v1/cortes/{uuid.uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "recurso_no_encontrado"
