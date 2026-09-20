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
from app.modules.ingesta.domain.contratos import ResultadoLectura
from app.modules.ingesta.domain.contratos import TipoArchivo as TipoArchivoIngesta
from app.modules.ingesta.persistence.lectores.pdt import LectorPDT
from app.shared.codigos import CategoriaDescarte, CodigoIndicadorProducto, DescarteIndicador
from app.shared.errors import (
    ArchivoInvalido,
    OperacionNoPermitida,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)
from tests.fabricas import construir_pdt


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
    """reemplazar_* no se ejercita aqui: crear_corte y listar_cortes no lo usan.

    copiar_datos SI se ejercita (HU-01/BE-04): registra cada llamada para que
    las pruebas verifiquen que crear_corte pide copiar exactamente lo que
    corresponde, y devuelve un conteo fijo simulando la copia real.
    """

    def __init__(self) -> None:
        self.llamadas_copiar_datos: list[tuple[uuid.UUID, uuid.UUID, TipoArchivoFuente]] = []
        self.llamadas_reemplazar_metas: list[tuple[uuid.UUID, list[dict[str, Any]]]] = []
        self.llamadas_reemplazar_presupuesto: list[
            tuple[uuid.UUID, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
        ] = []
        self.llamadas_reemplazar_proyectos: list[tuple[uuid.UUID, list[dict[str, Any]]]] = []

    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int:
        self.llamadas_reemplazar_metas.append((corte_id, metas))
        return len(metas)

    def reemplazar_presupuesto(self, corte_id, rubros, contratos, registros) -> int:
        self.llamadas_reemplazar_presupuesto.append((corte_id, rubros, contratos, registros))
        return len(rubros) + len(contratos) + len(registros)

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        self.llamadas_reemplazar_proyectos.append((corte_id, proyectos))
        return len(proyectos)

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


def test_crear_corte_rechaza_si_ya_existe_borrador_activo_de_otra_vigencia(servicio):
    # D11: la regla es global — un BORRADOR de OTRA vigencia también bloquea.
    servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    with pytest.raises(OperacionNoPermitida) as exc:
        servicio.crear_corte(vigencia=2025, fecha_corte=date(2025, 12, 1))

    assert exc.value.detalles["motivo"] == "borrador_activo_existente"
    assert len(servicio.listar_cortes()) == 1
    assert servicio.llamadas["commit"] == 1
    assert servicio.llamadas["rollback"] == 0


def test_crear_corte_rechaza_vigencia_y_fecha_duplicada(servicio):
    # D9: la misma vigencia+fecha_corte de un corte YA REGISTRADO también se
    # rechaza (regresión: antes esto llegaba como IntegrityError crudo/500,
    # solo el índice único de BD lo detenía, sin excepción de dominio).
    anterior = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 6, 30))
    anterior.estado = EstadoCorte.REGISTRADO
    servicio._cortes.confirmar_registro(anterior)

    with pytest.raises(OperacionNoPermitida) as exc:
        servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 6, 30))

    assert exc.value.detalles["motivo"] == "vigencia_fecha_duplicada"
    assert len(servicio.listar_cortes()) == 1


def test_listar_cortes_devuelve_lo_creado(servicio):
    # D11: como máximo un BORRADOR en toda la tabla — se registra el primero
    # antes de crear el segundo.
    primero = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
    primero.estado = EstadoCorte.REGISTRADO
    servicio._cortes.confirmar_registro(primero)
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

    llamadas = {(o, d, t) for o, d, t in servicio._datos.llamadas_copiar_datos}
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


class TestRegistrarCorte:
    def test_rechaza_sin_los_tres_archivos_y_no_toca_la_transaccion(self, servicio):
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        llamadas_previas = dict(servicio.llamadas)

        with pytest.raises(OperacionNoPermitida):
            servicio.registrar_corte(corte.id)

        assert servicio._cortes.obtener(corte.id).estado == EstadoCorte.BORRADOR
        # corte.registrar() valida antes de tocar el repositorio: si falla,
        # no hubo nada que confirmar ni que revertir (igual que validar_fecha
        # en crear_corte).
        assert servicio.llamadas == llamadas_previas

    def test_registra_y_confirma_la_transaccion_con_los_tres_archivos(self, servicio):
        corte = _crear_corte_registrado_con_archivos(
            servicio, vigencia=2026, fecha_corte=date(2026, 9, 8)
        )
        # El helper ya deja el corte en REGISTRADO; lo regreso a BORRADOR para
        # ejercitar registrar_corte de verdad, sin cambiar sus 3 archivos. Es
        # el mismo objeto que guarda el repositorio en memoria (ver
        # RepositorioCortesEnMemoria.guardar): mutar `corte` alcanza.
        corte.estado = EstadoCorte.BORRADOR
        commits_previos = servicio.llamadas["commit"]

        registrado = servicio.registrar_corte(corte.id)

        assert registrado.estado == EstadoCorte.REGISTRADO
        assert servicio._cortes.obtener(corte.id).estado == EstadoCorte.REGISTRADO
        assert servicio.llamadas["commit"] == commits_previos + 1

    def test_corte_inexistente_lanza_recurso_no_encontrado(self, servicio):
        with pytest.raises(RecursoNoEncontrado):
            servicio.registrar_corte(uuid.uuid4())

    def test_si_falla_la_confirmacion_revierte_la_transaccion(self, servicio):
        corte = _crear_corte_registrado_con_archivos(
            servicio, vigencia=2026, fecha_corte=date(2026, 9, 8)
        )
        corte.estado = EstadoCorte.BORRADOR

        def _commit_que_falla():
            raise RuntimeError("fallo simulado de la base de datos")

        servicio._commit = _commit_que_falla

        with pytest.raises(RuntimeError):
            servicio.registrar_corte(corte.id)

        assert servicio.llamadas["rollback"] == 1


class TestCorregirCorte:
    """D11 (docs/DECISIONES.md, aclaración 2026-09-19): PATCH /cortes/{id}."""

    def test_corte_inexistente_lanza_recurso_no_encontrado(self, servicio):
        with pytest.raises(RecursoNoEncontrado):
            servicio.corregir_corte(uuid.uuid4(), vigencia=2025, fecha_corte=date(2026, 9, 9))

    def test_rechaza_corregir_un_corte_registrado(self, servicio):
        corte = _crear_corte_registrado_con_archivos(
            servicio, vigencia=2026, fecha_corte=date(2026, 9, 8)
        )

        with pytest.raises(OperacionNoPermitida) as exc:
            servicio.corregir_corte(corte.id, vigencia=2025, fecha_corte=date(2026, 9, 9))

        assert exc.value.detalles["motivo"] == "corte_no_es_borrador"
        assert servicio._cortes.obtener(corte.id).vigencia == 2026

    def test_rechaza_si_vigencia_y_fecha_coinciden_con_otro_corte(self, servicio):
        # D9: el otro corte debe estar REGISTRADO (D11 no permite dos BORRADOR).
        otro = servicio.crear_corte(vigencia=2025, fecha_corte=date(2025, 12, 1))
        otro.estado = EstadoCorte.REGISTRADO
        servicio._cortes.confirmar_registro(otro)
        propio = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        with pytest.raises(OperacionNoPermitida) as exc:
            servicio.corregir_corte(propio.id, vigencia=2025, fecha_corte=date(2025, 12, 1))

        assert exc.value.detalles["motivo"] == "vigencia_fecha_duplicada"
        assert servicio._cortes.obtener(propio.id).vigencia == 2026

    def test_corregir_con_la_misma_vigencia_y_fecha_que_ya_tenia_no_se_autorechaza(self, servicio):
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        corregido = servicio.corregir_corte(corte.id, vigencia=2026, fecha_corte=date(2026, 9, 8))

        assert corregido.vigencia == 2026
        assert corregido.fecha_corte == date(2026, 9, 8)

    def test_corrige_y_confirma_la_transaccion(self, servicio):
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        commits_previos = servicio.llamadas["commit"]

        corregido = servicio.corregir_corte(corte.id, vigencia=2025, fecha_corte=date(2026, 9, 1))

        assert corregido.vigencia == 2025
        assert corregido.fecha_corte == date(2026, 9, 1)
        assert servicio._cortes.obtener(corte.id).vigencia == 2025
        assert servicio._cortes.obtener(corte.id).fecha_corte == date(2026, 9, 1)
        assert servicio.llamadas["commit"] == commits_previos + 1

    def test_si_falla_la_confirmacion_revierte_la_transaccion(self, servicio):
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        def _commit_que_falla():
            raise RuntimeError("fallo simulado de la base de datos")

        servicio._commit = _commit_que_falla

        with pytest.raises(RuntimeError):
            servicio.corregir_corte(corte.id, vigencia=2025, fecha_corte=date(2026, 9, 1))

        assert servicio.llamadas["rollback"] == 1


class _LectorFalso:
    """Doble de LectorArchivoFuente: aisla la orquestación de cargar_archivo
    de la lectura real de Excel. `tipo` fijo en PDT porque `_lectores` se
    indexa por TipoArchivoFuente, no por el atributo del lector.
    """

    def __init__(self, resultado: ResultadoLectura | None = None, error: Exception | None = None):
        self._resultado = resultado
        self._error = error
        self.llamadas: list[tuple[bytes, str, int]] = []

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        self.llamadas.append((contenido, nombre_archivo, vigencia))
        if self._error is not None:
            raise self._error
        assert self._resultado is not None
        return self._resultado


#: Contenido mínimo que pasa SEC-03 (firma ZIP + estructura de libro): se
#: reutiliza el .xlsx real de construir_pdt() en vez de fabricar bytes ad
#: hoc, para no mantener una segunda noción de "qué es un .xlsx válido".
_XLSX_VALIDO = construir_pdt()


class TestCargarArchivo:
    """[HU-02][BE-04]: orquestación de cargar_archivo (SEC-03 -> lector ->
    Load -> registro del archivo), con un lector doble para aislarla de la
    lectura real de Excel. La integración real con LectorPDT se cubre aparte
    (TestCargarArchivoIntegracionPDT).
    """

    def _servicio_con_lector(self, servicio: ServicioCortes, lector) -> ServicioCortes:
        servicio._lectores = {TipoArchivoFuente.PDT: lector}
        return servicio

    def test_corte_inexistente_lanza_recurso_no_encontrado(self, servicio):
        self._servicio_con_lector(servicio, _LectorFalso())

        with pytest.raises(RecursoNoEncontrado):
            servicio.cargar_archivo(uuid.uuid4(), TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan.xlsx")

    def test_tipo_sin_lector_registrado_lanza_value_error(self, servicio):
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        # Sin registrar ningún lector (servicio._lectores queda {} por defecto).

        with pytest.raises(ValueError):
            servicio.cargar_archivo(corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan.xlsx")

    def test_archivo_invalido_lo_rechaza_sec03_antes_de_tocar_el_lector(self, servicio):
        lector = _LectorFalso(resultado=ResultadoLectura(tipo=TipoArchivoIngesta.PDT))
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        commits_previos = servicio.llamadas["commit"]

        with pytest.raises(ArchivoInvalido):
            servicio.cargar_archivo(corte.id, TipoArchivoFuente.PDT, b"no es un xlsx", "plan.xlsx")

        # SEC-03 corta ANTES del lector: ninguna transacción se abrió ni se
        # llamó al lector (frontera ETL: Extract+Transform fuera de la
        # escritura, y aquí ni siquiera llegó a Extract).
        assert lector.llamadas == []
        assert servicio.llamadas["commit"] == commits_previos
        assert servicio.llamadas["rollback"] == 0

    def test_carga_exitosa_llama_al_lector_reemplaza_metas_y_registra_el_archivo(self, servicio):
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.PDT,
            filas={"metas": [{"cod_indicador_producto": "040110500", "principal": True}]},
            conteos={"metas": 1},
            advertencias=[],
        )
        lector = _LectorFalso(resultado=resultado)
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        commits_previos = servicio.llamadas["commit"]

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan_indicativo.xlsx"
        )

        # El lector recibe la vigencia del corte (alias_columna_programacion
        # de pdt.py la necesita para resolver la columna de ese año).
        assert lector.llamadas[0][2] == 2026
        assert servicio._datos.llamadas_reemplazar_metas == [(corte.id, resultado.filas["metas"])]
        assert archivo.tipo == TipoArchivoFuente.PDT
        assert archivo.filas_reconocidas == 1
        assert archivo.reutilizado is False
        assert servicio._cortes.obtener(corte.id).archivos[TipoArchivoFuente.PDT] == archivo
        assert servicio.llamadas["commit"] == commits_previos + 1
        assert servicio.llamadas["rollback"] == 0

    def test_descartes_del_resultado_se_propagan_al_archivo(self, servicio):
        """D14: cargar_archivo propaga resultado.descartes al ArchivoFuente
        que registra -- hoy solo LectorProyectos los produce, pero el
        cableado no depende de esa implementacion, solo de que
        ResultadoLectura.descartes venga lleno."""
        descarte = DescarteIndicador(
            valor_crudo="2026",
            motivo="longitud invalida",
            categoria=CategoriaDescarte.LONGITUD_CORTA,
        )
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.PDT,
            filas={"metas": []},
            conteos={"metas": 0},
            descartes=[descarte],
        )
        lector = _LectorFalso(resultado=resultado)
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan.xlsx"
        )

        assert archivo.descartes == [descarte]

    def test_conteos_del_resultado_se_propagan_al_archivo(self, servicio):
        """[HU-03][FE-01]: cargar_archivo propaga resultado.conteos al
        ArchivoFuente que registra -- el dato ya existe completo en
        LectorEjecucion (filas por pestaña), solo faltaba conectarlo."""
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.EJECUCION,
            filas={"rubros": [], "contratos": [], "registros": []},
            conteos={
                "ejecucion": 374,
                "contratacion": 270,
                "rubros": 0,
                "contratos": 0,
                "registros": 0,
            },
        )
        lector = _LectorFalso(resultado=resultado)
        servicio._lectores = {TipoArchivoFuente.EJECUCION: lector}
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.EJECUCION, _XLSX_VALIDO, "presupuestal.xlsx"
        )

        assert archivo.conteos == {
            "ejecucion": 374,
            "contratacion": 270,
            "rubros": 0,
            "contratos": 0,
            "registros": 0,
        }

    def test_codigos_del_resultado_se_propagan_al_archivo(self, servicio):
        """[HU-04][FE-03]: mismo cableado que descartes (D14), ahora para la
        otra mitad de la tarjeta -- los codigos SI reconocidos. Deduplicar
        por orden de aparicion es responsabilidad del lector (ver
        test_lectores_proyectos.py); aqui solo se verifica que lo que venga
        en resultado.codigos llegue intacto a ArchivoFuente.codigos."""
        codigo = CodigoIndicadorProducto("170202300")
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.PDT,
            filas={"metas": []},
            conteos={"metas": 0},
            codigos=[codigo],
        )
        lector = _LectorFalso(resultado=resultado)
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan.xlsx"
        )

        assert archivo.codigos == [codigo]

    def test_nombre_de_archivo_saneado_es_el_que_se_registra(self, servicio):
        """SEC-03 (sanitizar_nombre) descarta rutas: un intento de path
        traversal en el nombre no debe llegar tal cual al registro."""
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.PDT, filas={"metas": []}, conteos={"metas": 0}
        )
        lector = _LectorFalso(resultado=resultado)
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "../../etc/plan.xlsx"
        )

        assert archivo.nombre_archivo == "plan.xlsx"
        assert lector.llamadas[0][1] == "plan.xlsx"

    def test_si_el_lector_rechaza_el_archivo_no_se_abre_transaccion(self, servicio):
        lector = _LectorFalso(error=ArchivoInvalido("no corresponde al formato esperado"))
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        commits_previos = servicio.llamadas["commit"]

        with pytest.raises(ArchivoInvalido):
            servicio.cargar_archivo(corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "ejecucion.xlsx")

        assert servicio.llamadas["commit"] == commits_previos
        assert servicio.llamadas["rollback"] == 0
        assert servicio._cortes.obtener(corte.id).archivos == {}

    def test_si_falla_el_load_se_revierte_la_transaccion_sin_registrar_el_archivo(self, servicio):
        resultado = ResultadoLectura(
            tipo=TipoArchivoIngesta.PDT,
            filas={"metas": [{"cod_indicador_producto": "040110500", "principal": True}]},
            conteos={"metas": 1},
        )
        lector = _LectorFalso(resultado=resultado)
        self._servicio_con_lector(servicio, lector)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        def _reemplazar_metas_que_falla(corte_id, metas):
            raise RuntimeError("fallo simulado de la base de datos")

        servicio._datos.reemplazar_metas = _reemplazar_metas_que_falla

        with pytest.raises(RuntimeError):
            servicio.cargar_archivo(corte.id, TipoArchivoFuente.PDT, _XLSX_VALIDO, "plan.xlsx")

        assert servicio.llamadas["rollback"] == 1
        assert servicio._cortes.obtener(corte.id).archivos == {}

    def test_tipo_ejecucion_despacha_a_reemplazar_presupuesto(self, servicio):
        """[HU-03][BE-06]: cargar_archivo despacha las tres listas nuevas de
        ResultadoLectura.filas ("rubros"/"contratos"/"registros") a
        reemplazar_presupuesto, y usa su retorno como filas_reconocidas —
        mismo patrón que el despacho de PDT a reemplazar_metas."""
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        rubros = [{"codigo_rubro_nivel": "1.2.3", "ultimo_nivel": True}]
        contratos = [{"numero_contrato": "C-001"}]
        registros = [{"numero_contrato": "C-001", "codigo_rubro_crudo": "1.2.3"}]
        lector = _LectorFalso(
            resultado=ResultadoLectura(
                tipo=TipoArchivoIngesta.EJECUCION,
                filas={
                    "ejecucion": [],
                    "contratacion": [],
                    "rubros": rubros,
                    "contratos": contratos,
                    "registros": registros,
                },
            )
        )
        servicio._lectores = {TipoArchivoFuente.EJECUCION: lector}

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.EJECUCION, _XLSX_VALIDO, "presupuestal.xlsx"
        )

        assert servicio._datos.llamadas_reemplazar_presupuesto == [
            (corte.id, rubros, contratos, registros)
        ]
        assert archivo.filas_reconocidas == 3  # len(rubros)+len(contratos)+len(registros)

    def test_tipo_proyectos_despacha_a_reemplazar_proyectos(self, servicio):
        """[HU-04][BE-04]: cargar_archivo despacha resultado.filas["proyectos"]
        a reemplazar_proyectos, mismo patrón que PDT/EJECUCION."""
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        proyectos = [{"bpin": "202500000050132", "codigos_indicador": ["170202300"]}]
        lector = _LectorFalso(
            resultado=ResultadoLectura(
                tipo=TipoArchivoIngesta.PROYECTOS, filas={"proyectos": proyectos}
            )
        )
        servicio._lectores = {TipoArchivoFuente.PROYECTOS: lector}

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PROYECTOS, _XLSX_VALIDO, "proyectos.xlsx"
        )

        assert servicio._datos.llamadas_reemplazar_proyectos == [(corte.id, proyectos)]
        assert archivo.filas_reconocidas == 1


class TestCargarArchivoIntegracionPDT:
    """Integración real (sin dobles) del lector PDT a través de
    cargar_archivo: prueba de punta a punta que la orquestación de
    [HU-02][BE-04] funciona con LectorPDT real, no solo con el doble."""

    def _servicio_con_pdt_real(self, servicio: ServicioCortes) -> ServicioCortes:
        servicio._lectores = {TipoArchivoFuente.PDT: LectorPDT()}
        return servicio

    def test_carga_el_pdt_real_y_reconoce_las_dos_metas(self, servicio):
        self._servicio_con_pdt_real(servicio)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        archivo = servicio.cargar_archivo(
            corte.id, TipoArchivoFuente.PDT, construir_pdt(), "plan_indicativo.xlsx"
        )

        assert archivo.filas_reconocidas == 2
        metas_cargadas = servicio._datos.llamadas_reemplazar_metas[-1][1]
        assert {m["cod_indicador_producto"] for m in metas_cargadas} == {"040110500", "170202300"}

    def test_rechaza_total_si_falta_la_columna_principal_hu02_ca3(self, servicio):
        self._servicio_con_pdt_real(servicio)
        corte = servicio.crear_corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        with pytest.raises(ArchivoInvalido) as exc:
            servicio.cargar_archivo(
                corte.id,
                TipoArchivoFuente.PDT,
                construir_pdt(incluir_principal=False),
                "plan_indicativo.xlsx",
            )

        assert exc.value.detalles["motivo"] == "columnas_faltantes"
        # HU-02/CA-3: rechazo TOTAL, no quedan datos parciales.
        assert servicio._cortes.obtener(corte.id).archivos == {}
        assert servicio._datos.llamadas_reemplazar_metas == []
