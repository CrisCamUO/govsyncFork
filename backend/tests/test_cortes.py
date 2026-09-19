"""Pruebas de dominio para Corte y sus invariantes.

TARJETA: [HU-01][BE-01]
CUBRE: HU-01 / CA-2, CA-4

Pruebas de dominio puro: sin base de datos, sin fixtures de infraestructura.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, EstadoCorte, TipoArchivoFuente
from app.shared.errors import OperacionNoPermitida, ReglaDeNegocioViolada


def test_rechaza_fecha_futura_con_motivo():
    hoy = date(2026, 9, 8)
    fecha_futura = date(2026, 9, 9)

    with pytest.raises(ReglaDeNegocioViolada) as exc_info:
        Corte.validar_fecha(fecha_futura, hoy)

    assert exc_info.value.detalles["fecha_corte"] == fecha_futura.isoformat()
    assert exc_info.value.detalles["hoy"] == hoy.isoformat()


def test_acepta_fecha_hoy_o_pasada():
    hoy = date(2026, 9, 8)
    Corte.validar_fecha(hoy, hoy)
    Corte.validar_fecha(date(2026, 9, 1), hoy)


def test_archivos_faltantes_en_corte_nuevo_devuelve_los_tres():
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    faltantes = corte.archivos_faltantes()

    assert set(faltantes) == {
        TipoArchivoFuente.PDT,
        TipoArchivoFuente.EJECUCION,
        TipoArchivoFuente.PROYECTOS,
    }
    assert corte.esta_completo() is False


def test_puede_reutilizar_acepta_pdt_y_proyectos():
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    assert corte.puede_reutilizar(TipoArchivoFuente.PDT) is True
    assert corte.puede_reutilizar(TipoArchivoFuente.PROYECTOS) is True


def test_puede_reutilizar_rechaza_ejecucion():
    """HU-01/CA-7: el archivo de ejecucion se solicita siempre, nunca se reutiliza."""
    corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

    assert corte.puede_reutilizar(TipoArchivoFuente.EJECUCION) is False


def _archivo(tipo: TipoArchivoFuente) -> ArchivoFuente:
    return ArchivoFuente(tipo=tipo, nombre_archivo=f"{tipo.value.lower()}.xlsx")


class TestRegistrar:
    def test_rechaza_corte_nuevo_nombrando_los_tres_faltantes(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))

        with pytest.raises(OperacionNoPermitida) as exc_info:
            corte.registrar()

        assert set(exc_info.value.detalles["archivos_faltantes"]) == {
            TipoArchivoFuente.PDT.value,
            TipoArchivoFuente.EJECUCION.value,
            TipoArchivoFuente.PROYECTOS.value,
        }
        assert corte.estado == EstadoCorte.BORRADOR

    def test_rechaza_nombrando_solo_el_que_falta(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        corte.archivos[TipoArchivoFuente.PDT] = _archivo(TipoArchivoFuente.PDT)
        corte.archivos[TipoArchivoFuente.PROYECTOS] = _archivo(TipoArchivoFuente.PROYECTOS)

        with pytest.raises(OperacionNoPermitida) as exc_info:
            corte.registrar()

        assert exc_info.value.detalles["archivos_faltantes"] == [TipoArchivoFuente.EJECUCION.value]
        assert corte.estado == EstadoCorte.BORRADOR

    def test_registra_cuando_estan_los_tres_archivos(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        for tipo in TipoArchivoFuente:
            corte.archivos[tipo] = _archivo(tipo)

        corte.registrar()

        assert corte.estado == EstadoCorte.REGISTRADO

    def test_registra_igual_si_alguna_fuente_fue_reutilizada(self):
        """CA-3/CA-5: no importa si el archivo es nuevo o reutilizado, solo que esté."""
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        for tipo in TipoArchivoFuente:
            corte.archivos[tipo] = ArchivoFuente(
                tipo=tipo,
                nombre_archivo="x.xlsx",
                reutilizado=(tipo != TipoArchivoFuente.EJECUCION),
            )

        corte.registrar()

        assert corte.estado == EstadoCorte.REGISTRADO

    def test_registrar_un_corte_ya_registrado_es_idempotente(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8), estado=EstadoCorte.REGISTRADO)
        for tipo in TipoArchivoFuente:
            corte.archivos[tipo] = _archivo(tipo)

        corte.registrar()

        assert corte.estado == EstadoCorte.REGISTRADO


class TestCorregir:
    """D11 (docs/DECISIONES.md, aclaración 2026-09-19): corrección de
    vigencia/fecha de un corte en BORRADOR."""

    def test_corrige_vigencia_y_fecha_de_un_corte_en_borrador(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        hoy = date(2026, 9, 10)

        corte.corregir(vigencia=2025, fecha_corte=date(2026, 9, 9), hoy=hoy)

        assert corte.vigencia == 2025
        assert corte.fecha_corte == date(2026, 9, 9)
        assert corte.estado == EstadoCorte.BORRADOR

    def test_rechaza_corregir_un_corte_registrado(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8), estado=EstadoCorte.REGISTRADO)
        hoy = date(2026, 9, 10)

        with pytest.raises(OperacionNoPermitida) as exc_info:
            corte.corregir(vigencia=2025, fecha_corte=date(2026, 9, 9), hoy=hoy)

        assert exc_info.value.detalles["motivo"] == "corte_no_es_borrador"
        assert exc_info.value.detalles["estado_actual"] == EstadoCorte.REGISTRADO.value
        # No cambia nada si se rechaza:
        assert corte.vigencia == 2026
        assert corte.fecha_corte == date(2026, 9, 8)

    def test_rechaza_corregir_con_fecha_futura(self):
        corte = Corte(vigencia=2026, fecha_corte=date(2026, 9, 8))
        hoy = date(2026, 9, 10)

        with pytest.raises(ReglaDeNegocioViolada) as exc_info:
            corte.corregir(vigencia=2026, fecha_corte=date(2026, 9, 11), hoy=hoy)

        assert exc_info.value.detalles["fecha_corte"] == date(2026, 9, 11).isoformat()
        # No cambia nada si se rechaza:
        assert corte.fecha_corte == date(2026, 9, 8)
