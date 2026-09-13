"""Endpoints de cortes y carga de archivos fuente.

CAPA: API
TARJETAS: [HU-01][FE-01] Endpoints de corte
          [HU-02][FE-01] Endpoint de carga del Plan Indicativo
          [HU-03][FE-01] Endpoint de carga del archivo presupuestal
          [HU-04][FE-01] Endpoint de carga de la plantilla BPIN

Solo HTTP: validación superficial, conversión a DTO y códigos de estado.
NINGUNA regla de negocio ni consulta vive aquí.

Los DTO son modelos Pydantic, NUNCA entidades ORM: si se expusiera el ORM,
agregar una columna cambiaría el contrato de la API en silencio.

Al terminar, registrar el router en app/main.py.

=============================================================================
ALCANCE DE [HU-01][FE-01] EN ESTA ITERACIÓN
=============================================================================
Cubre POST /cortes, GET /cortes y GET /cortes/{id}. NO cubre:

- POST /cortes/{id}/registrar: `Corte.registrar()` y
  `ServicioCortes.registrar_corte()` existen con firma definida pero lanzan
  NotImplementedError — es [HU-01][BE-05] (Juan Esteban). Se agrega en un
  commit posterior cuando esa tarjeta cierre.
- POST /cortes/{id}/archivos/{tipo}: depende de `cargar_archivo()`, también
  NotImplementedError — es [HU-02..04][BE-04]/[BE-06].
- 409 por "vigencia+fecha duplicada": GAP. No existe hoy, en casos_uso.py
  ni en el puerto RepositorioCortes, ninguna consulta que la soporte —
  es lógica de aplicación, no de esta capa. Se propone como tarjeta nueva.

El DTO de salida (`CorteRespuesta`) NO expone `archivos_faltantes`: el
array `archivos` solo lista lo ya cargado/reutilizado, tal como está
especificado en docs/ESPECIFICACIONES_TECNICAS.md. Es derivable en el
cliente contra el conjunto fijo {PDT, EJECUCION, PROYECTOS}; el consumidor
real de "qué falta" es el 422 de [HU-01][BE-05] al registrar, no la
respuesta exitosa de GET/POST /cortes.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.dependencias import ServicioCortesDep
from app.modules.cortes.domain.entidades import Corte

router = APIRouter(prefix="/cortes", tags=["Cortes de seguimiento"])


# --- DTOs (Pydantic, nunca la entidad de dominio/ORM) -----------------------


class CorteEntrada(BaseModel):
    vigencia: int
    fecha_corte: date


class ArchivoFuenteRespuesta(BaseModel):
    tipo: str
    reutilizado: bool
    corte_origen_id: UUID | None


class CorteRespuesta(BaseModel):
    id: UUID
    vigencia: int
    fecha_corte: date
    estado: str
    archivos: list[ArchivoFuenteRespuesta]


def _a_dto(corte: Corte) -> CorteRespuesta:
    """Conversión explícita dominio -> DTO. Nunca se expone `Corte` directo."""
    return CorteRespuesta(
        id=corte.id,
        vigencia=corte.vigencia,
        fecha_corte=corte.fecha_corte,
        estado=corte.estado.value,
        archivos=[
            ArchivoFuenteRespuesta(
                tipo=archivo.tipo.value,
                reutilizado=archivo.reutilizado,
                corte_origen_id=archivo.corte_origen_id,
            )
            for archivo in corte.archivos.values()
        ],
    )


# --- Endpoints ---------------------------------------------------------------


@router.post("", response_model=CorteRespuesta, status_code=status.HTTP_201_CREATED)
def crear_corte(entrada: CorteEntrada, servicio: ServicioCortesDep) -> CorteRespuesta:
    """HU-01 / CA-1, CA-2.

    El 422 de fecha futura ya lo lanza `Corte.validar_fecha` (dominio) y ya
    está mapeado a HTTP en app/core/errores.py — no se maneja aquí.
    """
    corte = servicio.crear_corte(entrada.vigencia, entrada.fecha_corte)
    return _a_dto(corte)


@router.get("", response_model=list[CorteRespuesta])
def listar_cortes(servicio: ServicioCortesDep) -> list[CorteRespuesta]:
    """HU-01 / CA-8 (junto con GET /cortes/{id}): histórico de cortes."""
    return [_a_dto(corte) for corte in servicio.listar_cortes()]


@router.get("/{corte_id}", response_model=CorteRespuesta)
def obtener_corte(corte_id: UUID, servicio: ServicioCortesDep) -> CorteRespuesta:
    """HU-01 / CA-8 (junto con GET /cortes): detalle de un corte por id.

    El 404 ya lo lanza `ServicioCortes.obtener_corte` y ya está mapeado a
    HTTP en app/core/errores.py — no se maneja aquí.
    """
    return _a_dto(servicio.obtener_corte(corte_id))


# TODO [HU-01][BE-05] POST /cortes/{id}/registrar — Corte.registrar() y
#      ServicioCortes.registrar_corte() siguen NotImplementedError.
# TODO [HU-02..04][BE-04/BE-06] POST /cortes/{id}/archivos/{tipo}
# GAP: no existe hoy validación de "vigencia+fecha duplicada" (409) — no
#      hay consulta de aplicación que la soporte. Tarjeta nueva sugerida.
