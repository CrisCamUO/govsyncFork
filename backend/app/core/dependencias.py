"""Dependencias FastAPI compartidas (composition root).

CAPA: API
TARJETAS: [HU-01][FE-01], [HU-02][FE-01], [HU-03][FE-01], [HU-04][FE-01]

Aquí se arma el grafo de objetos: cada caso de uso recibe sus repositorios ya
construidos y NO conoce SQLAlchemy.

-----------------------------------------------------------------------------
SOBRE AUTENTICACIÓN
-----------------------------------------------------------------------------
La tarjeta [REF-05] registra la decisión del equipo de diferir E-01
(autenticación y autorización) al Sprint 2, aceptando que las filas
Autenticación y Autorización de la Tabla 4 de la rúbrica queden en N/A, con la
mitigación de no exponer públicamente los endpoints de carga.

Este esqueleto RESPETA esa decisión: no hay dependencia de autorización.

Si el equipo revoca [REF-05], el cambio es acotado y entra aquí: una función
`exigir_roles(*roles)` que devuelva una dependencia, más un módulo
`modules/identidad/`. Los routers solo tendrían que añadir el parámetro.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.cortes.application.casos_uso import ServicioCortes
from app.modules.cortes.domain.entidades import TipoArchivoFuente
from app.modules.cortes.persistence.repositorios import (
    RepositorioCortesSQL,
    RepositorioDatosCorteSQL,
)
from app.modules.ingesta.persistence.lectores.ejecucion import LectorEjecucion
from app.modules.ingesta.persistence.lectores.pdt import LectorPDT
from app.modules.ingesta.persistence.lectores.proyectos import LectorProyectos

SesionDep = Annotated[Session, Depends(get_session)]

#: [HU-02][BE-04]/[HU-03][BE-06]/[HU-04][BE-04]: registro de lectores
#: disponibles (Strategy). Las tres fuentes (PDT, EJECUCION, PROYECTOS)
#: tienen lector + carga (`reemplazar_*`) funcionales — ver el docstring de
#: `_cargar_resultado` (casos_uso.py) para el despacho por tipo.
_LECTORES_DISPONIBLES = {
    TipoArchivoFuente.PDT: LectorPDT(),
    TipoArchivoFuente.EJECUCION: LectorEjecucion(),
    TipoArchivoFuente.PROYECTOS: LectorProyectos(),
}


def obtener_servicio_cortes(sesion: SesionDep) -> ServicioCortes:
    """[HU-01][FE-01] Composition root de ServicioCortes para los routers.

    OJO [BD-02]: RepositorioCortesSQL y RepositorioDatosCorteSQL siguen
    siendo clases abstractas incompletas en develop (solo TODO, sin
    metodos implementados) — instanciarlas aqui lanza TypeError. Contra
    Postgres real, los endpoints que dependen de esto responderan 500 hasta
    que [BD-02] se fusione (existe en origin/base/modelos). Las pruebas de
    la API no pasan por aqui: sobreescriben ServicioCortesDep con
    repositorios en memoria (ver tests/test_router_cortes.py).
    """
    return ServicioCortes(
        repo_cortes=RepositorioCortesSQL(sesion),
        repo_datos=RepositorioDatosCorteSQL(sesion),
        confirmar_transaccion=sesion.commit,
        revertir_transaccion=sesion.rollback,
        lectores=_LECTORES_DISPONIBLES,
    )


ServicioCortesDep = Annotated[ServicioCortes, Depends(obtener_servicio_cortes)]
