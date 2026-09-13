"""Implementaciones SQLAlchemy de los puertos del módulo de cortes.

CAPA: Persistencia
TARJETA: [BD-02] Repositorios SQLAlchemy reemplazando los repositorios en memoria
DEPENDE DE: [BD-01]

De la tarjeta: «La conversión entre modelo ORM y entidad de dominio es
explícita: el ORM no se filtra hacia el Dominio.» Por eso existe `_a_dominio`:
ningún objeto de SQLAlchemy debe llegar a la aplicación ni a la respuesta HTTP.

Los repositorios hacen `flush()`, NUNCA `commit()`: la transacción la controla
el caso de uso (`ServicioCortes`, con `confirmar_transaccion` / `revertir_transaccion`).

=============================================================================
ALCANCE DE ESTA ENTREGA
=============================================================================
`RepositorioCortesSQL` queda completo (los seis métodos del puerto). La etapa
Load (`RepositorioDatosCorteSQL`) se implementa con cada tarjeta que la
consume: `reemplazar_metas` con [HU-02][BE-04], `reemplazar_presupuesto` con
[HU-03][BE-06], `reemplazar_proyectos` y `copiar_datos` con [HU-04]/[HU-01][BE-04].

=============================================================================
TRAMPA CONOCIDA — LEER ANTES DE ESCRIBIR reemplazar_presupuesto
=============================================================================
El `default=uuid.uuid4` de una columna SOLO se evalúa cuando SQLAlchemy emite
el INSERT. Si se construye el objeto y se lee `objeto.id` ANTES del flush, el
valor es None.

Al cargar el archivo presupuestal se necesita un índice
`codigo_rubro -> id` para resolver la FK de los 319 registros presupuestales
sin hacer una consulta por cada uno (N+1). Si ese índice se llena con `.id`
antes del flush, queda lleno de None, TODOS los registros se descartan y la
matriz de [HU-07] no muestra un solo contrato — sin ningún error visible.

Solución: generar el UUID explícitamente al construir el objeto
(`RubroORM(id=uuid.uuid4(), ...)`). Así se conserva la inserción en lote y se
elimina la trampa de orden. La misma regla aplica a `CorteORM` aquí.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, EstadoCorte, TipoArchivoFuente
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte
from app.modules.cortes.persistence.models import ArchivoFuenteORM, CorteORM
from app.shared.errors import RecursoNoEncontrado


def _archivo_a_dominio(o: ArchivoFuenteORM) -> ArchivoFuente:
    return ArchivoFuente(
        tipo=o.tipo,
        nombre_archivo=o.nombre_archivo,
        filas_reconocidas=o.filas_reconocidas,
        reutilizado=o.reutilizado,
        corte_origen_id=o.corte_origen_id,
    )


def _a_dominio(o: CorteORM) -> Corte:
    """Reconstruye la entidad de dominio. El ORM no cruza esta frontera."""
    return Corte(
        vigencia=o.vigencia,
        fecha_corte=o.fecha_corte,
        id=o.id,
        estado=o.estado,
        archivos={a.tipo: _archivo_a_dominio(a) for a in o.archivos},
    )


class RepositorioCortesSQL(RepositorioCortes):
    def __init__(self, sesion: Session) -> None:
        self._s = sesion

    def guardar(self, corte: Corte) -> Corte:
        orm = CorteORM(
            id=corte.id,
            vigencia=corte.vigencia,
            fecha_corte=corte.fecha_corte,
            estado=corte.estado,
        )
        for archivo in corte.archivos.values():
            orm.archivos.append(
                ArchivoFuenteORM(
                    id=uuid.uuid4(),
                    tipo=archivo.tipo,
                    nombre_archivo=archivo.nombre_archivo,
                    filas_reconocidas=archivo.filas_reconocidas,
                    reutilizado=archivo.reutilizado,
                    corte_origen_id=archivo.corte_origen_id,
                )
            )
        self._s.add(orm)
        self._s.flush()
        return _a_dominio(orm)

    def obtener(self, corte_id: uuid.UUID) -> Corte | None:
        orm = self._s.get(CorteORM, corte_id, options=[selectinload(CorteORM.archivos)])
        return _a_dominio(orm) if orm is not None else None

    def ultimo_registrado(self, vigencia: int | None = None) -> Corte | None:
        consulta = (
            select(CorteORM)
            .where(CorteORM.estado == EstadoCorte.REGISTRADO)
            .options(selectinload(CorteORM.archivos))
            .order_by(CorteORM.fecha_corte.desc(), CorteORM.fecha_creacion.desc())
            .limit(1)
        )
        if vigencia is not None:
            consulta = consulta.where(CorteORM.vigencia == vigencia)
        orm = self._s.scalars(consulta).first()
        return _a_dominio(orm) if orm is not None else None

    def listar(self) -> list[Corte]:
        consulta = (
            select(CorteORM)
            .options(selectinload(CorteORM.archivos))
            .order_by(CorteORM.fecha_corte.desc(), CorteORM.fecha_creacion.desc())
        )
        return [_a_dominio(o) for o in self._s.scalars(consulta)]

    def registrar_archivo(self, corte_id: uuid.UUID, archivo: ArchivoFuente) -> None:
        """Registra o REEMPLAZA el archivo de ese tipo (HU-06: corregir carga)."""
        existente = self._s.scalars(
            select(ArchivoFuenteORM).where(
                ArchivoFuenteORM.corte_id == corte_id,
                ArchivoFuenteORM.tipo == archivo.tipo,
            )
        ).first()
        if existente is not None:
            existente.nombre_archivo = archivo.nombre_archivo
            existente.filas_reconocidas = archivo.filas_reconocidas
            existente.reutilizado = archivo.reutilizado
            existente.corte_origen_id = archivo.corte_origen_id
        else:
            self._s.add(
                ArchivoFuenteORM(
                    id=uuid.uuid4(),
                    corte_id=corte_id,
                    tipo=archivo.tipo,
                    nombre_archivo=archivo.nombre_archivo,
                    filas_reconocidas=archivo.filas_reconocidas,
                    reutilizado=archivo.reutilizado,
                    corte_origen_id=archivo.corte_origen_id,
                )
            )
        self._s.flush()

    def confirmar_registro(self, corte: Corte) -> None:
        """Persiste el paso a estado REGISTRADO (la transición la valida el dominio)."""
        orm = self._s.get(CorteORM, corte.id)
        if orm is None:
            raise RecursoNoEncontrado(
                f"No existe el corte {corte.id} que se intenta registrar.",
                detalles={"motivo": "corte_no_encontrado", "corte_id": str(corte.id)},
            )
        orm.estado = corte.estado
        self._s.flush()


class RepositorioDatosCorteSQL(RepositorioDatosCorte):
    """Etapa Load del ETL. Escribe en lote; nunca hace commit por fila.

    Cada método se implementa con la tarjeta que lo consume; ver el docstring
    del módulo (ALCANCE DE ESTA ENTREGA) y la TRAMPA CONOCIDA del UUID previo
    al flush.
    """

    def __init__(self, sesion: Session) -> None:
        self._s = sesion

    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int:
        raise NotImplementedError("[HU-02][BE-04] Carga de metas del PDT")

    def reemplazar_presupuesto(
        self,
        corte_id: uuid.UUID,
        rubros: list[dict[str, Any]],
        contratos: list[dict[str, Any]],
        registros: list[dict[str, Any]],
    ) -> int:
        raise NotImplementedError("[HU-03][BE-06] Carga de ejecución y contratación")

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        raise NotImplementedError("[HU-04][BE-05] Carga de la plantilla de proyectos BPIN")

    def copiar_datos(
        self, origen_id: uuid.UUID, destino_id: uuid.UUID, tipo: TipoArchivoFuente
    ) -> int:
        raise NotImplementedError("[HU-01][BE-04] Copia física de una fuente reutilizada")
