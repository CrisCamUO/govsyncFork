"""Contratos (puertos) de la ingesta de archivos fuente.

CAPA: Dominio
TARJETAS: [HU-02][BE-01], [HU-03][BE-01], [HU-04][BE-01]

Patrón Strategy: cada fuente tiene reglas de reconocimiento y validación
PROPIAS Y DELIBERADAMENTE DISTINTAS —el PDT rechaza si falta una columna
(HU-02/CA-3), la plantilla BPIN se acepta tal cual la entrega el municipio
(HU-04/CA-2)—. Un `if tipo == ...` central mezclaría tres conjuntos de reglas
en una función y crecería con cada fuente nueva.

RESTRICCIÓN ARQUITECTÓNICA: sin pandas ni openpyxl aquí. La implementación
concreta va en `persistence/lectores/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.shared.codigos import CodigoIndicadorProducto, DescarteIndicador


class TipoArchivo(StrEnum):
    PDT = "PDT"
    EJECUCION = "EJECUCION"
    PROYECTOS = "PROYECTOS"


@dataclass(slots=True)
class ResultadoLectura:
    """Salida de Extract+Transform, antes de la etapa Load.

    Si el lector no pudo garantizar el formato NO devuelve un resultado
    parcial: lanza ArchivoInvalido. El rechazo es total (HU-02/CA-3).
    """

    tipo: TipoArchivo
    filas: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    conteos: dict[str, int] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
    descartes: list[DescarteIndicador] = field(default_factory=list)
    """D14 (docs/DECISIONES.md): fragmentos de indicador descartados por
    `CodigoIndicadorProducto.extraer_todos`, con su `categoria` estructural
    intacta -- sin reconstruirla como texto en `advertencias`. Reutiliza
    `DescarteIndicador` de `shared/codigos.py` directamente (mismo shared
    kernel que ya cruza las 4 fuentes; `shared/` no pertenece a ningun
    modulo, asi que esto no cruza la regla de modulos de
    `test_arquitectura.py`). Hoy solo `LectorProyectos` lo llena -- PDT y
    EJECUCION no producen descartes de codigo, asi que queda `[]` para
    ellos, que es el comportamiento correcto, no una limitacion a resolver.
    """
    codigos: list[CodigoIndicadorProducto] = field(default_factory=list)
    """[HU-04][FE-03]: la otra mitad de "vista previa de codigos extraidos
    y descartados" -- los codigos que SI se reconocieron (complemento de
    `descartes`, que solo cubre los que fallaron). Deduplicados por
    `.valor` preservando el orden de primera aparicion en el archivo
    (decision del equipo, 2026-09-20, ver docs/DECISIONES.md): la celda de
    Proyectos repite el mismo codigo de indicador para varios proyectos de
    forma legitima, y esta lista es para que la administradora confirme
    QUE se reconocio, no un log de ocurrencias -- eso ya lo cubre
    `total_reconocido`/`filas_reconocidas`. Mismo criterio de `descartes`:
    hoy solo `LectorProyectos` lo llena, PDT/EJECUCION quedan en `[]`.
    """

    @property
    def total_reconocido(self) -> int:
        """Conteo que se muestra a la administradora (HU-02/CA-5)."""
        return sum(self.conteos.values())


class LectorArchivoFuente(ABC):
    """Estrategia de lectura de un tipo de archivo fuente."""

    tipo: TipoArchivo

    @abstractmethod
    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        """Extrae y transforma. Lanza ArchivoInvalido si el archivo no aplica.

        `vigencia` [HU-02][BE-02]: al menos el PDT la necesita para resolver
        una columna obligatoria cuyo nombre real cambia cada año
        ("Programación del producto bien o servicio <vigencia>") — no se
        puede expresar como alias fijo en una constante de módulo. Los
        lectores que no la necesiten simplemente la ignoran.
        """
