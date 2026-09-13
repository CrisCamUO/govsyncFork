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

    @property
    def total_reconocido(self) -> int:
        """Conteo que se muestra a la administradora (HU-02/CA-5)."""
        return sum(self.conteos.values())


class LectorArchivoFuente(ABC):
    """Estrategia de lectura de un tipo de archivo fuente."""

    tipo: TipoArchivo

    @abstractmethod
    def leer(self, contenido: bytes, nombre_archivo: str) -> ResultadoLectura:
        """Extrae y transforma. Lanza ArchivoInvalido si el archivo no aplica."""
