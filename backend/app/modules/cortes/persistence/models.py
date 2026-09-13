"""Modelos ORM del corte y de los datos que sus fuentes alimentan.

CAPA: Persistencia
TARJETA: [BD-01] Modelo de dominio y migraciones Alembic iniciales
DESBLOQUEA: [BD-02] repositorios, y con ello los casos de uso de HU-01..HU-04, HU-07

=============================================================================
[REF-01] / D1 — RATIFICADA (docs/DECISIONES.md, 2026-09-08)
=============================================================================
La migración de Alembic es la ÚNICA fuente de verdad del esquema. Los tres
`.sql` que circulaban quedan como material histórico. Este archivo declara los
modelos; `alembic revision --autogenerate -m "esquema inicial"` genera la
migración a partir de `Base.metadata`.

=============================================================================
TABLAS DEL SPRINT 1
=============================================================================
  corte                      vigencia, fecha_corte, estado(BORRADOR|REGISTRADO)
  archivo_fuente             corte_id, tipo, nombre, filas, reutilizado, origen
  meta                       del PDT                       -> [HU-02]
  meta_programacion_fisica   cantidad programada por año    -> [HU-02]
  programacion_financiera    monto programado por fuente/año -> [HU-02]
  proyecto                   de la plantilla BPIN           -> [HU-04]
  proyecto_indicador         separación multivalor (N:M)    -> [HU-04][BE-03]
  rubro                      de la pestaña Ejecución         -> [HU-03]
  contrato                   de la pestaña Contratación      -> [HU-03]
  registro_presupuestal      puente contrato <-> rubro (1..N por contrato)

=============================================================================
DECISIONES DE MODELO VERIFICADAS CONTRA LOS DATOS REALES (docs/DECISIONES.md)
=============================================================================
1. Los códigos de indicador son String(9), NUNCA Integer. Cuatro empiezan en
   cero (040110500, 040600400, 040600500, 040601600).
2. `rubro.ultimo_nivel` NOT NULL. 111 de 485 filas son subtotales jerárquicos.
3. UNIQUE(corte_id, codigo_rubro_nivel). NO sobre codigo_rubro_ccpet (142
   duplicados verificados).
4. `registro_presupuestal` SIN restricción UNIQUE: 45 filas repiten
   (contrato, registro) con rubros distintos. Deuda técnica documentada.
5. `registro_presupuestal.rubro_id` NULLABLE a propósito: si el código de
   rubro de Contratación no cruza, se guarda `codigo_rubro_crudo` para
   diagnóstico en vez de rechazar la carga completa.
6. `meta.es_principal` BOOLEAN NOT NULL (HU-02/CA-3 la exige como columna).
7. Índice (corte_id, cod_indicador_producto) en meta, rubro y contrato: son
   las condiciones de JOIN de la matriz de [HU-07].

Adicional (D1/D3, docs/DECISIONES.md): a lo sumo un corte BORRADOR por
vigencia -> índice único parcial `WHERE estado = 'BORRADOR'`.

RESTRICCIÓN ARQUITECTÓNICA: SQLAlchemy vive aquí (capa persistencia); pandas y
openpyxl no. Lo verifica tests/test_arquitectura.py.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.cortes.domain.entidades import EstadoCorte, TipoArchivoFuente

#: Precisión de columnas monetarias (pesos colombianos, dos decimales).
DINERO = sa.Numeric(20, 2)
#: Precisión de columnas de cantidad física (la meta puede ser fraccionaria).
CANTIDAD = sa.Numeric(18, 4)

_ESTADO_CORTE = sa.Enum(EstadoCorte, name="estado_corte")
_TIPO_ARCHIVO = sa.Enum(TipoArchivoFuente, name="tipo_archivo_fuente")


class CorteORM(Base):
    """La tripleta (municipio, vigencia, fecha) — el agregado raíz."""

    __tablename__ = "corte"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    vigencia: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    fecha_corte: Mapped[date] = mapped_column(nullable=False)
    estado: Mapped[EstadoCorte] = mapped_column(
        _ESTADO_CORTE, nullable=False, default=EstadoCorte.BORRADOR
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    archivos: Mapped[list[ArchivoFuenteORM]] = relationship(
        back_populates="corte",
        foreign_keys="ArchivoFuenteORM.corte_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # D1/D3: solo puede haber un borrador abierto por vigencia. Los cortes
        # REGISTRADOS de la misma vigencia sí conviven (histórico / versiones).
        sa.Index(
            "ux_corte_borrador_por_vigencia",
            "vigencia",
            unique=True,
            postgresql_where=sa.text("estado = 'BORRADOR'"),
            sqlite_where=sa.text("estado = 'BORRADOR'"),
        ),
    )


class ArchivoFuenteORM(Base):
    """Registro de cada archivo asociado a un corte (nuevo o reutilizado)."""

    __tablename__ = "archivo_fuente"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[TipoArchivoFuente] = mapped_column(_TIPO_ARCHIVO, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    filas_reconocidas: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    reutilizado: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    corte_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="SET NULL"), nullable=True
    )
    fecha_carga: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    corte: Mapped[CorteORM] = relationship(back_populates="archivos", foreign_keys=[corte_id])

    __table_args__ = (
        # HU-06: reemplazar un archivo del corte sustituye el de ese tipo.
        sa.UniqueConstraint("corte_id", "tipo", name="ux_archivo_por_tipo"),
    )


class MetaORM(Base):
    """Meta / indicador de producto del Plan Indicativo (una por corte)."""

    __tablename__ = "meta"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="CASCADE"), nullable=False
    )
    # Decisión 1: código MGA de 9 dígitos como TEXTO. Llave del cruce de HU-07.
    cod_indicador_producto: Mapped[str] = mapped_column(sa.String(9), nullable=False)
    cod_indicador_sistp: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    codigo_producto_mga: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)
    nombre_producto: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    unidad_medida: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    meta_cuatrienio: Mapped[Decimal | None] = mapped_column(CANTIDAD, nullable=True)
    # Decisión 6: la eficacia solo considera indicadores principales.
    es_principal: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    # BPIN multivaluado del PDT, crudo (coma-separado). El cruce real de HU-07
    # va por `proyecto_indicador`; esta columna queda para diagnóstico.
    bpin_relacionados: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (sa.Index("ix_meta_cruce", "corte_id", "cod_indicador_producto"),)


class MetaProgramacionFisicaORM(Base):
    """Cantidad física programada de una meta, por año (formato ancho del PDT)."""

    __tablename__ = "meta_programacion_fisica"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    meta_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("meta.id", ondelete="CASCADE"), nullable=False
    )
    anio: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    # PI2: no se descartan las metas con programación cero; el valor puede ser 0.
    valor_programado: Mapped[Decimal | None] = mapped_column(CANTIDAD, nullable=True)

    __table_args__ = (sa.UniqueConstraint("meta_id", "anio", name="ux_prog_fisica_meta_anio"),)


class ProgramacionFinancieraORM(Base):
    """Monto financiero programado por meta, fuente de financiación y año.

    `proyecto_id` NULLABLE: el PDT programa a nivel de meta; el enlace a
    proyecto solo se llena si la fuente lo aporta (fuera del alcance de HU-02).
    """

    __tablename__ = "programacion_financiera"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    meta_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("meta.id", ondelete="CASCADE"), nullable=True
    )
    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("proyecto.id", ondelete="CASCADE"), nullable=True
    )
    fuente: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    anio: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    valor_programado: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)

    __table_args__ = (sa.Index("ix_prog_financiera_meta", "meta_id"),)


class ProyectoORM(Base):
    """Proyecto BPIN de la plantilla del municipio. Se almacena TAL CUAL (HU-04/CA-2)."""

    __tablename__ = "proyecto"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="CASCADE"), nullable=False
    )
    # Sin normalizar: uno de los 38 proyectos reales no cumple 15 dígitos (CA-2).
    bpin: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    nombre_proyecto: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Celda multivalor original, antes de la separación de [HU-04][BE-03].
    indicador_producto_raw: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    indicadores: Mapped[list[ProyectoIndicadorORM]] = relationship(
        back_populates="proyecto", cascade="all, delete-orphan"
    )


class ProyectoIndicadorORM(Base):
    """Relación N:M proyecto <-> indicador de producto (HU-04/CA-4).

    Sin `corte_id` propio: lo hereda de `proyecto` (regla de HU-07 para no
    generar filas fantasma que crucen cortes).
    """

    __tablename__ = "proyecto_indicador"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("proyecto.id", ondelete="CASCADE"), nullable=False
    )
    cod_indicador_producto: Mapped[str] = mapped_column(sa.String(9), nullable=False)

    proyecto: Mapped[ProyectoORM] = relationship(back_populates="indicadores")

    __table_args__ = (
        sa.UniqueConstraint("proyecto_id", "cod_indicador_producto", name="ux_proyecto_indicador"),
        sa.Index("ix_proyecto_indicador_cod", "cod_indicador_producto"),
    )


class RubroORM(Base):
    """Rubro presupuestal de la pestaña de Ejecución. La bisagra del cruce."""

    __tablename__ = "rubro"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="CASCADE"), nullable=False
    )
    # Decisión 3: llave real del rubro. NO codigo_rubro_ccpet (142 duplicados).
    codigo_rubro_nivel: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    codigo_rubro_ccpet: Mapped[str | None] = mapped_column(sa.String(150), nullable=True)
    # Código largo con sufijos (-Actual-ENTIDAD-1), para casar contra Contratación.
    codigo_rubro_completo: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    codigo_sector_ccpet: Mapped[str | None] = mapped_column(sa.String(2), nullable=True)
    codigo_producto_ccpet: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)
    # Segundo segmento de codigo_rubro_nivel (EJ4); nullable en subtotales.
    cod_indicador_producto: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    codigo_tipo_gasto: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    nombre_financiacion: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Decisión 2: 111 de 485 filas son subtotales jerárquicos; se excluyen del cruce.
    ultimo_nivel: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    apropiacion_definitiva: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    disponibilidad_acumulada: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    compromiso_acumulado: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    # OrdenPagoAcumulado — base del % de avance financiero (docs, D5 del maestro).
    obligacion_acumulada: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    pago_acumulado: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("corte_id", "codigo_rubro_nivel", name="ux_rubro_nivel"),
        sa.Index("ix_rubro_cruce", "corte_id", "cod_indicador_producto"),
    )


class ContratoORM(Base):
    """Contrato de la pestaña de Contratación (una fila por contrato distinto)."""

    __tablename__ = "contrato"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("corte.id", ondelete="CASCADE"), nullable=False
    )
    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("proyecto.id", ondelete="SET NULL"), nullable=True
    )
    # CT2: NumeroContrato no es llave única. `llave_sustituta` la calcula [HU-03].
    numero_contrato: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    llave_sustituta: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    objeto: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    modalidad_seleccion: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    tipo_gasto: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    nit_contratista: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    nombre_contratista: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valor_contrato: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    valor_pagado: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    bpin: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    # "Cod Indicador Ccpet" — mismo dato canónico que el de ejecución (HU-03/CA-3).
    cod_indicador_producto: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)

    registros: Mapped[list[RegistroPresupuestalORM]] = relationship(
        back_populates="contrato", cascade="all, delete-orphan"
    )

    __table_args__ = (sa.Index("ix_contrato_cruce", "corte_id", "cod_indicador_producto"),)


class RegistroPresupuestalORM(Base):
    """Línea CDP/RP de un contrato contra un rubro (1..N por contrato)."""

    __tablename__ = "registro_presupuestal"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    contrato_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("contrato.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Decisión 5: NULLABLE. Si el código de rubro no cruza, se guarda el crudo.
    rubro_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("rubro.id", ondelete="SET NULL"), nullable=True
    )
    codigo_rubro_crudo: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    numero_cdp: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    fecha_cdp: Mapped[date | None] = mapped_column(nullable=True)
    valor_cdp: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    numero_registro: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    fecha_registro: Mapped[date | None] = mapped_column(nullable=True)
    valor_registro_ptal: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)
    valor_pagos: Mapped[Decimal | None] = mapped_column(DINERO, nullable=True)

    contrato: Mapped[ContratoORM] = relationship(back_populates="registros")

    # Decisión 4: SIN UniqueConstraint. 45 filas repiten (contrato, registro)
    # con rubros distintos en el archivo real — deuda técnica documentada hasta
    # revisar esos casos con quien conoce el proceso de captura en Tesorería.
