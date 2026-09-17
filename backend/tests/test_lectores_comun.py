"""Pruebas de las utilidades compartidas de lectura (capa Persistencia).

TARJETA: [HU-03][BE-03] Unificación de los dos nombres de columna del indicador
CUBRE: HU-03/CA-3 (CP-HU03-03 en docs/CASOS_DE_PRUEBA.md)

Solo prueba `mapear_columnas`: es la única función de `_comun.py` que no
depende de `resolver_hoja`/`abrir_libro`/`leer_hoja` ([HU-02][BE-01],
[HU-03][BE-01], todavía sin implementar). El resto del módulo queda fuera de
alcance de esta tarjeta.
"""

from __future__ import annotations

import pandas as pd

from app.modules.ingesta.persistence.lectores._comun import mapear_columnas
from app.modules.ingesta.persistence.lectores.ejecucion import (
    OBLIGATORIAS_CONTRATACION,
    OBLIGATORIAS_EJECUCION,
)


def test_reconoce_el_nombre_de_ejecucion():
    df = pd.DataFrame({"CodigoIndicadorCcpet": ["040110500"], "Otra": ["x"]})
    assert mapear_columnas(df, OBLIGATORIAS_EJECUCION) == {
        "cod_indicador_producto": "CodigoIndicadorCcpet"
    }


def test_reconoce_el_nombre_de_contratacion():
    df = pd.DataFrame({"Cod Indicador Ccpet": ["040110500"], "Otra": ["x"]})
    assert mapear_columnas(df, OBLIGATORIAS_CONTRATACION) == {
        "cod_indicador_producto": "Cod Indicador Ccpet"
    }


def test_tolera_tildes_mayusculas_y_espacios_extra():
    """Peculiaridad 3 de _comun.py: encabezados inconsistentes entre cortes."""
    df = pd.DataFrame({"  CÓDIGO INDICADOR CCPET  ": ["040110500"]})
    requeridas = {"cod_indicador_producto": ("Codigo Indicador Ccpet",)}
    assert mapear_columnas(df, requeridas) == {
        "cod_indicador_producto": "  CÓDIGO INDICADOR CCPET  "
    }


def test_columna_ausente_no_aparece_en_el_resultado():
    """No rechaza: eso es responsabilidad de exigir_columnas ([HU-02][BE-02])."""
    df = pd.DataFrame({"OtraColumna": ["x"]})
    assert mapear_columnas(df, OBLIGATORIAS_EJECUCION) == {}


def test_diccionario_de_requeridas_vacio_devuelve_vacio():
    df = pd.DataFrame({"CodigoIndicadorCcpet": ["040110500"]})
    assert mapear_columnas(df, {}) == {}


def test_primer_alias_en_orden_gana_si_ambos_estuvieran_presentes():
    """Caso borde improbable en datos reales (cada pestaña trae una sola
    grafía), pero el comportamiento debe ser determinista, no accidental."""
    df = pd.DataFrame({"Cod Indicador Ccpet": ["b"], "CodigoIndicadorCcpet": ["a"]})
    requeridas = {"cod_indicador_producto": ("CodigoIndicadorCcpet", "Cod Indicador Ccpet")}
    assert mapear_columnas(df, requeridas) == {"cod_indicador_producto": "CodigoIndicadorCcpet"}


def test_no_confunde_columnas_de_otras_claves_logicas():
    df = pd.DataFrame({"CodigoIndicadorCcpet": ["a"], "NumeroContrato": ["123"]})
    requeridas = {
        "cod_indicador_producto": ("CodigoIndicadorCcpet", "Cod Indicador Ccpet"),
        "numero_contrato": ("NumeroContrato",),
    }
    assert mapear_columnas(df, requeridas) == {
        "cod_indicador_producto": "CodigoIndicadorCcpet",
        "numero_contrato": "NumeroContrato",
    }
