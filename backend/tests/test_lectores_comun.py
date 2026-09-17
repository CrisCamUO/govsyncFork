"""Pruebas de las utilidades compartidas de lectura de Excel.

TARJETAS: [HU-02][BE-01] (encontrar y leer la pestaña correcta del PDT),
          [HU-03][BE-03] (mapear_columnas: unificación de los dos nombres de
          columna del indicador), [HU-04][BE-01] (rellenar_celdas_combinadas)
CUBRE: HU-02 / CA-2, HU-03 / CA-3 (CP-HU03-03 en docs/CASOS_DE_PRUEBA.md).
El rechazo por columnas faltantes (CA-3 de HU-02) es [HU-02][BE-02], la
siguiente tarjeta; aquí solo se prueba la mecánica genérica de cada función.

Nota de fusión (2026-09-17): `mapear_columnas` normalizaba con una función
propia (`_normalizar_para_comparar`) escrita cuando `normalizar_encabezado`
todavía era un stub en la rama de [HU-03][BE-03]. Al fusionar con
`[HU-02][BE-01]` (que sí la implementa) se consolidó `mapear_columnas` para
reutilizar `normalizar_encabezado` en vez de mantener dos normalizaciones del
mismo tipo de dato — ver `_comun.py::mapear_columnas`. Las pruebas de
`mapear_columnas` de abajo son las mismas 7 que trajo esa tarjeta, sin
cambios: la consolidación no les cambia el comportamiento observable.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import Workbook

from app.modules.ingesta.persistence.lectores import _comun
from app.modules.ingesta.persistence.lectores._comun import mapear_columnas
from app.modules.ingesta.persistence.lectores.ejecucion import (
    OBLIGATORIAS_CONTRATACION,
    OBLIGATORIAS_EJECUCION,
)
from app.shared.errors import ArchivoInvalido
from tests.fabricas import HOJA_PDT, HOJAS_SENUELO_PDT, construir_pdt

ALIAS_HOJA_PDT = ("Plan indicativo - Productos", "Plan indicativo Productos")


class TestNormalizarEncabezado:
    def test_quita_tildes_mayusculas_y_colapsa_espacios(self) -> None:
        assert _comun.normalizar_encabezado(" Código  de\nIndicador ") == "codigo de indicador"

    def test_valores_vacios_devuelven_cadena_vacia(self) -> None:
        assert _comun.normalizar_encabezado(None) == ""
        assert _comun.normalizar_encabezado(float("nan")) == ""


class TestResolverHoja:
    def test_encuentra_la_hoja_por_nombre_exacto(self) -> None:
        nombres = [*HOJAS_SENUELO_PDT, HOJA_PDT]
        assert _comun.resolver_hoja(nombres, ALIAS_HOJA_PDT) == HOJA_PDT

    def test_encuentra_la_hoja_truncada_a_31_caracteres(self) -> None:
        # Peculiaridad real: Excel trunca el nombre de hoja de ejecución.
        nombres = ["Formato Resumido Ejecucion Gast"]
        alias = ("Formato Resumido Ejecucion Gasto",)
        assert _comun.resolver_hoja(nombres, alias) == "Formato Resumido Ejecucion Gast"

    def test_no_confunde_con_una_hoja_de_nombre_parecido(self) -> None:
        # "Plan indicativo SGR - Productos" no es "Plan indicativo - Productos".
        nombres = ["Plan indicativo SGR - Productos", "Otra hoja"]
        assert _comun.resolver_hoja(nombres, ALIAS_HOJA_PDT) is None

    def test_ninguna_coincide_devuelve_none(self) -> None:
        assert _comun.resolver_hoja(["Hoja1"], ALIAS_HOJA_PDT) is None


class TestAbrirLibro:
    def test_abre_un_libro_valido(self) -> None:
        libro = _comun.abrir_libro(construir_pdt(), "pdt.xlsx")
        assert HOJA_PDT in libro.sheetnames

    def test_rechaza_contenido_que_no_es_un_libro(self) -> None:
        with pytest.raises(ArchivoInvalido):
            _comun.abrir_libro(b"esto no es un xlsx", "pdt.xlsx")


class TestLocalizarFilaEncabezado:
    def test_salta_la_fila_de_titulo_de_seccion(self) -> None:
        fila = _comun.localizar_fila_encabezado(
            construir_pdt(),
            HOJA_PDT,
            requeridas=("Código de indicador de producto (MGA)", "Principal"),
        )
        assert fila == 1  # fila 0 = título de sección, fila 1 = encabezado real

    def test_columnas_inexistentes_lanza_archivo_invalido(self) -> None:
        with pytest.raises(ArchivoInvalido):
            _comun.localizar_fila_encabezado(
                construir_pdt(), HOJA_PDT, requeridas=("Una columna que no existe",)
            )

    def test_hoja_inexistente_lanza_archivo_invalido(self) -> None:
        with pytest.raises(ArchivoInvalido):
            _comun.localizar_fila_encabezado(
                construir_pdt(), "Hoja que no existe", requeridas=("Principal",)
            )


class TestLeerHoja:
    def test_lee_como_texto_sin_perder_ceros_a_la_izquierda(self) -> None:
        df = _comun.leer_hoja(construir_pdt(), HOJA_PDT, fila_encabezado=1)
        codigos = df["codigo de indicador de producto (mga)"].tolist()
        assert "040110500" in codigos

    def test_no_confunde_el_codigo_sistp_con_la_llave(self) -> None:
        df = _comun.leer_hoja(construir_pdt(), HOJA_PDT, fila_encabezado=1)
        assert "IP-63" in df["codigo de indicador de producto (sispt)"].tolist()

    def test_descarta_filas_totalmente_vacias(self) -> None:
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Datos"
        hoja.append(["col1", "col2"])
        hoja.append(["a", "1"])
        hoja.append([None, None])
        hoja.append(["b", "2"])
        buffer = io.BytesIO()
        libro.save(buffer)

        df = _comun.leer_hoja(buffer.getvalue(), "Datos", fila_encabezado=0)

        assert df["col1"].tolist() == ["a", "b"]


class TestMapearColumnas:
    """[HU-03][BE-03] · CA-3: 'CodigoIndicadorCcpet' y 'Cod Indicador Ccpet'
    son el mismo dato, sin duplicar columnas."""

    def test_reconoce_el_nombre_de_ejecucion(self) -> None:
        df = pd.DataFrame({"CodigoIndicadorCcpet": ["040110500"], "Otra": ["x"]})
        assert mapear_columnas(df, OBLIGATORIAS_EJECUCION) == {
            "cod_indicador_producto": "CodigoIndicadorCcpet"
        }

    def test_reconoce_el_nombre_de_contratacion(self) -> None:
        df = pd.DataFrame({"Cod Indicador Ccpet": ["040110500"], "Otra": ["x"]})
        assert mapear_columnas(df, OBLIGATORIAS_CONTRATACION) == {
            "cod_indicador_producto": "Cod Indicador Ccpet"
        }

    def test_tolera_tildes_mayusculas_y_espacios_extra(self) -> None:
        """Peculiaridad 3 de _comun.py: encabezados inconsistentes entre cortes."""
        df = pd.DataFrame({"  CÓDIGO INDICADOR CCPET  ": ["040110500"]})
        requeridas = {"cod_indicador_producto": ("Codigo Indicador Ccpet",)}
        assert mapear_columnas(df, requeridas) == {
            "cod_indicador_producto": "  CÓDIGO INDICADOR CCPET  "
        }

    def test_columna_ausente_no_aparece_en_el_resultado(self) -> None:
        """No rechaza: eso es responsabilidad de exigir_columnas ([HU-02][BE-02])."""
        df = pd.DataFrame({"OtraColumna": ["x"]})
        assert mapear_columnas(df, OBLIGATORIAS_EJECUCION) == {}

    def test_diccionario_de_requeridas_vacio_devuelve_vacio(self) -> None:
        df = pd.DataFrame({"CodigoIndicadorCcpet": ["040110500"]})
        assert mapear_columnas(df, {}) == {}

    def test_primer_alias_en_orden_gana_si_ambos_estuvieran_presentes(self) -> None:
        """Caso borde improbable en datos reales (cada pestaña trae una sola
        grafía), pero el comportamiento debe ser determinista, no accidental."""
        df = pd.DataFrame({"Cod Indicador Ccpet": ["b"], "CodigoIndicadorCcpet": ["a"]})
        requeridas = {"cod_indicador_producto": ("CodigoIndicadorCcpet", "Cod Indicador Ccpet")}
        assert mapear_columnas(df, requeridas) == {"cod_indicador_producto": "CodigoIndicadorCcpet"}

    def test_no_confunde_columnas_de_otras_claves_logicas(self) -> None:
        df = pd.DataFrame({"CodigoIndicadorCcpet": ["a"], "NumeroContrato": ["123"]})
        requeridas = {
            "cod_indicador_producto": ("CodigoIndicadorCcpet", "Cod Indicador Ccpet"),
            "numero_contrato": ("NumeroContrato",),
        }
        assert mapear_columnas(df, requeridas) == {
            "cod_indicador_producto": "CodigoIndicadorCcpet",
            "numero_contrato": "NumeroContrato",
        }


_OBLIGATORIAS_PRUEBA = {
    "codigo_indicador": ("Código de indicador de producto (MGA)",),
    "principal": ("Principal",),
}


class TestExigirColumnas:
    def test_no_hace_nada_si_todas_estan_resueltas(self) -> None:
        mapeo = {
            "codigo_indicador": "codigo de indicador de producto (mga)",
            "principal": "principal",
        }
        _comun.exigir_columnas(mapeo, _OBLIGATORIAS_PRUEBA, "pdt.xlsx", HOJA_PDT)

    def test_rechaza_y_nombra_la_columna_que_falta(self) -> None:
        mapeo = {"codigo_indicador": "codigo de indicador de producto (mga)"}
        with pytest.raises(ArchivoInvalido) as exc:
            _comun.exigir_columnas(mapeo, _OBLIGATORIAS_PRUEBA, "pdt.xlsx", HOJA_PDT)
        assert exc.value.detalles["columnas_faltantes"] == ["Principal"]

    def test_rechaza_y_nombra_todas_las_que_faltan(self) -> None:
        with pytest.raises(ArchivoInvalido) as exc:
            _comun.exigir_columnas({}, _OBLIGATORIAS_PRUEBA, "pdt.xlsx", HOJA_PDT)
        assert set(exc.value.detalles["columnas_faltantes"]) == {
            "Código de indicador de producto (MGA)",
            "Principal",
        }


class TestRellenarCeldasCombinadas:
    """[HU-04][BE-01] · peculiaridad 6: celdas combinadas verticalmente."""

    def test_propaga_el_ultimo_valor_no_nulo_hacia_abajo(self) -> None:
        df = pd.DataFrame(
            {
                "bpin": ["202500000050132", None, "202500000050299"],
                "no contrato": ["C-001", "C-002", "C-003"],
            }
        )
        resultado = _comun.rellenar_celdas_combinadas(df, ["bpin"])
        assert resultado["bpin"].tolist() == [
            "202500000050132",
            "202500000050132",
            "202500000050299",
        ]

    def test_no_toca_columnas_que_no_se_piden(self) -> None:
        df = pd.DataFrame({"bpin": ["A", None], "no contrato": ["C-001", "C-002"]})
        resultado = _comun.rellenar_celdas_combinadas(df, ["bpin"])
        assert resultado["no contrato"].tolist() == ["C-001", "C-002"]


class TestTexto:
    def test_limpia_espacios_pero_conserva_tildes(self) -> None:
        assert _comun.texto("  Vías  ") == "Vías"

    def test_valores_vacios_devuelven_none(self) -> None:
        assert _comun.texto(None) is None
        assert _comun.texto("   ") is None
        assert _comun.texto(float("nan")) is None
