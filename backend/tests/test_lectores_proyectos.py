"""Pruebas de las declaraciones de proyectos.py (sin depender de leer(), aún
NotImplementedError) y del escenario real que resuelve esta tarjeta.

TARJETA: [HU-04][BE-01] (resolver_hoja_proyectos + _comun.rellenar_celdas_combinadas)
CUBRE: HU-04 / CA-2.
"""

from __future__ import annotations

import pandas as pd
import pytest
from openpyxl import Workbook

from app.modules.ingesta.persistence.lectores import _comun
from app.modules.ingesta.persistence.lectores.proyectos import (
    LectorProyectos,
    resolver_hoja_proyectos,
)
from app.shared.codigos import CategoriaDescarte
from app.shared.errors import ArchivoInvalido
from tests.fabricas import BPIN_1, BPIN_2, HOJA_PROYECTOS, _a_bytes, construir_proyectos


class TestResolverHojaProyectos:
    def test_encuentra_la_hoja_sin_nombre_estandar(self) -> None:
        hoja, fila_encabezado = resolver_hoja_proyectos(construir_proyectos(), "proyectos.xlsx")
        assert hoja == HOJA_PROYECTOS
        assert fila_encabezado == 0

    def test_prueba_cada_hoja_hasta_encontrar_las_columnas(self) -> None:
        # La primera hoja del libro no trae las columnas requeridas; la
        # segunda sí. resolver_hoja_proyectos no puede asumir que la
        # respuesta está en la primera hoja que abre.
        libro = Workbook()
        libro.remove(libro.active)
        libro.create_sheet("Portada")["A1"] = "esta hoja no trae columnas"
        hoja_datos = libro.create_sheet("2026")
        hoja_datos.append(["Código BPIN", "Indicador de producto"])
        hoja_datos.append([BPIN_1, "459903100"])

        hoja, fila_encabezado = resolver_hoja_proyectos(_a_bytes(libro), "proyectos.xlsx")

        assert hoja == "2026"
        assert fila_encabezado == 0

    def test_lanza_archivo_invalido_si_ninguna_hoja_tiene_las_columnas(self) -> None:
        with pytest.raises(ArchivoInvalido) as exc:
            resolver_hoja_proyectos(construir_proyectos(incluir_bpin=False), "proyectos.xlsx")
        assert exc.value.detalles["motivo"] == "hoja_no_encontrada"


def test_celdas_combinadas_de_proyecto_se_propagan_a_la_fila_de_contrato() -> None:
    """Escenario real completo: resolver la hoja, leerla, y propagar BPIN y
    nombre del proyecto desde la fila combinada hacia la fila que solo trae
    datos de contrato — la peculiaridad 6 documentada en _comun.py.
    """
    contenido = construir_proyectos()
    hoja, fila_encabezado = resolver_hoja_proyectos(contenido, "proyectos.xlsx")
    df = _comun.leer_hoja(contenido, hoja, fila_encabezado)

    # Antes de propagar: la fila de contrato llega vacía en las columnas que
    # en Excel están combinadas con la fila de proyecto de arriba.
    assert df["codigo bpin"].iloc[0] == BPIN_1
    assert pd.isna(df["codigo bpin"].iloc[1])

    propagado = _comun.rellenar_celdas_combinadas(df, ["codigo bpin", "nombre del proyecto"])

    assert propagado["codigo bpin"].tolist() == [BPIN_1, BPIN_1]
    assert propagado["nombre del proyecto"].nunique() == 1


class TestLeer:
    """[HU-04][BE-01]: leer() completo — deduplicación proyecto/contrato,
    separación de indicadores multivalor (BE-03, vía
    CodigoIndicadorProducto.extraer_todos, ya probada aparte) y
    conservación de BPIN tal cual (CA-2)."""

    def test_caso_feliz_deduplica_proyecto_y_separa_indicadores(self) -> None:
        resultado = LectorProyectos().leer(construir_proyectos(), "proyectos.xlsx", vigencia=2026)

        assert resultado.conteos == {"proyectos": 1}
        assert resultado.advertencias == []
        proyecto = resultado.filas["proyectos"][0]
        assert proyecto["bpin"] == BPIN_1
        assert proyecto["nombre_proyecto"] == "Mejoramiento de vías terciarias del municipio"
        assert proyecto["codigos_indicador"] == ["170202300", "330105300"]

    def test_dos_proyectos_distintos_no_se_fusionan(self) -> None:
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Nombre del proyecto", "Indicador de producto", "No CONTRATO"])
        hoja.append([BPIN_1, "Proyecto uno", "170202300", None])
        hoja.append([BPIN_2, "Proyecto dos", "330105300", None])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.conteos == {"proyectos": 2}
        assert [p["bpin"] for p in resultado.filas["proyectos"]] == [BPIN_1, BPIN_2]

    def test_bpin_con_formato_invalido_se_conserva_tal_cual(self) -> None:
        """CA-2: 'tal cual', incluso si no cumple los 15 dígitos — no se
        rechaza ni se normaliza (a diferencia de CodigoBpin.desde_crudo)."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Nombre del proyecto", "Indicador de producto"])
        hoja.append(["BPIN-MAL-FORMADO", "Proyecto raro", "170202300"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.filas["proyectos"][0]["bpin"] == "BPIN-MAL-FORMADO"

    def test_columna_nombre_proyecto_ausente_no_rechaza_el_archivo(self) -> None:
        """nombre_proyecto es opcional (CA-3: solo bpin+indicador son ancla)."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Indicador de producto"])
        hoja.append([BPIN_1, "170202300"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.filas["proyectos"][0]["nombre_proyecto"] is None

    def test_indicador_no_reconocible_conserva_el_proyecto_con_advertencia(self) -> None:
        """CA-4 no exige rechazar el proyecto si su indicador no separa en
        ningún código válido: se conserva (tal cual, CA-2) con advertencia,
        no se descarta el proyecto completo."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Indicador de producto"])
        hoja.append([BPIN_1, "texto sin ningún código reconocible"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.filas["proyectos"][0]["codigos_indicador"] == []
        assert len(resultado.advertencias) == 1
        assert BPIN_1 in resultado.advertencias[0]

    def test_fragmento_descartado_se_propaga_estructurado_con_categoria(self) -> None:
        """D14: el DescarteIndicador crudo (con categoria) llega intacto a
        ResultadoLectura.descartes, no solo como texto en advertencias."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Indicador de producto"])
        hoja.append([BPIN_1, "170202300,2026"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.filas["proyectos"][0]["codigos_indicador"] == ["170202300"]
        assert len(resultado.descartes) == 1
        assert resultado.descartes[0].valor_crudo == "2026"
        assert resultado.descartes[0].categoria == CategoriaDescarte.LONGITUD_CORTA
        assert len(resultado.advertencias) == 1
        # [HU-04][FE-03]: el fragmento descartado ("2026") no cuenta como
        # codigo reconocido -- solo el valido llega a resultado.codigos.
        assert [c.valor for c in resultado.codigos] == ["170202300"]

    def test_codigo_repetido_entre_proyectos_se_expone_una_sola_vez_en_orden(self) -> None:
        """[HU-04][FE-03], decision del equipo 2026-09-20: resultado.codigos
        es una vista previa de QUE se reconocio, no un log de apariciones --
        el mismo codigo de indicador puede aparecer legitimamente en varios
        proyectos (docstring de contratos.py), y aqui se deduplica por
        `.valor` preservando el orden de PRIMERA aparicion en el archivo."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Indicador de producto"])
        hoja.append([BPIN_1, "459903100\n459902300"])
        hoja.append([BPIN_2, "459902300\n459903100"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        # Orden de primera aparicion (fila 1): 459903100 antes que 459902300,
        # pese a que la fila 2 los repite en orden inverso.
        assert [c.valor for c in resultado.codigos] == ["459903100", "459902300"]

    def test_indicador_con_codigos_repetidos_no_los_deduplica(self) -> None:
        """CA-4 (docstring de extraer_todos): un código repetido en la celda
        es información real, no un error — no se colapsa."""
        libro = Workbook()
        libro.remove(libro.active)
        hoja = libro.create_sheet(HOJA_PROYECTOS)
        hoja.append(["Código BPIN", "Indicador de producto"])
        hoja.append([BPIN_1, "170202300\n170202300"])
        buffer_libro = _a_bytes(libro)

        resultado = LectorProyectos().leer(buffer_libro, "proyectos.xlsx", vigencia=2026)

        assert resultado.filas["proyectos"][0]["codigos_indicador"] == ["170202300", "170202300"]
