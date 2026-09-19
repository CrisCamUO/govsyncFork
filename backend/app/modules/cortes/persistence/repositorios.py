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
consume: `copiar_datos` con [BD-03] (bug activo detectado en producción: HU-01/
CA-5, ya mergeado, lo llama sin protección — ver docs/TRAZABILIDAD.md),
`reemplazar_metas` con [HU-02][BE-04], `reemplazar_presupuesto` con
[HU-03][BE-06], `reemplazar_proyectos` con [HU-04][BE-04].

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
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, EstadoCorte, TipoArchivoFuente
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte
from app.modules.cortes.persistence.models import (
    ArchivoFuenteORM,
    ContratoORM,
    CorteORM,
    MetaORM,
    MetaProgramacionFisicaORM,
    ProgramacionFinancieraORM,
    ProyectoIndicadorORM,
    ProyectoORM,
    RegistroPresupuestalORM,
    RubroORM,
)
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

    def existe_borrador_activo(self) -> bool:
        """D11: consulta global, no filtra por vigencia (ver puertos.py)."""
        consulta = select(CorteORM.id).where(CorteORM.estado == EstadoCorte.BORRADOR).limit(1)
        return self._s.scalars(consulta).first() is not None

    def existe_corte_duplicado(
        self, vigencia: int, fecha_corte: date, *, excluir_id: uuid.UUID | None = None
    ) -> bool:
        """D9: respaldo de aplicación del índice único `ux_corte_vigencia_fecha`.

        `excluir_id` (D11): usado por `corregir_corte` para no autorrechazar
        un corte contra sí mismo.
        """
        consulta = (
            select(CorteORM.id)
            .where(CorteORM.vigencia == vigencia, CorteORM.fecha_corte == fecha_corte)
            .limit(1)
        )
        if excluir_id is not None:
            consulta = consulta.where(CorteORM.id != excluir_id)
        return self._s.scalars(consulta).first() is not None

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

    def confirmar_correccion(self, corte: Corte) -> None:
        """D11: persiste vigencia/fecha corregidas (la validación ya la hizo el dominio)."""
        orm = self._s.get(CorteORM, corte.id)
        if orm is None:
            raise RecursoNoEncontrado(
                f"No existe el corte {corte.id} que se intenta corregir.",
                detalles={"motivo": "corte_no_encontrado", "corte_id": str(corte.id)},
            )
        orm.vigencia = corte.vigencia
        orm.fecha_corte = corte.fecha_corte
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
        """[HU-02][BE-04]: reemplazo total de las metas del corte.

        "Reemplazo total" (docstring de la clase): borra las metas existentes
        de `corte_id` antes de insertar las nuevas — así HU-06 (corregir un
        PDT cargado por error) no acumula filas duplicadas. El `ON DELETE
        CASCADE` de `meta_programacion_fisica.meta_id` y
        `programacion_financiera.meta_id` (models.py) se encarga de sus
        hijas; ninguna tarjeta de HU-02 llena esas dos tablas todavía — el
        lector (`lectores/pdt.py`) solo produce el total del cuatrienio, no
        una serie por año — así que no hay nada que reinsertar ahí.

        UUID generado explícitamente al construir cada fila, siguiendo la
        TRAMPA CONOCIDA documentada arriba (el `default=uuid.uuid4` de la
        columna solo se evalúa al hacer flush): aquí no se lee `.id` antes
        del flush, pero se mantiene la misma disciplina para no reintroducir
        el error si este método sirve de plantilla para
        `reemplazar_presupuesto`/`reemplazar_proyectos`.
        """
        self._s.execute(delete(MetaORM).where(MetaORM.corte_id == corte_id))

        for meta in metas:
            self._s.add(
                MetaORM(
                    id=uuid.uuid4(),
                    corte_id=corte_id,
                    cod_indicador_producto=meta["cod_indicador_producto"],
                    cod_indicador_sistp=meta.get("cod_indicador_sistp"),
                    codigo_producto_mga=meta.get("codigo_producto_mga"),
                    nombre_producto=meta.get("nombre_producto"),
                    unidad_medida=meta.get("unidad_medida"),
                    meta_cuatrienio=meta.get("meta_cuatrienio"),
                    es_principal=bool(meta["principal"]),
                    bpin_relacionados=meta.get("bpin_relacionados"),
                )
            )

        self._s.flush()
        return len(metas)

    def reemplazar_presupuesto(
        self,
        corte_id: uuid.UUID,
        rubros: list[dict[str, Any]],
        contratos: list[dict[str, Any]],
        registros: list[dict[str, Any]],
    ) -> int:
        """[HU-03][BE-06]: reemplazo total de Rubro/Contrato/RegistroPresupuestal.

        Orden de escritura (no es arbitrario):

        1. Borra `contrato` y `rubro` existentes de `corte_id`. El `ON DELETE
           CASCADE` de `registro_presupuestal.contrato_id` (models.py) se
           encarga de las hijas — igual que `reemplazar_metas` con sus
           tablas hijas. No hace falta borrar `registro_presupuestal` aparte.
        2. Inserta `rubro`, construyendo `mapa_rubros: codigo_rubro_nivel ->
           id` MIENTRAS se insertan (no después): es la misma TRAMPA
           CONOCIDA documentada en el docstring del módulo (el `default` de
           `id` solo se evalúa al hacer flush) — se genera el UUID
           explícitamente antes de usarlo como valor del mapa.
        3. Inserta `contrato`, construyendo `mapa_contratos: numero_contrato
           -> id` de la misma forma. `llave_sustituta` queda NULL (DECISIÓN
           TÉCNICA documentada en `lectores/ejecucion.py`, delegada al
           equipo: no hay otro dato en el archivo real para calcularla).
        4. Inserta `registro_presupuestal`, resolviendo `contrato_id` con
           `mapa_contratos` (obligatorio: si no aparece, el registro no
           tiene contrato válido y se descarta — no debería ocurrir, porque
           `_leer_contratos_y_registros` siempre agrupa cada registro bajo
           el mismo NumeroContrato con el que arma `contratos`, pero esta
           función no debe asumir esa invariante del lector sin verificarla)
           y `rubro_id` con `mapa_rubros` buscando por `codigo_rubro_crudo`
           (Decisión 5 de RegistroPresupuestalORM: NULLABLE — si el código no
           cruza, `rubro_id` queda None y `codigo_rubro_crudo` conserva el
           dato original para trazabilidad).

        `valor_pagos` de cada registro queda NULL: ver DECISIÓN TÉCNICA en
        `lectores/ejecucion.py` (la columna "Pagos" del archivo real es a
        nivel de contrato, no hay desglose por CDP/registro individual).

        SUPUESTO (MENOR — registrado, no bloqueante): el valor de retorno es
        `len(rubros) + len(contratos) + registros_insertados` — el conteo
        REAL de filas insertadas en las tres tablas, no el tamaño de las
        listas recibidas: un registro descartado por no tener contrato
        válido (ver el `continue` de abajo) no cuenta, para no reportar como
        "reconocida" una fila que en realidad se perdió. Ninguna CA de HU-03
        define qué debe significar `ArchivoFuente.filas_reconocidas` cuando
        una sola carga llena tres tablas a la vez (a diferencia de
        `reemplazar_metas`, una sola tabla); si el equipo prefiere otro
        criterio (p. ej. solo `registros_insertados`, por ser la unidad "una
        fila del archivo original"), es un cambio de una línea aquí, sin
        impacto en el resto del pipeline.
        """
        self._s.execute(delete(ContratoORM).where(ContratoORM.corte_id == corte_id))
        self._s.execute(delete(RubroORM).where(RubroORM.corte_id == corte_id))

        mapa_rubros: dict[str, uuid.UUID] = {}
        for rubro in rubros:
            nueva_id = uuid.uuid4()
            mapa_rubros[rubro["codigo_rubro_nivel"]] = nueva_id
            self._s.add(
                RubroORM(
                    id=nueva_id,
                    corte_id=corte_id,
                    codigo_rubro_nivel=rubro["codigo_rubro_nivel"],
                    codigo_rubro_ccpet=rubro.get("codigo_rubro_ccpet"),
                    codigo_rubro_completo=rubro.get("codigo_rubro_completo"),
                    codigo_sector_ccpet=rubro.get("codigo_sector_ccpet"),
                    codigo_producto_ccpet=rubro.get("codigo_producto_ccpet"),
                    cod_indicador_producto=rubro.get("cod_indicador_producto"),
                    codigo_tipo_gasto=rubro.get("codigo_tipo_gasto"),
                    nombre_financiacion=rubro.get("nombre_financiacion"),
                    ultimo_nivel=bool(rubro["ultimo_nivel"]),
                    apropiacion_definitiva=rubro.get("apropiacion_definitiva"),
                    disponibilidad_acumulada=rubro.get("disponibilidad_acumulada"),
                    compromiso_acumulado=rubro.get("compromiso_acumulado"),
                    obligacion_acumulada=rubro.get("obligacion_acumulada"),
                    pago_acumulado=rubro.get("pago_acumulado"),
                )
            )

        mapa_contratos: dict[str, uuid.UUID] = {}
        for contrato in contratos:
            nueva_id = uuid.uuid4()
            mapa_contratos[contrato["numero_contrato"]] = nueva_id
            self._s.add(
                ContratoORM(
                    id=nueva_id,
                    corte_id=corte_id,
                    proyecto_id=None,
                    numero_contrato=contrato["numero_contrato"],
                    llave_sustituta=None,
                    objeto=contrato.get("objeto"),
                    modalidad_seleccion=contrato.get("modalidad_seleccion"),
                    tipo_gasto=contrato.get("tipo_gasto"),
                    nit_contratista=contrato.get("nit_contratista"),
                    nombre_contratista=contrato.get("nombre_contratista"),
                    valor_contrato=contrato.get("valor_contrato"),
                    valor_pagado=contrato.get("valor_pagado"),
                    bpin=contrato.get("bpin"),
                    cod_indicador_producto=contrato.get("cod_indicador_producto"),
                )
            )

        registros_insertados = 0
        for registro in registros:
            contrato_id = mapa_contratos.get(registro["numero_contrato"])
            if contrato_id is None:
                # Defensivo: no debería ocurrir (ver docstring arriba), pero
                # un registro sin contrato válido no es insertable
                # (contrato_id es NOT NULL en registro_presupuestal) — se
                # descarta en vez de dejar que el INSERT falle con un error
                # de integridad crudo, mismo criterio que _leer_rubros con
                # UltimoNivel no reconocible. NO cuenta en el retorno: contar
                # una fila descartada como "reconocida" ocultaría la pérdida.
                continue
            self._s.add(
                RegistroPresupuestalORM(
                    id=uuid.uuid4(),
                    contrato_id=contrato_id,
                    rubro_id=mapa_rubros.get(registro.get("codigo_rubro_crudo")),
                    codigo_rubro_crudo=registro.get("codigo_rubro_crudo"),
                    numero_cdp=registro.get("numero_cdp"),
                    fecha_cdp=registro.get("fecha_cdp"),
                    valor_cdp=registro.get("valor_cdp"),
                    numero_registro=registro.get("numero_registro"),
                    fecha_registro=registro.get("fecha_registro"),
                    valor_registro_ptal=registro.get("valor_registro_ptal"),
                    valor_pagos=None,
                )
            )
            registros_insertados += 1

        self._s.flush()
        return len(rubros) + len(contratos) + registros_insertados

    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int:
        """[HU-04][BE-04]: reemplazo total de Proyecto + ProyectoIndicador.

        Más simple que `reemplazar_presupuesto`: `ProyectoIndicadorORM` SÍ es
        una relationship con cascade (`ProyectoORM.indicadores`, igual que
        `_copiar_proyectos` de abajo) — no hace falta un mapa de ids manual,
        SQLAlchemy resuelve `proyecto_id` de las hijas al hacer flush.

        Deduplicación de códigos de indicador: `CodigoIndicadorProducto.
        extraer_todos` (el lector, `proyectos.py`) NO deduplica a propósito
        (ver su docstring: un código repetido en la celda es información
        real). Pero `ProyectoIndicadorORM` tiene
        `UniqueConstraint(proyecto_id, cod_indicador_producto)` — insertar el
        duplicado tal cual rompería el INSERT con un error de integridad
        crudo. Se deduplica AQUÍ, en la etapa Load (con `dict.fromkeys` para
        conservar el orden de aparición), no en el lector: es la misma
        separación de responsabilidades que ya aplica
        `reemplazar_presupuesto` (extracción vs. persistencia).

        SUPUESTO (MENOR — mismo criterio ya registrado en
        `reemplazar_presupuesto`): el retorno es
        `len(proyectos) + indicadores_insertados` (total de filas
        insertadas, después de deduplicar) — no hay CA que defina qué debe
        significar `ArchivoFuente.filas_reconocidas` para esta carga.
        """
        self._s.execute(delete(ProyectoORM).where(ProyectoORM.corte_id == corte_id))

        indicadores_insertados = 0
        for proyecto in proyectos:
            nuevo = ProyectoORM(
                id=uuid.uuid4(),
                corte_id=corte_id,
                bpin=proyecto.get("bpin"),
                nombre_proyecto=proyecto.get("nombre_proyecto"),
                indicador_producto_raw=proyecto.get("indicador_producto_raw"),
            )
            for codigo in dict.fromkeys(proyecto.get("codigos_indicador", ())):
                nuevo.indicadores.append(
                    ProyectoIndicadorORM(id=uuid.uuid4(), cod_indicador_producto=codigo)
                )
                indicadores_insertados += 1
            self._s.add(nuevo)

        self._s.flush()
        return len(proyectos) + indicadores_insertados

    def copiar_datos(
        self, origen_id: uuid.UUID, destino_id: uuid.UUID, tipo: TipoArchivoFuente
    ) -> int:
        """Copia física de los datos de `tipo` (HU-01/CA-5). [BD-03].

        Genera IDs nuevos para cada fila copiada: cada corte es una fotografía
        independiente, ninguna fila puede pertenecer a dos cortes a la vez.
        Solo PDT y PROYECTOS son copiables (`puede_reutilizar` en entidades.py
        ya descarta EJECUCION antes de llegar aquí); cualquier otro tipo es un
        error de contrato del llamador, no una regla de dominio.
        """
        if tipo is TipoArchivoFuente.PDT:
            return self._copiar_metas(origen_id, destino_id)
        if tipo is TipoArchivoFuente.PROYECTOS:
            return self._copiar_proyectos(origen_id, destino_id)
        raise ValueError(f"El tipo {tipo!r} no es una fuente copiable/reutilizable.")

    def _copiar_metas(self, origen_id: uuid.UUID, destino_id: uuid.UUID) -> int:
        """Copia `meta` y sus hijas (`meta_programacion_fisica`,
        `programacion_financiera` con `meta_id`) al corte destino.

        Sin relationship declarada entre MetaORM y sus hijas en models.py:
        se resuelven con un mapa id_origen -> id_nuevo, igual a la trampa de
        UUID documentada arriba (se genera el id ANTES de usarlo como FK).
        """
        metas_origen = self._s.scalars(select(MetaORM).where(MetaORM.corte_id == origen_id)).all()
        if not metas_origen:
            return 0

        mapa_ids: dict[uuid.UUID, uuid.UUID] = {}
        for meta in metas_origen:
            nueva_id = uuid.uuid4()
            mapa_ids[meta.id] = nueva_id
            self._s.add(
                MetaORM(
                    id=nueva_id,
                    corte_id=destino_id,
                    cod_indicador_producto=meta.cod_indicador_producto,
                    cod_indicador_sistp=meta.cod_indicador_sistp,
                    codigo_producto_mga=meta.codigo_producto_mga,
                    nombre_producto=meta.nombre_producto,
                    unidad_medida=meta.unidad_medida,
                    meta_cuatrienio=meta.meta_cuatrienio,
                    es_principal=meta.es_principal,
                    bpin_relacionados=meta.bpin_relacionados,
                )
            )

        programaciones = self._s.scalars(
            select(MetaProgramacionFisicaORM).where(
                MetaProgramacionFisicaORM.meta_id.in_(mapa_ids.keys())
            )
        ).all()
        for programacion in programaciones:
            self._s.add(
                MetaProgramacionFisicaORM(
                    id=uuid.uuid4(),
                    meta_id=mapa_ids[programacion.meta_id],
                    anio=programacion.anio,
                    valor_programado=programacion.valor_programado,
                )
            )

        # Solo las financiadas por meta (el PDT programa a nivel de meta); el
        # enlace por proyecto_id no lo llena ninguna tarjeta actual (ver el
        # comentario de ProgramacionFinancieraORM en models.py).
        financiera = self._s.scalars(
            select(ProgramacionFinancieraORM).where(
                ProgramacionFinancieraORM.meta_id.in_(mapa_ids.keys())
            )
        ).all()
        for programacion in financiera:
            self._s.add(
                ProgramacionFinancieraORM(
                    id=uuid.uuid4(),
                    meta_id=mapa_ids[programacion.meta_id],
                    proyecto_id=None,
                    fuente=programacion.fuente,
                    anio=programacion.anio,
                    valor_programado=programacion.valor_programado,
                )
            )

        self._s.flush()
        return len(metas_origen)

    def _copiar_proyectos(self, origen_id: uuid.UUID, destino_id: uuid.UUID) -> int:
        """Copia `proyecto` y sus `proyecto_indicador` al corte destino.

        A diferencia de `_copiar_metas`, `ProyectoORM.indicadores` SÍ es una
        relationship (cascade): agregar a `nuevo.indicadores` deja que
        SQLAlchemy resuelva el `proyecto_id` de las hijas al hacer flush, sin
        necesidad de un mapa de ids manual.
        """
        proyectos_origen = self._s.scalars(
            select(ProyectoORM)
            .where(ProyectoORM.corte_id == origen_id)
            .options(selectinload(ProyectoORM.indicadores))
        ).all()

        for proyecto in proyectos_origen:
            nuevo = ProyectoORM(
                id=uuid.uuid4(),
                corte_id=destino_id,
                bpin=proyecto.bpin,
                nombre_proyecto=proyecto.nombre_proyecto,
                indicador_producto_raw=proyecto.indicador_producto_raw,
            )
            for indicador in proyecto.indicadores:
                nuevo.indicadores.append(
                    ProyectoIndicadorORM(
                        id=uuid.uuid4(),
                        cod_indicador_producto=indicador.cod_indicador_producto,
                    )
                )
            self._s.add(nuevo)

        self._s.flush()
        return len(proyectos_origen)
