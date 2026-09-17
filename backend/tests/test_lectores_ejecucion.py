"""Pruebas de resolver_hojas en lectores/ejecucion.py.

TARJETA: [HU-03][BE-01]
CUBRE: HU-03 / CA-2 — ambas pestañas (Ejecución y Contratación) se localizan
de forma independiente: la ausencia de una no impide resolver la otra, y no
se exige subirlas por separado (es un solo archivo, dos hojas).
"""

from __future__ import annotations

from app.modules.ingesta.persistence.lectores.ejecucion import resolver_hojas
from tests.fabricas import HOJA_CONTRATACION, HOJA_EJECUCION, construir_ejecucion


def test_resuelve_ambas_hojas_cuando_las_dos_existen() -> None:
    hoja_ejecucion, hoja_contratacion = resolver_hojas(construir_ejecucion(), "presupuestal.xlsx")

    assert hoja_ejecucion == HOJA_EJECUCION
    assert hoja_contratacion == HOJA_CONTRATACION


def test_resuelve_ejecucion_aunque_falte_contratacion() -> None:
    contenido = construir_ejecucion(incluir_contratacion=False)

    hoja_ejecucion, hoja_contratacion = resolver_hojas(contenido, "presupuestal.xlsx")

    assert hoja_ejecucion == HOJA_EJECUCION
    assert hoja_contratacion is None


def test_resuelve_contratacion_aunque_falte_ejecucion() -> None:
    contenido = construir_ejecucion(incluir_ejecucion=False)

    hoja_ejecucion, hoja_contratacion = resolver_hojas(contenido, "presupuestal.xlsx")

    assert hoja_ejecucion is None
    assert hoja_contratacion == HOJA_CONTRATACION


def test_ninguna_pestana_no_lanza_excepcion() -> None:
    contenido = construir_ejecucion(incluir_ejecucion=False, incluir_contratacion=False)

    assert resolver_hojas(contenido, "presupuestal.xlsx") == (None, None)
