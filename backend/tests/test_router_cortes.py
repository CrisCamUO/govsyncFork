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

import io
import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.dependencias import obtener_servicio_cortes
from app.main import crear_app
from app.modules.cortes.application.casos_uso import ServicioCortes
from app.modules.cortes.domain.entidades import (
    ArchivoFuente,
    Corte,
    EstadoCorte,
    TipoArchivoFuente,
)
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte
from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)

HOY = date(2026, 9, 8)


class RepositorioCortesEnMemoria(RepositorioCortes):
    def __init__(self) -> None:
        self._cortes: dict[uuid.UUID, Corte] = {}

    def guardar(self, corte: Corte) -> Corte:
        self._cortes[corte.id] = corte
        return corte

    def existe_borrador_activo(self) -> bool:
        return any(c.estado == EstadoCorte.BORRADOR for c in self._cortes.values())

    def existe_corte_duplicado(
        self, vigencia: int, fecha_corte: date, *, excluir_id: uuid.UUID | None = None
    ) -> bool:
        return any(
            c.vigencia == vigencia and c.fecha_corte == fecha_corte and c.id != excluir_id
            for c in self._cortes.values()
        )

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

    def confirmar_correccion(self, corte: Corte) -> None:
        self._cortes[corte.id].vigencia = corte.vigencia
        self._cortes[corte.id].fecha_corte = corte.fecha_corte


class RepositorioDatosCorteEnMemoria(RepositorioDatosCorte):
    """Los 3 métodos de carga se ejercitan (TestCargarArchivo, un tipo cada
    uno) — ya no quedan NotImplementedError aquí, mismo estado que el real
    en `develop` desde que [HU-03][BE-06]/[HU-04][BE-01] cerraron."""

    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int:
        return len(metas)

    def reemplazar_presupuesto(self, corte_id, rubros, contratos, registros) -> int:
        return len(rubros) + len(contratos) + len(registros)

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        return len(proyectos)

    def copiar_datos(self, origen_id, destino_id, tipo) -> int:
        raise NotImplementedError


class LectorPDTFalso(LectorArchivoFuente):
    """Doble mínimo: no lee Excel de verdad, solo produce un ResultadoLectura
    con una fila fija — suficiente para probar el cableado del endpoint
    (router -> ServicioCortes.cargar_archivo -> reemplazar_metas -> 201),
    no la lógica real de lectura (eso es `test_lectores_pdt.py`)."""

    tipo = TipoArchivo.PDT

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        return ResultadoLectura(
            tipo=TipoArchivo.PDT,
            filas={"metas": [{"cod_indicador_producto": "040110500", "principal": True}]},
            conteos={"metas": 1},
        )


class LectorEjecucionFalso(LectorArchivoFuente):
    """Mismo espíritu que LectorPDTFalso, para el tipo EJECUCION — el
    cableado real está en `test_lectores_ejecucion.py`, aquí solo se
    prueba router -> cargar_archivo -> reemplazar_presupuesto -> 201."""

    tipo = TipoArchivo.EJECUCION

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        return ResultadoLectura(
            tipo=TipoArchivo.EJECUCION,
            filas={
                "rubros": [{"codigo_rubro_nivel": "1", "ultimo_nivel": True}],
                "contratos": [{"numero_contrato": "1"}],
                "registros": [{"numero_contrato": "1"}],
            },
            conteos={"ejecucion": 1, "contratacion": 1},
        )


class LectorProyectosFalso(LectorArchivoFuente):
    """Mismo espíritu que LectorPDTFalso, para el tipo PROYECTOS — el
    cableado real está en `test_lectores_proyectos.py`, aquí solo se
    prueba router -> cargar_archivo -> reemplazar_proyectos -> 201."""

    tipo = TipoArchivo.PROYECTOS

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        return ResultadoLectura(
            tipo=TipoArchivo.PROYECTOS,
            filas={"proyectos": [{"bpin": "459903100000000"}]},
            conteos={"proyectos": 1},
        )


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


# --- PATCH /cortes/{id} — D11 (docs/DECISIONES.md, aclaración 2026-09-19) --


def test_patch_cortes_id_corrige_vigencia_y_fecha_200(cliente):
    creado = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()

    respuesta = cliente.patch(
        f"/api/v1/cortes/{creado['id']}",
        json={"vigencia": 2025, "fecha_corte": "2026-09-01"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["vigencia"] == 2025
    assert cuerpo["fecha_corte"] == "2026-09-01"
    assert cuerpo["estado"] == "BORRADOR"


def test_patch_cortes_id_inexistente_devuelve_404(cliente):
    respuesta = cliente.patch(
        f"/api/v1/cortes/{uuid.uuid4()}",
        json={"vigencia": 2025, "fecha_corte": "2026-09-01"},
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "recurso_no_encontrado"


def test_patch_cortes_id_sobre_corte_registrado_devuelve_409(cliente):
    creado = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()
    corte = cliente.repo_cortes.obtener(uuid.UUID(creado["id"]))
    corte.estado = EstadoCorte.REGISTRADO
    cliente.repo_cortes.confirmar_registro(corte)

    respuesta = cliente.patch(
        f"/api/v1/cortes/{creado['id']}",
        json={"vigencia": 2025, "fecha_corte": "2026-09-01"},
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detalles"]["motivo"] == "corte_no_es_borrador"


def test_patch_cortes_id_duplicado_contra_otro_corte_devuelve_409(cliente):
    otro = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2025, "fecha_corte": "2025-12-01"}
    ).json()
    corte_otro = cliente.repo_cortes.obtener(uuid.UUID(otro["id"]))
    corte_otro.estado = EstadoCorte.REGISTRADO
    cliente.repo_cortes.confirmar_registro(corte_otro)
    propio = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()

    respuesta = cliente.patch(
        f"/api/v1/cortes/{propio['id']}",
        json={"vigencia": 2025, "fecha_corte": "2025-12-01"},
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detalles"]["motivo"] == "vigencia_fecha_duplicada"


def test_patch_cortes_id_fecha_futura_devuelve_422(cliente):
    creado = cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()

    respuesta = cliente.patch(
        f"/api/v1/cortes/{creado['id']}",
        json={"vigencia": 2026, "fecha_corte": "2026-09-09"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "regla_de_negocio_violada"


# --- POST /cortes/{id}/archivos/{tipo} — [HU-02][FE-01] --------------------
#
# `cliente` (arriba) construye ServicioCortes sin `lectores` (default {}) —
# suficiente para 404/422, que fallan antes de buscar un lector. El camino
# feliz (los 3 tipos) necesita lectores reales, por eso esta fixture aparte
# en vez de tocar la compartida y arriesgar los 5 tests de arriba.
@pytest.fixture()
def cliente_con_lectores():
    repo_cortes = RepositorioCortesEnMemoria()
    servicio = ServicioCortes(
        repo_cortes=repo_cortes,
        repo_datos=RepositorioDatosCorteEnMemoria(),
        confirmar_transaccion=lambda: None,
        revertir_transaccion=lambda: None,
        lectores={
            TipoArchivoFuente.PDT: LectorPDTFalso(),
            TipoArchivoFuente.EJECUCION: LectorEjecucionFalso(),
            TipoArchivoFuente.PROYECTOS: LectorProyectosFalso(),
        },
        hoy=HOY,
    )

    app = crear_app()
    app.dependency_overrides[obtener_servicio_cortes] = lambda: servicio
    with TestClient(app) as c:
        c.repo_cortes = repo_cortes
        yield c
    app.dependency_overrides.clear()


def _crear_corte_borrador(cliente) -> str:
    return cliente.post(
        "/api/v1/cortes", json={"vigencia": 2026, "fecha_corte": "2026-09-08"}
    ).json()["id"]


def _xlsx_minimo() -> bytes:
    """.xlsx real y mínimo (SEC-03 exige la firma ZIP + estructura OOXML
    válida, no basta contenido arbitrario) — LectorPDTFalso no lo parsea,
    así que su contenido interno no importa, solo que sea un libro válido."""
    libro = Workbook()
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_post_archivos_pdt_devuelve_201(cliente_con_lectores):
    corte_id = _crear_corte_borrador(cliente_con_lectores)

    respuesta = cliente_con_lectores.post(
        f"/api/v1/cortes/{corte_id}/archivos/PDT",
        files={
            "archivo": (
                "plan.xlsx",
                _xlsx_minimo(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "PDT"
    assert cuerpo["nombre_archivo"] == "plan.xlsx"
    assert cuerpo["filas_reconocidas"] == 1


def test_post_archivos_ejecucion_devuelve_201(cliente_con_lectores):
    """Confirma que el guard que rechazaba EJECUCION con 501 ya no existe:
    [HU-03][BE-06] cerró en develop, reemplazar_presupuesto ya no lanza
    NotImplementedError (ver docs/TRAZABILIDAD.md, HU-03/CA-1)."""
    corte_id = _crear_corte_borrador(cliente_con_lectores)

    respuesta = cliente_con_lectores.post(
        f"/api/v1/cortes/{corte_id}/archivos/EJECUCION",
        files={
            "archivo": (
                "ejecucion.xlsx",
                _xlsx_minimo(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "EJECUCION"
    # 1 rubro + 1 contrato + 1 registro, ver LectorEjecucionFalso.
    assert cuerpo["filas_reconocidas"] == 3


def test_post_archivos_proyectos_devuelve_201(cliente_con_lectores):
    """Confirma que el guard que rechazaba PROYECTOS con 501 ya no existe:
    [HU-04][BE-01] cerró en develop, LectorProyectos.leer ya no lanza
    NotImplementedError (ver docs/TRAZABILIDAD.md, HU-04/CA-1)."""
    corte_id = _crear_corte_borrador(cliente_con_lectores)

    respuesta = cliente_con_lectores.post(
        f"/api/v1/cortes/{corte_id}/archivos/PROYECTOS",
        files={
            "archivo": (
                "proyectos.xlsx",
                _xlsx_minimo(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "PROYECTOS"
    assert cuerpo["filas_reconocidas"] == 1


def test_post_archivos_tipo_fuera_del_enum_devuelve_422(cliente):
    """Confirma que tipar `tipo: TipoArchivoFuente` en el endpoint basta —
    no hace falta validación propia para un valor fuera del enum."""
    corte_id = _crear_corte_borrador(cliente)

    respuesta = cliente.post(
        f"/api/v1/cortes/{corte_id}/archivos/BASURA",
        files={"archivo": ("x.xlsx", b"x", "application/octet-stream")},
    )

    assert respuesta.status_code == 422


def test_post_archivos_corte_inexistente_devuelve_404(cliente):
    respuesta = cliente.post(
        f"/api/v1/cortes/{uuid.uuid4()}/archivos/PDT",
        files={"archivo": ("plan.xlsx", b"x", "application/octet-stream")},
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "recurso_no_encontrado"
