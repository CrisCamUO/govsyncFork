"""Pruebas del endpoint de estado.

TARJETA: [DEV-07] (parte de código)

/health no depende de la base de datos (no usa SesionDep), por lo que se
prueba con la app tal cual, sin overrides de dependencias — a diferencia
de test_router_cortes.py, que sí necesita sobreescribir ServicioCortesDep.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_app


# /api/v1/salud (el alias) ya está cubierto por
# tests/test_salud.py::test_la_aplicacion_responde — no se duplica aquí.
def test_health_devuelve_200_ok():
    cliente = TestClient(crear_app())

    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
