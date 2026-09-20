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
Cubre POST /cortes, GET /cortes, GET /cortes/{id} y PATCH /cortes/{id}. NO
cubre:

- POST /cortes/{id}/registrar: `Corte.registrar()` y
  `ServicioCortes.registrar_corte()` ya están implementados y probados
  (`casos_uso.py:245`) — es [HU-01][BE-05] (Juan Esteban); falta únicamente
  exponer el endpoint HTTP aquí, no la lógica de negocio.
- POST /cortes/{id}/archivos/{tipo}: implementado para los 3 tipos
  (PDT/EJECUCION/PROYECTOS, HU-02/03/04 CA-1) — el guard temporal que
  rechazaba EJECUCION/PROYECTOS con 501 se retiró: `[HU-03][BE-06]` y
  `[HU-04][BE-01]` ya cierran en `develop`. El cuerpo de éxito
  (`ArchivoFuenteRespuestaParcial`) ya expone `descartes` con `categoria`
  ([HU-04][FE-03], D14) pero sigue siendo provisional: no cumple todavía
  el contrato completo de `docs/ESPECIFICACIONES_TECNICAS.md` (falta
  `advertencias` y, para PROYECTOS, `proyectos_reconocidos`/
  `indicadores_extraidos` separados — ver docstring del DTO).

PATCH /cortes/{id} (D11, docs/DECISIONES.md, aclaración 2026-09-19): corrige
vigencia/fecha de un corte en BORRADOR. Solo aplica a BORRADOR (un
REGISTRADO se rechaza con 409), es total (exige vigencia y fecha_corte
juntos, mismo contrato que POST /cortes) y es exclusivamente vigencia/fecha
— no toca `archivos` (eso sigue su propio mecanismo de reemplazo por tipo,
HU-06). 409 por "vigencia+fecha duplicada" reutiliza
`existe_corte_duplicado` (domain/puertos.py, ya consumida por `crear_corte`)
excluyendo al propio corte que se corrige.

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

from fastapi import APIRouter, UploadFile, status
from pydantic import BaseModel

from app.core.dependencias import ServicioCortesDep
from app.modules.cortes.domain.entidades import Corte, TipoArchivoFuente
from app.shared.codigos import CategoriaDescarte

router = APIRouter(prefix="/cortes", tags=["Cortes de seguimiento"])


# --- DTOs (Pydantic, nunca la entidad de dominio/ORM) -----------------------


class CorteEntrada(BaseModel):
    vigencia: int
    fecha_corte: date


class CorteCorreccion(BaseModel):
    """D11: cuerpo de PATCH /cortes/{id}.

    Misma forma que `CorteEntrada` hoy, pero clase propia a propósito:
    corregir y crear son operaciones semánticamente distintas aunque
    compartan validación — el nombre debe reflejarlo en el schema de
    OpenAPI, y separarlas evita tener que elegir entre romper POST /cortes
    o duplicar la clase bajo presión si D11 evoluciona a un PATCH parcial
    más adelante.
    """

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


class DescarteRespuesta(BaseModel):
    """D14 (docs/DECISIONES.md): un fragmento de indicador descartado, con
    `categoria` para que la vista previa de [HU-04][FE-03] priorice
    descartes reales (POSIBLE_CERO_PERDIDO/LONGITUD_LARGA) sobre ruido de
    texto libre (LONGITUD_CORTA) — ver docstring de `CategoriaDescarte`
    en `shared/codigos.py`.
    """

    valor_crudo: str
    motivo: str
    categoria: CategoriaDescarte


class ArchivoFuenteRespuestaParcial(BaseModel):
    """Forma PROVISIONAL de la respuesta de POST /cortes/{id}/archivos/{tipo}.

    `descartes` ya cierra ([HU-04][FE-03], PR #77 propagó
    `ArchivoFuente.descartes` desde `ResultadoLectura`) — `[]` para
    PDT/EJECUCION (no producen descartes de código) y para archivos
    reutilizados, comportamiento correcto, no una limitación.

    Sigue sin ser el contrato completo de docs/ESPECIFICACIONES_TECNICAS.md:
    para PROYECTOS esa especificación también pide `proyectos_reconocidos`/
    `indicadores_extraidos` separados — `filas_reconocidas` sigue siendo un
    solo entero (`reemplazar_proyectos` no distingue ambos conteos hoy).
    Deliberadamente fuera de este cambio (Opción 2, registrada, no
    bloqueante) — ver docs/DECISIONES.md.

    `filas_ejecucion_reconocidas`/`filas_contratacion_reconocidas`
    ([HU-03][FE-01]) ya cierran: el dato ya existía completo en
    `ResultadoLectura.conteos` (`LectorEjecucion.leer`), solo faltaba
    propagarlo. `None` para PDT/PROYECTOS — no aplica a esos tipos.
    """

    tipo: str
    nombre_archivo: str
    filas_reconocidas: int
    filas_ejecucion_reconocidas: int | None = None
    filas_contratacion_reconocidas: int | None = None
    descartes: list[DescarteRespuesta]


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


@router.post(
    "/{corte_id}/archivos/{tipo}",
    response_model=ArchivoFuenteRespuestaParcial,
    status_code=status.HTTP_201_CREATED,
)
async def cargar_archivo(
    corte_id: UUID,
    tipo: TipoArchivoFuente,
    servicio: ServicioCortesDep,
    archivo: UploadFile,
) -> ArchivoFuenteRespuestaParcial:
    """HU-02/CA-1, HU-03/CA-1, HU-04/CA-1: los 3 tipos cierran de punta a punta.

    `tipo` tipado con `TipoArchivoFuente` -> FastAPI valida automáticamente
    cualquier valor fuera del enum con 422, sin código adicional aquí.

    El guard que rechazaba EJECUCION/PROYECTOS con 501
    (`TipoArchivoNoDisponible`) se retiró: `RepositorioDatosCorteSQL.
    reemplazar_presupuesto` (`[HU-03][BE-06]`) y `LectorProyectos.leer`
    (`[HU-04][BE-01]`) ya no lanzan `NotImplementedError` en `develop`.
    Ver docs/TRAZABILIDAD.md (HU-03/CA-1, HU-04/CA-1) para la evidencia.
    """
    contenido = await archivo.read()
    resultado = servicio.cargar_archivo(corte_id, tipo, contenido, archivo.filename)
    return ArchivoFuenteRespuestaParcial(
        tipo=resultado.tipo.value,
        nombre_archivo=resultado.nombre_archivo,
        filas_reconocidas=resultado.filas_reconocidas,
        filas_ejecucion_reconocidas=resultado.conteos.get("ejecucion"),
        filas_contratacion_reconocidas=resultado.conteos.get("contratacion"),
        descartes=[
            DescarteRespuesta(
                valor_crudo=descarte.valor_crudo,
                motivo=descarte.motivo,
                categoria=descarte.categoria,
            )
            for descarte in resultado.descartes
        ],
    )


@router.patch("/{corte_id}", response_model=CorteRespuesta)
def corregir_corte(
    corte_id: UUID, entrada: CorteCorreccion, servicio: ServicioCortesDep
) -> CorteRespuesta:
    """D11 (docs/DECISIONES.md, aclaración 2026-09-19): corrige vigencia/
    fecha de un corte en BORRADOR.

    404 (corte inexistente), 409 (corte no está en BORRADOR, o vigencia+
    fecha duplicada contra OTRO corte) y 422 (fecha futura) ya los lanza
    `ServicioCortes.corregir_corte` (dominio + aplicación) y ya están
    mapeados a HTTP en app/core/errores.py — no se manejan aquí.
    """
    corte = servicio.corregir_corte(corte_id, entrada.vigencia, entrada.fecha_corte)
    return _a_dto(corte)


# TODO [HU-01][BE-05] POST /cortes/{id}/registrar — el dominio y la
#      aplicación YA están implementados y probados (`Corte.registrar()`
#      en domain/entidades.py, `ServicioCortes.registrar_corte()` en
#      application/casos_uso.py:245, tests en test_casos_uso_cortes.py:258,
#      277, 285, 299) — falta únicamente exponer el endpoint HTTP aquí.
