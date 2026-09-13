"""Pruebas de dominio para Corte y sus invariantes.

TARJETA: [HU-01][BE-01]
CUBRE: HU-01 / CA-2, CA-4

Pruebas de dominio puro: sin base de datos, sin fixtures de infraestructura.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.cortes.domain.entidades import Corte, TipoArchivoFuente
from app.shared.errors import ReglaDeNegocioViolada


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
