"""Implementaciones concretas de los lectores (pandas / openpyxl).

Fábrica de estrategias: único punto que conoce el mapa tipo -> lector.
Agregar una fuente nueva = una clase nueva + una entrada aquí (Open/Closed).
"""

from app.modules.ingesta.domain.contratos import LectorArchivoFuente, TipoArchivo

# TODO Descomentar cada línea a medida que su lector exista.
from app.modules.ingesta.persistence.lectores.pdt import LectorPDT  # [HU-02][BE-03]

# from app.modules.ingesta.persistence.lectores.ejecucion import LectorEjecucion  # [HU-03][BE-01]
# from app.modules.ingesta.persistence.lectores.proyectos import LectorProyectos  # [HU-04][BE-01]

_REGISTRO: dict[TipoArchivo, type[LectorArchivoFuente]] = {
    TipoArchivo.PDT: LectorPDT,
    # TipoArchivo.EJECUCION: LectorEjecucion,
    # TipoArchivo.PROYECTOS: LectorProyectos,
}


def obtener_lector(tipo: TipoArchivo) -> LectorArchivoFuente:
    if tipo not in _REGISTRO:
        raise NotImplementedError(f"Todavía no hay lector para {tipo.value}")
    return _REGISTRO[tipo]()
