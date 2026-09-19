"""Construcción de la matriz de relación.

CAPA: Persistencia
TARJETAS: [HU-07][BE-01] Servicio de cruce de las tres fuentes
          [HU-07][BE-02] Manejo de relaciones múltiples sin colapsar
          [HU-07][BE-03] Registro de no coincidencias sin asociación ficticia
CUBRE: HU-07 / CA-2 a CA-8

=============================================================================
ESTRUCTURA DEL CRUCE
=============================================================================
El eje es el código de indicador de producto de 9 dígitos, la única llave
presente en las cuatro fuentes (ver app/shared/codigos.py).

    meta (PDT)
      ├─ proyecto_indicador -> proyecto     -> columna «Cód. BPIN»
      └─ rubro (SOLO hojas)                 -> columna «Cód. indicador (ejec.)»
            └─ registro_presupuestal
                  └─ contrato               -> «Núm. contrato» y «Descripción»

=============================================================================
TRES REGLAS QUE NO SE PUEDEN ROMPER
=============================================================================

1. FILTRAR ultimo_nivel = true.
   111 de 485 filas de ejecución son subtotales jerárquicos que YA contienen a
   sus hojas. Sin el filtro, cada meta aparece además emparejada con el
   subtotal que la contiene: infla la matriz y, en cualquier suma posterior,
   el dinero.

2. TODOS LOS JOIN SON LEFT (CA-8).
   «Si determinada información no pudo relacionarse, NO se crea una asociación
   ficticia.» Los campos sin correspondencia viajan como NULL EXPLÍCITO, nunca
   como cadena vacía, cero ni "N/A". La distinción entre "no hay dato" y "hay
   dato vacío" se conserva hasta el frontend.
   Una meta sin BPIN, sin ejecución o sin contrato SIGUE APARECIENDO: es el
   insumo de las alertas de cruce de E-04/HU-05.

3. NO COLAPSAR RELACIONES MÚLTIPLES (CA-7) — leer con cuidado.
   La tarjeta [HU-07][BE-02] dice: «PROHIBIDO: DISTINCT, LIMIT 1, first(), o
   cualquier agregación que se quede con una sola fila "porque queda más
   limpio". El CA lo prohíbe.»

   Pruebas obligatorias de esa tarjeta:
     - Un indicador con dos BPIN    -> aparecen ambos.
     - Un BPIN con tres indicadores -> aparecen los tres.
     - Conteo total de filas contrastado con el cálculo manual esperado.
       MÁS filas de las esperadas TAMBIÉN es un defecto.

   OJO CON UN CASO QUE PARECE VIOLAR LA REGLA Y NO LO ES:
   un contrato tiene 1..N registros presupuestales (319 registros / 270
   contratos). Como NINGUNA de las seis columnas de la matriz sale de
   `registro_presupuestal` —esa tabla solo hace de puente hacia el contrato—,
   un JOIN directo produce filas IDÉNTICAS en las seis columnas.

   La salida correcta NO es un DISTINCT sobre el resultado (lo prohíbe la
   tarjeta), sino deduplicar el PUENTE:

       SELECT DISTINCT rubro_id, contrato_id FROM registro_presupuestal

   Así no se genera fan-out en ningún momento, no se oculta ninguna relación
   válida, y la deduplicación queda explícita sobre lo que significa: «el
   conjunto de vínculos entre rubro y contrato».

=============================================================================
CUIDADO CON EL CRUCE ENTRE CORTES
=============================================================================
`proyecto_indicador` no tiene corte_id propio (lo tiene `proyecto`). Si se
encadenan dos LEFT JOIN, un indicador de OTRO corte con el mismo código entra
al primer JOIN y produce una fila fantasma con el proyecto en NULL. Acotar el
corte DENTRO de la subconsulta de proyectos.

=============================================================================
RENDIMIENTO
=============================================================================
El cruce sobre los archivos reales produce miles de combinaciones. Paginar del
lado del servidor: [HU-07][FE-01] pide el endpoint con paginación.

=============================================================================
IMPLEMENTACIÓN [HU-07][BE-01]/[BE-02]/[BE-03]
=============================================================================
Las tres tarjetas viven en la misma sentencia (mismo archivo, misma función,
per PLANDETRABAJO.md 5.1-5.3): no son separables en el código porque CA-2..
CA-6 (BE-01, Juan Esteban), CA-7 (BE-02, Cristhian) y CA-8 (BE-03, Juan
Esteban) son propiedades de LA MISMA consulta, no funciones independientes —
no se puede escribir un JOIN correcto sin decidir a la vez cómo tratar el
fan-out (CA-7) y los NULL (CA-8). Coordinado con el equipo antes de tocar el
archivo (ver decisión del 2026-09-19).

Claves de columna (idénticas a `trazabilidad/api/router.py::COLUMNAS`, para
que el contrato de las seis columnas viva en un solo lugar — API y
persistencia usan las mismas cadenas literales a propósito):

    cod_bpin, cod_indicador_producto, nombre_producto,
    cod_indicador_ejecucion, numero_contrato, descripcion_contrato

DOS PUENTES, cada uno resuelto ANTES del JOIN principal (nunca como
subconsulta correlacionada por fila — sería N+1 disfrazado de ORM):

1. `proyecto_indicador` -> `proyecto`, ACOTADO AL CORTE dentro de la propia
   subconsulta (ver "CUIDADO CON EL CRUCE ENTRE CORTES" arriba): sin esto, un
   indicador de OTRO corte con el mismo código de 9 dígitos se colaría.

2. `registro_presupuestal` -> `contrato`, DEDUPLICADO por (rubro_id,
   contrato_id) — la solución de CA-7/BE-02 ya documentada en la regla 3 de
   arriba. Se filtra `rubro_id IS NOT NULL` porque un registro sin rubro
   resuelto (Decisión 5 de `RegistroPresupuestalORM`) no puede aportar una
   fila a ESTA matriz (el eje es el indicador, que vive en `rubro`, no en
   `registro_presupuestal`) — eso no pierde información: ese registro sigue
   existiendo en la tabla, solo no participa de este cruce por indicador.

DECISIÓN TÉCNICA (MENOR, registrada — ninguna CA define la forma exacta del
valor de retorno): `construir_matriz` devuelve un `ResultadoMatriz` con las
filas de la página pedida MÁS el total de filas sin paginar (`total`). Un CA
de paginación real vive en `[HU-07][FE-01]`, sin implementación de endpoint
todavía; sin el total, esa tarjeta no podría construir los controles de
paginación al llegarle el turno. Es un cambio de forma acotado a esta
función si el equipo prefiere otra forma.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.cortes.persistence.models import (
    ContratoORM,
    MetaORM,
    ProyectoIndicadorORM,
    ProyectoORM,
    RegistroPresupuestalORM,
    RubroORM,
)


@dataclass(frozen=True, slots=True)
class FilaMatriz:
    """Una fila de la matriz de relación (HU-07/CA-3 a CA-6).

    Las seis columnas confirmadas. Un campo en `None` es un NULL EXPLÍCITO
    (CA-8): "esa fuente no tenía información para este indicador", nunca "el
    dato vino vacío" — ver Regla 2 del docstring del módulo.
    """

    cod_indicador_producto: str
    nombre_producto: str | None
    cod_bpin: str | None
    cod_indicador_ejecucion: str | None
    numero_contrato: str | None
    descripcion_contrato: str | None


@dataclass(frozen=True, slots=True)
class ResultadoMatriz:
    """Página de la matriz + su total (ver DECISIÓN TÉCNICA del docstring)."""

    filas: list[FilaMatriz]
    total: int
    pagina: int
    tamano_pagina: int


def _construir_consulta_base(corte_id: uuid.UUID):
    """El cruce de las cuatro fuentes, SIN paginar — compartido entre el
    conteo total y la página pedida (ver `construir_matriz`).

    Regla 1 (subtotales): `RubroORM.ultimo_nivel.is_(True)` en el JOIN, nunca
    después — filtrar después de un LEFT JOIN no cambiaría el resultado de
    ESTA consulta en particular (no hay agregación), pero sí lo haría con
    cualquier evolución que sume `apropiacion_definitiva` sobre este mismo
    cruce; se deja en el JOIN por consistencia con esa regla, documentada
    para quien reutilice esta consulta como base de un reporte financiero.

    Regla 2 (LEFT JOIN, CA-8): TODOS los joins de meta hacia afuera son
    `outerjoin` — una meta sin BPIN, sin ejecución o sin contrato sigue
    apareciendo, con esos campos en `None`.
    """
    proyectos_del_corte = (
        select(
            ProyectoIndicadorORM.cod_indicador_producto.label("cod_indicador_producto"),
            ProyectoORM.bpin.label("bpin"),
        )
        .join(ProyectoORM, ProyectoORM.id == ProyectoIndicadorORM.proyecto_id)
        .where(ProyectoORM.corte_id == corte_id)
        .subquery()
    )

    # CA-7/[HU-07][BE-02]: deduplicar el PUENTE, no el resultado (Regla 3).
    puente_rubro_contrato = (
        select(
            RegistroPresupuestalORM.rubro_id.label("rubro_id"),
            RegistroPresupuestalORM.contrato_id.label("contrato_id"),
        )
        .distinct()
        .where(RegistroPresupuestalORM.rubro_id.is_not(None))
        .subquery()
    )

    return (
        select(
            MetaORM.cod_indicador_producto,
            MetaORM.nombre_producto,
            proyectos_del_corte.c.bpin.label("cod_bpin"),
            RubroORM.cod_indicador_producto.label("cod_indicador_ejecucion"),
            ContratoORM.numero_contrato,
            ContratoORM.objeto.label("descripcion_contrato"),
        )
        .where(MetaORM.corte_id == corte_id)
        .outerjoin(
            proyectos_del_corte,
            proyectos_del_corte.c.cod_indicador_producto == MetaORM.cod_indicador_producto,
        )
        .outerjoin(
            RubroORM,
            (RubroORM.corte_id == corte_id)
            & (RubroORM.cod_indicador_producto == MetaORM.cod_indicador_producto)
            & (RubroORM.ultimo_nivel.is_(True)),
        )
        .outerjoin(puente_rubro_contrato, puente_rubro_contrato.c.rubro_id == RubroORM.id)
        .outerjoin(ContratoORM, ContratoORM.id == puente_rubro_contrato.c.contrato_id)
    )


def construir_matriz(
    sesion: Session, corte_id: uuid.UUID, pagina: int = 1, tamano_pagina: int = 50
) -> ResultadoMatriz:
    """[HU-07][BE-01]/[BE-02]/[BE-03]: cruce de las 4 fuentes (CA-2 a CA-8).

    CA-2: usa información YA PROCESADA y persistida (`meta`/`proyecto`/
    `rubro`/`contrato`) — no vuelve a leer ningún Excel. La unificación de
    nombres de columna del indicador (HU03-CA03) ya ocurrió en la ingesta;
    esta consulta ni sabe que esa ambigüedad existió.
    """
    consulta_base = _construir_consulta_base(corte_id)

    total = sesion.scalar(select(func.count()).select_from(consulta_base.subquery())) or 0

    filas_crudas = sesion.execute(
        consulta_base.order_by(MetaORM.cod_indicador_producto)
        .offset((pagina - 1) * tamano_pagina)
        .limit(tamano_pagina)
    ).all()

    filas = [
        FilaMatriz(
            cod_indicador_producto=fila.cod_indicador_producto,
            nombre_producto=fila.nombre_producto,
            cod_bpin=fila.cod_bpin,
            cod_indicador_ejecucion=fila.cod_indicador_ejecucion,
            numero_contrato=fila.numero_contrato,
            descripcion_contrato=fila.descripcion_contrato,
        )
        for fila in filas_crudas
    ]
    return ResultadoMatriz(filas=filas, total=total, pagina=pagina, tamano_pagina=tamano_pagina)
