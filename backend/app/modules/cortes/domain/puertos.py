"""Puertos (interfaces de repositorio) del módulo de cortes.

CAPA: Dominio
TARJETA: [HU-01][BE-02] Contrato de repositorio de Corte y migración

El dominio define el contrato; `persistence/` lo implementa. Los casos de uso
dependen de estas abstracciones, nunca de SQLAlchemy (Inversión de
Dependencias).

De la tarjeta [BD-02]: «Los repositorios en memoria se conservan, pero solo
para pruebas unitarias. La conversión entre modelo ORM y entidad de dominio es
explícita: el ORM no se filtra hacia el Dominio.»
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, TipoArchivoFuente


class RepositorioCortes(ABC):
    @abstractmethod
    def guardar(self, corte: Corte) -> Corte:
        """Persiste un corte nuevo (siempre en estado BORRADOR)."""

    @abstractmethod
    def existe_borrador_activo(self) -> bool:
        """D11: hay como máximo un corte en BORRADOR en toda la tabla,
        sin importar la vigencia (docs/DECISIONES.md, D11).

        `crear_corte` (casos_uso.py) lo consulta ANTES de `guardar()` para
        devolver un 409 legible (OperacionNoPermitida) en vez de dejar que
        la violación del índice único parcial `estado='BORRADOR'` llegue
        como un error de integridad crudo. El índice sigue siendo necesario
        como respaldo contra la condición de carrera (dos POST /cortes casi
        simultáneos) — este método no lo reemplaza, resuelve el caso común
        con un mensaje de negocio.
        """

    @abstractmethod
    def existe_corte_duplicado(
        self, vigencia: int, fecha_corte: date, *, excluir_id: uuid.UUID | None = None
    ) -> bool:
        """D9: no puede haber dos cortes con la misma vigencia y la misma
        fecha_corte exacta (docs/DECISIONES.md, D9).

        `crear_corte` (casos_uso.py) lo consulta ANTES de `guardar()` para
        devolver un 409 legible (OperacionNoPermitida) en vez de dejar que
        la violación del índice único `ux_corte_vigencia_fecha` llegue como
        un `IntegrityError` crudo (500). El índice de BD sigue siendo
        necesario como respaldo contra la condición de carrera — este
        método no lo reemplaza, resuelve el caso común con un mensaje de
        negocio, igual que `existe_borrador_activo` para D11.

        `excluir_id` (D11, PATCH /cortes/{id}): `corregir_corte` consulta
        este método contra el propio corte que está corrigiendo — sin
        excluirlo, corregir un corte manteniendo su misma vigencia/fecha se
        autorrechazaría con un 409 falso.
        """

    @abstractmethod
    def obtener(self, corte_id: uuid.UUID) -> Corte | None: ...

    @abstractmethod
    def ultimo_registrado(self, vigencia: int | None = None) -> Corte | None:
        """Corte REGISTRADO más reciente. Base de la reutilización (CA-5)."""

    @abstractmethod
    def listar(self) -> list[Corte]:
        """Histórico de cortes, del más reciente al más antiguo (CA-4)."""

    @abstractmethod
    def registrar_archivo(self, corte_id: uuid.UUID, archivo: ArchivoFuente) -> None:
        """Registra o REEMPLAZA el archivo de ese tipo (HU-06: corregir carga)."""

    @abstractmethod
    def confirmar_registro(self, corte: Corte) -> None:
        """Persiste el paso a estado REGISTRADO."""

    @abstractmethod
    def confirmar_correccion(self, corte: Corte) -> None:
        """D11: persiste vigencia/fecha corregidas de un corte en BORRADOR.

        La validación (estado BORRADOR, fecha no futura) ya la hizo el
        dominio (`Corte.corregir()`) antes de llegar aquí — este método solo
        persiste.
        """


class RepositorioDatosCorte(ABC):
    """Persistencia de los datos extraídos de los archivos fuente (etapa Load).

    Todas las operaciones son de REEMPLAZO TOTAL por corte y tipo de fuente:
    volver a cargar un archivo borra lo anterior. Es lo que hace que HU-06
    (corregir un archivo cargado por error) no acumule filas duplicadas.
    """

    @abstractmethod
    def reemplazar_metas(self, corte_id: uuid.UUID, metas: list[dict[str, Any]]) -> int: ...

    @abstractmethod
    def reemplazar_presupuesto(
        self,
        corte_id: uuid.UUID,
        rubros: list[dict[str, Any]],
        contratos: list[dict[str, Any]],
        registros: list[dict[str, Any]],
    ) -> int: ...

    @abstractmethod
    def reemplazar_proyectos(self, corte_id: uuid.UUID, proyectos: list[dict[str, Any]]) -> int: ...

    @abstractmethod
    def copiar_datos(
        self, origen_id: uuid.UUID, destino_id: uuid.UUID, tipo: TipoArchivoFuente
    ) -> int:
        """Copia FÍSICA de los datos de una fuente reutilizada (CA-5).

        Regla verificada: cada corte es una fotografía independiente. Los BPIN
        de un año a otro no coinciden (0 de 59 códigos de 2025 aparecen en los
        24 de 2026), así que no hay nada que "compartir" entre cortes. Al
        reutilizar se COPIAN las filas con el corte_id nuevo; ninguna fila
        puede pertenecer a dos cortes.
        """
