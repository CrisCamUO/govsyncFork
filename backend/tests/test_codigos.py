"""Pruebas de los objetos de valor de códigos de dominio.

TARJETA: [TRANS-01] · CAPA: Dominio (kernel compartido)
CUBRE:
- normalización desde una celda de Excel (str, int, float, NaN, None)
- conservación de los ceros a la izquierda (código MGA de 9 dígitos)
- recuperación de UN cero perdido por Excel (8 -> 9), sin fabricar códigos cortos
- rechazo de identificadores SisPT ("IP-63") y de montos ("$ 1.218.264.452")
- inmutabilidad y comparación por valor (necesarias para el cruce de HU-07)
"""

from __future__ import annotations

import pytest

from app.shared.codigos import CodigoBpin, CodigoIndicadorProducto, DescarteIndicador
from app.shared.errors import ReglaDeNegocioViolada


class TestCodigoIndicadorProducto:
    def test_acepta_nueve_digitos(self) -> None:
        assert CodigoIndicadorProducto("123456789").valor == "123456789"

    def test_conserva_el_cero_inicial(self) -> None:
        codigo = CodigoIndicadorProducto.desde_crudo("040110500")
        assert codigo is not None
        assert codigo.valor == "040110500"

    def test_recupera_un_cero_perdido_desde_texto(self) -> None:
        codigo = CodigoIndicadorProducto.desde_crudo("40110500")
        assert codigo is not None
        assert codigo.valor == "040110500"

    def test_recupera_un_cero_perdido_desde_entero(self) -> None:
        codigo = CodigoIndicadorProducto.desde_crudo(40110500)
        assert codigo is not None
        assert codigo.valor == "040110500"

    def test_recupera_un_cero_perdido_desde_float_entero(self) -> None:
        codigo = CodigoIndicadorProducto.desde_crudo(40110500.0)
        assert codigo is not None
        assert codigo.valor == "040110500"

    def test_rechaza_numero_corto_no_fabrica_un_codigo(self) -> None:
        assert CodigoIndicadorProducto.desde_crudo("12345") is None

    def test_rechaza_identificador_sistp(self) -> None:
        assert CodigoIndicadorProducto.desde_crudo("IP-63") is None

    def test_rechaza_un_monto(self) -> None:
        assert CodigoIndicadorProducto.desde_crudo("$ 1.218.264.452") is None

    def test_rechaza_mas_de_nueve_digitos(self) -> None:
        assert CodigoIndicadorProducto.desde_crudo("1234567890") is None

    @pytest.mark.parametrize(
        "vacio",
        [None, "", "   ", float("nan"), True, 40110500.5, object()],
    )
    def test_rechaza_valores_no_normalizables(self, vacio: object) -> None:
        assert CodigoIndicadorProducto.desde_crudo(vacio) is None

    def test_construccion_directa_es_estricta(self) -> None:
        # desde_crudo tolera 8 -> 9; el constructor no. Blinda la invariante.
        with pytest.raises(ReglaDeNegocioViolada):
            CodigoIndicadorProducto("40110500")

    def test_es_inmutable(self) -> None:
        codigo = CodigoIndicadorProducto("040110500")
        with pytest.raises(AttributeError):
            codigo.valor = "999999999"  # type: ignore[misc]

    def test_compara_y_hashea_por_valor(self) -> None:
        directo = CodigoIndicadorProducto("040110500")
        normalizado = CodigoIndicadorProducto.desde_crudo("40110500")
        assert directo == normalizado
        assert len({directo, normalizado}) == 1

    def test_extraer_todos_separa_el_ejemplo_real_de_la_tarjeta(self) -> None:
        celda = (
            "459903100\n"
            "Entidades, organismos y dependencias asistidos técnicamente\n"
            "$ 1.218.264.452\n"
            "\n"
            "459902300\n"
            "Sistema de Gestión implementado\n"
            "$230.000.000,00"
        )
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [
            CodigoIndicadorProducto("459903100"),
            CodigoIndicadorProducto("459902300"),
        ]
        # El "00" del monto con coma decimal se registra (limitación
        # conocida y documentada en el docstring de extraer_todos, D13):
        # no fabrica un código falso, solo entra a revisión manual.
        assert resultado.descartes == [
            DescarteIndicador(valor_crudo="00", motivo=resultado.descartes[0].motivo)
        ]

    def test_extraer_todos_ignora_nombre_y_monto_de_un_solo_bloque(self) -> None:
        celda = "040110500\nUn producto cualquiera\n$100.000"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [CodigoIndicadorProducto("040110500")]
        assert resultado.descartes == []

    def test_extraer_todos_registra_ocho_digitos_como_descarte_sin_recuperar_cero(
        self,
    ) -> None:
        # A diferencia de desde_crudo: aquí un candidato de 8 dígitos casi
        # siempre es un monto sin '$' u otro fragmento, no un código
        # truncado. No se rellena (fabricaría un código que no existe en la
        # celda real) PERO, a diferencia del comportamiento anterior a
        # [HU-04][BE-03] (D13), ya no se pierde en silencio: se registra
        # como descarte con su motivo.
        celda = "40110500\nProducto\n$100"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == []
        assert resultado.descartes == [
            DescarteIndicador(
                valor_crudo="40110500",
                motivo="8 dígitos: ni 9 ni múltiplo de 9 (no se adivina dónde cortarlo).",
            )
        ]

    def test_extraer_todos_registra_un_bpin_de_quince_digitos_como_descarte(self) -> None:
        celda = "459903100\nProducto\n202400000002842"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [CodigoIndicadorProducto("459903100")]
        assert resultado.descartes == [
            DescarteIndicador(
                valor_crudo="202400000002842",
                motivo="15 dígitos: ni 9 ni múltiplo de 9 (no se adivina dónde cortarlo).",
            )
        ]

    def test_extraer_todos_conserva_duplicados(self) -> None:
        celda = "459903100\nA\n$1\n\n459903100\nB\n$2"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [
            CodigoIndicadorProducto("459903100"),
            CodigoIndicadorProducto("459903100"),
        ]
        assert len(resultado.codigos) == 2
        assert resultado.descartes == []

    @pytest.mark.parametrize("vacio", [None, "", "   ", 459903100, float("nan")])
    def test_extraer_todos_con_entrada_no_normalizable_devuelve_vacio(self, vacio: object) -> None:
        resultado = CodigoIndicadorProducto.extraer_todos(vacio)
        assert resultado.codigos == []
        assert resultado.descartes == []

    # --- Casos borde exigidos por la tarjeta [HU-04][BE-03] (reabierta,
    # ver docs/DECISIONES.md D13) --------------------------------------

    @pytest.mark.parametrize(
        "celda",
        [
            "459903100,459902300",
            "459903100;459902300",
            "459903100-459902300",
            "459903100 459902300",
            "459903100\n459902300",
            "459903100,  459902300",
            "459903100 ; 459902300",
        ],
    )
    def test_extraer_todos_acepta_separadores_distintos(self, celda: str) -> None:
        """Coma, punto y coma, guion, espacio y salto de línea son todos
        separadores válidos entre códigos, en cualquier combinación."""
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [
            CodigoIndicadorProducto("459903100"),
            CodigoIndicadorProducto("459902300"),
        ]
        assert resultado.descartes == []

    def test_extraer_todos_segmenta_codigos_pegados_si_el_total_es_multiplo_de_nueve(
        self,
    ) -> None:
        celda = "459903100459902300"  # 18 dígitos = 2 x 9, sin separador
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == [
            CodigoIndicadorProducto("459903100"),
            CodigoIndicadorProducto("459902300"),
        ]
        assert resultado.descartes == []

    def test_extraer_todos_no_segmenta_codigos_pegados_si_el_total_no_es_multiplo_de_nueve(
        self,
    ) -> None:
        # 17 dígitos: no es múltiplo de 9 -> dato inválido, se reporta, no
        # se adivina dónde cortar.
        celda = "45990310045990230"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == []
        assert resultado.descartes == [
            DescarteIndicador(
                valor_crudo="45990310045990230",
                motivo="17 dígitos: ni 9 ni múltiplo de 9 (no se adivina dónde cortarlo).",
            )
        ]

    def test_extraer_todos_celda_vacia_o_con_texto_libre_no_produce_codigos_ni_descartes(
        self,
    ) -> None:
        celda = "Este proyecto todavía no tiene indicador de producto asignado"
        resultado = CodigoIndicadorProducto.extraer_todos(celda)
        assert resultado.codigos == []
        assert resultado.descartes == []


class TestCodigoBpin:
    def test_acepta_quince_digitos(self) -> None:
        codigo = CodigoBpin.desde_crudo("202400000002842")
        assert codigo is not None
        assert codigo.valor == "202400000002842"

    @pytest.mark.parametrize(
        "invalido",
        ["20240000000284", "2024000000028420", "IP-1", "", None, float("nan")],
    )
    def test_rechaza_longitud_distinta_de_quince(self, invalido: object) -> None:
        assert CodigoBpin.desde_crudo(invalido) is None

    def test_construccion_directa_es_estricta(self) -> None:
        with pytest.raises(ReglaDeNegocioViolada):
            CodigoBpin("123")
