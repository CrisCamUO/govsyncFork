"""Endpoint de la matriz de relación.

CAPA: API
TARJETA: [HU-07][FE-01] Endpoint de la matriz con paginación

Sugerencia de diseño: enviar las COLUMNAS junto con los datos, para que el
contrato de las seis columnas confirmadas viva en un solo lugar y el frontend
no pueda desalinearse de él en silencio.

ALCANCE DE ESTA ITERACIÓN: solo GET /matriz-relacion/{corte_id}. El chequeo
de "las tres fuentes cargadas" (409) vive aquí, no en una capa de
aplicación nueva — PLANDETRABAJO.md (5.1-5.4) solo asigna 2 archivos a
HU-07 backend (consultas.py, este router), sin `trazabilidad/application/`.
Es una excepción deliberada al patrón de `cortes/api/router.py` (que sí
delega todo a casos_uso.py): el chequeo reutiliza `Corte.archivos_faltantes()`,
ya existente, no fabrica una regla de negocio nueva.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.dependencias import ServicioCortesDep, SesionDep
from app.modules.cortes.domain.entidades import Corte, TipoArchivoFuente
from app.modules.trazabilidad.persistence.consultas import construir_matriz
from app.shared.errors import OperacionNoPermitida

router = APIRouter(prefix="/matriz-relacion", tags=["Trazabilidad"])

#: Las seis columnas confirmadas (HU-07 / CA-3 a CA-6).
COLUMNAS: list[dict[str, str]] = [
    {"clave": "cod_bpin", "titulo": "Cód. BPIN", "fuente": "Proyectos"},
    {"clave": "cod_indicador_producto", "titulo": "Cód. indicador (SisPT)", "fuente": "PDT"},
    {"clave": "nombre_producto", "titulo": "Nombre del producto", "fuente": "PDT"},
    {
        "clave": "cod_indicador_ejecucion",
        "titulo": "Cód. indicador (ejecución)",
        "fuente": "Ejecución",
    },
    {"clave": "numero_contrato", "titulo": "Núm. contrato", "fuente": "Contratación"},
    {"clave": "descripcion_contrato", "titulo": "Descripción", "fuente": "Contratación"},
]


# --- DTOs (Pydantic, nunca la entidad de dominio/ORM) -----------------------


class FilaMatrizRespuesta(BaseModel):
    cod_indicador_producto: str
    nombre_producto: str | None
    cod_bpin: str | None
    cod_indicador_ejecucion: str | None
    numero_contrato: str | None
    descripcion_contrato: str | None


class MatrizRespuesta(BaseModel):
    corte_id: UUID
    pagina: int
    tamano_pagina: int
    total_filas: int
    filas: list[FilaMatrizRespuesta]


# --- Endpoints ---------------------------------------------------------------


@router.get("/{corte_id}", response_model=MatrizRespuesta)
def obtener_matriz(
    corte_id: UUID,
    servicio: ServicioCortesDep,
    sesion: SesionDep,
    pagina: int = 1,
    tamano_pagina: int = 50,
) -> MatrizRespuesta:
    """HU-07/CA-1: matriz de relación de un corte específico.

    404 ya lo lanza `ServicioCortes.obtener_corte` (RecursoNoEncontrado,
    mapeado en core/errores.py) — no se maneja aquí, mismo patrón que
    cortes/api/router.py::obtener_corte.

    409 si falta alguna de las tres fuentes: reutiliza
    `Corte.archivos_faltantes()` (ya existente, HU-01), sin duplicar la
    regla. `detalles.archivos_faltantes` nombra exactamente qué falta.
    """
    corte: Corte = servicio.obtener_corte(corte_id)

    faltantes: list[TipoArchivoFuente] = corte.archivos_faltantes()
    if faltantes:
        raise OperacionNoPermitida(
            "El corte no tiene todas las fuentes cargadas. "
            f"Falta: {', '.join(tipo.value for tipo in faltantes)}.",
            detalles={
                "motivo": "fuentes_incompletas",
                "archivos_faltantes": [tipo.value for tipo in faltantes],
            },
        )

    resultado = construir_matriz(sesion, corte_id, pagina, tamano_pagina)
    return MatrizRespuesta(
        corte_id=corte_id,
        pagina=resultado.pagina,
        tamano_pagina=resultado.tamano_pagina,
        total_filas=resultado.total,
        filas=[
            FilaMatrizRespuesta(
                cod_indicador_producto=fila.cod_indicador_producto,
                nombre_producto=fila.nombre_producto,
                cod_bpin=fila.cod_bpin,
                cod_indicador_ejecucion=fila.cod_indicador_ejecucion,
                numero_contrato=fila.numero_contrato,
                descripcion_contrato=fila.descripcion_contrato,
            )
            for fila in resultado.filas
        ],
    )


# TODO [HU-07][FE-01] GET /matriz-relacion/actual — requiere
#      ServicioCortes.obtener_corte_actual() en casos_uso.py (no existe
#      hoy, es código de Juan Esteban, no se agrega sin su aprobación).
#      Pendiente además: "actual" filtra por vigencia o es global — mismo
#      tipo de decisión que D9/D11, sin resolver.
