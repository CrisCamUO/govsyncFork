"""Pruebas del endpoint de la matriz de relación (capa API).

TARJETA: [HU-07][FE-01]
CUBRE: HU-07 / CA-1

A diferencia de `test_router_cortes.py`, aquí no hay dobles en memoria:
`construir_matriz` hace SQL directo contra el ORM, así que se reutilizan
`motor`/`sesion`/`cliente` de `conftest.py` (SQLite en memoria, esquema
real) — el mismo mecanismo que ya usa `test_consultas_matriz.py` para
probar `construir_matriz` en aislamiento. Aquí se prueba el endpoint
completo: 404/409 del router + el cruce real vía `RepositorioCortesSQL`
(ya completo en develop, sin dobles).
"""

from __future__ import annotations

import uuid
from datetime import date

from app.modules.cortes.domain.entidades import EstadoCorte, TipoArchivoFuente
from app.modules.cortes.persistence.models import ArchivoFuenteORM, CorteORM, MetaORM


def _crear_corte(sesion, *, vigencia: int = 2026, fecha: date = date(2026, 1, 1)) -> uuid.UUID:
    corte_id = uuid.uuid4()
    sesion.add(
        CorteORM(id=corte_id, vigencia=vigencia, fecha_corte=fecha, estado=EstadoCorte.BORRADOR)
    )
    sesion.flush()
    return corte_id


def _marcar_archivo_cargado(sesion, corte_id: uuid.UUID, tipo: TipoArchivoFuente) -> None:
    sesion.add(
        ArchivoFuenteORM(
            id=uuid.uuid4(),
            corte_id=corte_id,
            tipo=tipo,
            nombre_archivo=f"{tipo.value.lower()}.xlsx",
        )
    )


def test_matriz_devuelve_404_si_el_corte_no_existe(cliente):
    respuesta = cliente.get(f"/api/v1/matriz-relacion/{uuid.uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "recurso_no_encontrado"


def test_matriz_devuelve_409_si_falta_una_fuente(cliente, sesion):
    corte_id = _crear_corte(sesion)
    _marcar_archivo_cargado(sesion, corte_id, TipoArchivoFuente.PDT)
    _marcar_archivo_cargado(sesion, corte_id, TipoArchivoFuente.EJECUCION)
    # PROYECTOS falta a propósito.
    sesion.commit()

    respuesta = cliente.get(f"/api/v1/matriz-relacion/{corte_id}")

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "operacion_no_permitida"
    assert cuerpo["detalles"]["archivos_faltantes"] == ["PROYECTOS"]


def test_matriz_devuelve_409_si_faltan_las_tres_fuentes(cliente, sesion):
    corte_id = _crear_corte(sesion)
    sesion.commit()

    respuesta = cliente.get(f"/api/v1/matriz-relacion/{corte_id}")

    assert respuesta.status_code == 409
    faltantes = respuesta.json()["detalles"]["archivos_faltantes"]
    assert set(faltantes) == {"PDT", "EJECUCION", "PROYECTOS"}


def test_matriz_devuelve_200_con_datos_reales_cuando_estan_las_tres_fuentes(cliente, sesion):
    corte_id = _crear_corte(sesion)
    for tipo in TipoArchivoFuente:
        _marcar_archivo_cargado(sesion, corte_id, tipo)
    sesion.add(
        MetaORM(
            id=uuid.uuid4(),
            corte_id=corte_id,
            cod_indicador_producto="040110500",
            nombre_producto="Vías pavimentadas",
            es_principal=True,
        )
    )
    sesion.commit()

    respuesta = cliente.get(f"/api/v1/matriz-relacion/{corte_id}?pagina=1&tamano_pagina=50")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["corte_id"] == str(corte_id)
    assert cuerpo["pagina"] == 1
    assert cuerpo["tamano_pagina"] == 50
    assert cuerpo["total_filas"] == 1
    assert len(cuerpo["filas"]) == 1
    fila = cuerpo["filas"][0]
    assert fila["cod_indicador_producto"] == "040110500"
    assert fila["nombre_producto"] == "Vías pavimentadas"
    # Sin proyecto/rubro/contrato cargados para este código: NULL explícito
    # (CA-8), no "" ni 0 — mismo criterio que consultas.py.
    assert fila["cod_bpin"] is None
    assert fila["cod_indicador_ejecucion"] is None
    assert fila["numero_contrato"] is None


def test_matriz_pagina_vacia_devuelve_200_con_filas_vacias(cliente, sesion):
    """Con las 3 fuentes cargadas pero sin ninguna meta: 200, no 404 ni 409
    — el corte está completo, simplemente no cruza nada todavía."""
    corte_id = _crear_corte(sesion)
    for tipo in TipoArchivoFuente:
        _marcar_archivo_cargado(sesion, corte_id, tipo)
    sesion.commit()

    respuesta = cliente.get(f"/api/v1/matriz-relacion/{corte_id}")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_filas"] == 0
    assert cuerpo["filas"] == []
