"""Pruebas de las declaraciones de pdt.py (sin depender de leer(), aún NotImplementedError).

TARJETA: [HU-02][BE-02]
CUBRE: HU-02 / CA-3 — que los alias declarados en OBLIGATORIAS realmente
coincidan con los encabezados del archivo real (regresión: si alguien cambia
uno de los dos sin el otro, esta prueba lo detecta).
"""

from __future__ import annotations

from app.modules.ingesta.persistence.lectores import _comun
from app.modules.ingesta.persistence.lectores.pdt import (
    OBLIGATORIAS,
    alias_columna_programacion,
)

_ENCABEZADOS_REALES = (
    "Código de indicador de producto (MGA)",
    "Código de indicador de producto (SisPT)",
    "Producto (MGA)",
    "Indicador de Producto(MGA)",
    "Principal",
    "Programación del producto bien o servicio 2026",
    "Total 2026",
)


def test_alias_de_obligatorias_coinciden_con_encabezados_reales() -> None:
    normalizados_reales = {_comun.normalizar_encabezado(c) for c in _ENCABEZADOS_REALES}
    for alias in OBLIGATORIAS.values():
        assert any(_comun.normalizar_encabezado(a) in normalizados_reales for a in alias)


def test_alias_columna_programacion_coincide_con_el_encabezado_real_de_esa_vigencia() -> None:
    generado = alias_columna_programacion(2026)
    normalizados_reales = {_comun.normalizar_encabezado(c) for c in _ENCABEZADOS_REALES}
    assert _comun.normalizar_encabezado(generado) in normalizados_reales


def test_alias_columna_programacion_cambia_con_la_vigencia() -> None:
    assert alias_columna_programacion(2025) != alias_columna_programacion(2026)
