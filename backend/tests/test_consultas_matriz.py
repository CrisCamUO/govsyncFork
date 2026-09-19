"""Pruebas de construir_matriz (el cruce de las 4 fuentes de HU-07).

TARJETAS: [HU-07][BE-01] (Juan Esteban, CA-2..CA-6)
          [HU-07][BE-02] (Cristhian, CA-7 -- no colapsar relaciones multiples;
          implementado en la misma consulta por acuerdo del equipo, ver
          docstring de consultas.py)
          [HU-07][BE-03] (Juan Esteban, CA-8 -- NULL explicito)
CUBRE: HU-07 / CA-2 a CA-8.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.modules.cortes.domain.entidades import EstadoCorte
from app.modules.cortes.persistence.models import (
    ContratoORM,
    CorteORM,
    MetaORM,
    ProyectoIndicadorORM,
    ProyectoORM,
    RegistroPresupuestalORM,
    RubroORM,
)
from app.modules.trazabilidad.persistence.consultas import construir_matriz

COD_1 = "170202300"
COD_2 = "330105300"
COD_3 = "040110500"


def _crear_corte(
    sesion,
    *,
    vigencia: int = 2026,
    fecha: date = date(2026, 1, 1),
    estado: EstadoCorte = EstadoCorte.BORRADOR,
) -> uuid.UUID:
    corte_id = uuid.uuid4()
    sesion.add(CorteORM(id=corte_id, vigencia=vigencia, fecha_corte=fecha, estado=estado))
    sesion.flush()
    return corte_id


def _crear_meta(sesion, corte_id: uuid.UUID, cod: str, *, nombre: str | None = None) -> None:
    sesion.add(
        MetaORM(
            id=uuid.uuid4(),
            corte_id=corte_id,
            cod_indicador_producto=cod,
            nombre_producto=nombre,
            es_principal=True,
        )
    )


def _crear_proyecto_con_indicador(sesion, corte_id: uuid.UUID, bpin: str, cod: str) -> None:
    proyecto_id = uuid.uuid4()
    sesion.add(ProyectoORM(id=proyecto_id, corte_id=corte_id, bpin=bpin))
    sesion.add(
        ProyectoIndicadorORM(id=uuid.uuid4(), proyecto_id=proyecto_id, cod_indicador_producto=cod)
    )


def _crear_rubro(sesion, corte_id: uuid.UUID, cod: str, *, ultimo_nivel: bool = True) -> uuid.UUID:
    rubro_id = uuid.uuid4()
    sesion.add(
        RubroORM(
            id=rubro_id,
            corte_id=corte_id,
            codigo_rubro_nivel=f"nivel-{cod}",
            cod_indicador_producto=cod,
            ultimo_nivel=ultimo_nivel,
        )
    )
    return rubro_id


def _crear_contrato(
    sesion, corte_id: uuid.UUID, numero: str, objeto: str | None = None
) -> uuid.UUID:
    contrato_id = uuid.uuid4()
    sesion.add(
        ContratoORM(id=contrato_id, corte_id=corte_id, numero_contrato=numero, objeto=objeto)
    )
    return contrato_id


def _crear_registro(sesion, rubro_id: uuid.UUID | None, contrato_id: uuid.UUID) -> None:
    sesion.add(RegistroPresupuestalORM(id=uuid.uuid4(), rubro_id=rubro_id, contrato_id=contrato_id))


class TestCasoFeliz:
    def test_meta_con_proyecto_rubro_y_contrato_completos(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1, nombre="Vias terciarias mantenidas")
        _crear_proyecto_con_indicador(sesion, corte_id, "202500000050132", COD_1)
        rubro_id = _crear_rubro(sesion, corte_id, COD_1)
        contrato_id = _crear_contrato(sesion, corte_id, "C-001", "Mantenimiento de vias")
        _crear_registro(sesion, rubro_id, contrato_id)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.total == 1
        fila = resultado.filas[0]
        assert fila.cod_indicador_producto == COD_1
        assert fila.nombre_producto == "Vias terciarias mantenidas"
        assert fila.cod_bpin == "202500000050132"
        assert fila.cod_indicador_ejecucion == COD_1
        assert fila.numero_contrato == "C-001"
        assert fila.descripcion_contrato == "Mantenimiento de vias"


class TestCA8SinAsociacionFicticia:
    def test_meta_sin_ninguna_correspondencia_sigue_apareciendo_con_null_explicito(
        self, sesion
    ) -> None:
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.total == 1
        fila = resultado.filas[0]
        assert fila.cod_bpin is None
        assert fila.cod_indicador_ejecucion is None
        assert fila.numero_contrato is None
        assert fila.descripcion_contrato is None

    def test_meta_con_bpin_pero_sin_ejecucion_ni_contrato(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1)
        _crear_proyecto_con_indicador(sesion, corte_id, "202500000050132", COD_1)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        fila = resultado.filas[0]
        assert fila.cod_bpin == "202500000050132"
        assert fila.cod_indicador_ejecucion is None
        assert fila.numero_contrato is None


class TestCA7NoColapsaRelacionesMultiples:
    def test_un_indicador_con_dos_bpin_aparecen_ambos(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1)
        _crear_proyecto_con_indicador(sesion, corte_id, "AAA", COD_1)
        _crear_proyecto_con_indicador(sesion, corte_id, "BBB", COD_1)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.total == 2
        assert {f.cod_bpin for f in resultado.filas} == {"AAA", "BBB"}

    def test_un_bpin_con_tres_indicadores_aparecen_los_tres(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        proyecto_id = uuid.uuid4()
        sesion.add(ProyectoORM(id=proyecto_id, corte_id=corte_id, bpin="COMPARTIDO"))
        for cod in (COD_1, COD_2, COD_3):
            _crear_meta(sesion, corte_id, cod)
            sesion.add(
                ProyectoIndicadorORM(
                    id=uuid.uuid4(), proyecto_id=proyecto_id, cod_indicador_producto=cod
                )
            )
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.total == 3
        assert {f.cod_indicador_producto for f in resultado.filas} == {COD_1, COD_2, COD_3}
        assert all(f.cod_bpin == "COMPARTIDO" for f in resultado.filas)

    def test_un_contrato_con_varios_registros_presupuestales_no_produce_fan_out(
        self, sesion
    ) -> None:
        """Caso frontera documentado en consultas.py: un contrato con 1..N
        registros contra el MISMO rubro no debe duplicar la fila -- ninguna
        columna de la matriz sale de registro_presupuestal, es solo un
        puente. Deduplicar el puente evita el fan-out sin usar DISTINCT
        sobre el resultado (prohibido por la tarjeta)."""
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1)
        rubro_id = _crear_rubro(sesion, corte_id, COD_1)
        contrato_id = _crear_contrato(sesion, corte_id, "C-001")
        _crear_registro(sesion, rubro_id, contrato_id)
        _crear_registro(sesion, rubro_id, contrato_id)
        _crear_registro(sesion, rubro_id, contrato_id)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.total == 1


class TestFiltraSubtotales:
    def test_rubro_con_ultimo_nivel_falso_no_alimenta_la_matriz(self, sesion) -> None:
        """Regla 1 (consultas.py): un subtotal jerarquico ya incluye el valor
        de sus hojas -- incluirlo tambien en el cruce infla la matriz."""
        corte_id = _crear_corte(sesion)
        _crear_meta(sesion, corte_id, COD_1)
        _crear_rubro(sesion, corte_id, COD_1, ultimo_nivel=False)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id)

        assert resultado.filas[0].cod_indicador_ejecucion is None


class TestAislamientoEntreCortes:
    def test_proyecto_de_otro_corte_no_se_cuela(self, sesion) -> None:
        """CUIDADO CON EL CRUCE ENTRE CORTES (consultas.py): proyecto_indicador
        no tiene corte_id propio -- sin acotar por el proyecto padre, un
        indicador de OTRO corte con el mismo codigo produciria una fila
        fantasma."""
        corte_1 = _crear_corte(
            sesion, vigencia=2025, fecha=date(2025, 12, 1), estado=EstadoCorte.REGISTRADO
        )
        corte_2 = _crear_corte(sesion, vigencia=2026, fecha=date(2026, 1, 1))
        _crear_proyecto_con_indicador(sesion, corte_1, "DEL-OTRO-CORTE", COD_1)
        _crear_meta(sesion, corte_2, COD_1)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_2)

        assert resultado.total == 1
        assert resultado.filas[0].cod_bpin is None

    def test_rubro_de_otro_corte_no_se_cuela(self, sesion) -> None:
        corte_1 = _crear_corte(
            sesion, vigencia=2025, fecha=date(2025, 12, 1), estado=EstadoCorte.REGISTRADO
        )
        corte_2 = _crear_corte(sesion, vigencia=2026, fecha=date(2026, 1, 1))
        _crear_rubro(sesion, corte_1, COD_1)
        _crear_meta(sesion, corte_2, COD_1)
        sesion.flush()

        resultado = construir_matriz(sesion, corte_2)

        assert resultado.filas[0].cod_indicador_ejecucion is None


class TestPaginacion:
    def test_total_cuenta_todas_las_filas_sin_paginar(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        for i in range(5):
            _crear_meta(sesion, corte_id, f"{i:09d}")
        sesion.flush()

        resultado = construir_matriz(sesion, corte_id, pagina=1, tamano_pagina=2)

        assert resultado.total == 5
        assert len(resultado.filas) == 2

    def test_segunda_pagina_trae_las_filas_siguientes(self, sesion) -> None:
        corte_id = _crear_corte(sesion)
        for i in range(5):
            _crear_meta(sesion, corte_id, f"{i:09d}")
        sesion.flush()

        pagina_1 = construir_matriz(sesion, corte_id, pagina=1, tamano_pagina=2)
        pagina_2 = construir_matriz(sesion, corte_id, pagina=2, tamano_pagina=2)

        codigos_1 = {f.cod_indicador_producto for f in pagina_1.filas}
        codigos_2 = {f.cod_indicador_producto for f in pagina_2.filas}
        assert codigos_1.isdisjoint(codigos_2)
