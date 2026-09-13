"""Entidades y reglas de negocio del módulo de cortes.

CAPA: Dominio
TARJETA: [HU-01][BE-01] Entidad de dominio Corte con invariantes y estados
CUBRE: HU-01 / CA-2, CA-4

=============================================================================
INVARIANTES (de la tarjeta)
=============================================================================
- La vigencia no puede ser fecha futura (CA-2). Al violarse lanza excepción de
  dominio CON EL MOTIVO, no un error genérico.
- El paso a REGISTRADO exige las tres fuentes asociadas (CA-4).
- Un corte REGISTRADO no admite cambio de vigencia.

=============================================================================
POR QUÉ EL CORTE TIENE ESTADO
=============================================================================
HU-01/CA-3 exige que un corte incompleto NO quede registrado, pero
HU-02/CA-1, HU-03/CA-1 y HU-04/CA-1 exigen subir archivos contra un corte que
ya existe. Sin un estado explícito ambas cosas son incompatibles: los archivos
se cargan contra un corte en BORRADOR y solo al completarse pasa a REGISTRADO
y entra al histórico.

RESTRICCIÓN ARQUITECTÓNICA: sin imports de SQLAlchemy, FastAPI, pandas ni
openpyxl. Lo verifica tests/test_arquitectura.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

# from enum import Enum
from enum import StrEnum

from app.shared.errors import ReglaDeNegocioViolada


class EstadoCorte(StrEnum):
    BORRADOR = "BORRADOR"
    REGISTRADO = "REGISTRADO"


class TipoArchivoFuente(StrEnum):
    PDT = "PDT"
    EJECUCION = "EJECUCION"
    PROYECTOS = "PROYECTOS"


#: Los tres archivos obligatorios de un corte (HU-01 / CA-3, CA-4).
ARCHIVOS_OBLIGATORIOS: tuple[TipoArchivoFuente, ...] = (
    TipoArchivoFuente.PDT,
    TipoArchivoFuente.EJECUCION,
    TipoArchivoFuente.PROYECTOS,
)

#: HU-01/CA-5, CA-7: archivos que se reutilizan automáticamente del último
#: corte REGISTRADO de la MISMA vigencia (D-05). EJECUCION queda deliberadamente
#: fuera de esta tupla: CA-7 exige que se solicite siempre, en todo corte.
#:
#: SUPUESTO (D-04 del equipo, PENDIENTE DE RATIFICAR CON LA CLIENTA): "el
#: archivo del municipio" de CA-5/CA-6 = la plantilla de proyectos BPIN, por
#: ser la única de las tres que el municipio diligencia a mano. Si en realidad
#: se refiere a un cuarto archivo no modelado, esta tupla y la tabla de fuentes
#: deben revisarse.
ARCHIVOS_REUTILIZABLES: tuple[TipoArchivoFuente, ...] = (
    TipoArchivoFuente.PDT,
    TipoArchivoFuente.PROYECTOS,
)


@dataclass(slots=True)
class ArchivoFuente:
    tipo: TipoArchivoFuente
    nombre_archivo: str
    filas_reconocidas: int = 0
    reutilizado: bool = False
    corte_origen_id: uuid.UUID | None = None


@dataclass(slots=True)
class Corte:
    """Agrupación de fuentes y resultados de un momento de seguimiento."""

    vigencia: int
    fecha_corte: date
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    estado: EstadoCorte = EstadoCorte.BORRADOR
    archivos: dict[TipoArchivoFuente, ArchivoFuente] = field(default_factory=dict)

    @staticmethod
    def validar_fecha(fecha_corte: date, hoy: date) -> None:
        """HU-01/CA-2: no se aceptan cortes con fecha futura."""
        if fecha_corte > hoy:
            raise ReglaDeNegocioViolada(
                f"La fecha de corte ({fecha_corte.isoformat()}) no puede ser "
                f"posterior a hoy ({hoy.isoformat()}).",
                detalles={
                    "fecha_corte": fecha_corte.isoformat(),
                    "hoy": hoy.isoformat(),
                },
            )

    def archivos_faltantes(self) -> list[TipoArchivoFuente]:
        """Tipos obligatorios que aún no están cargados ni reutilizados."""
        return [tipo for tipo in ARCHIVOS_OBLIGATORIOS if tipo not in self.archivos]

    def esta_completo(self) -> bool:
        return not self.archivos_faltantes()

    def registrar(self) -> None:
        """HU-01/CA-3 y CA-4: transición BORRADOR -> REGISTRADO.

        Si falta algún archivo obligatorio, la operación se rechaza indicando
        CUÁL falta y el corte NO cambia de estado. Un mensaje genérico incumple
        el CA.
        """
        raise NotImplementedError("[HU-01][BE-05] Transición a REGISTRADO")

    def puede_reutilizar(self, tipo: TipoArchivoFuente) -> bool:
        """HU-01/CA-5, CA-7: solo PDT y PROYECTOS son reutilizables.

        EJECUCION siempre devuelve False: CA-7 exige que se solicite en cada
        corte, sin excepción.
        """
        return tipo in ARCHIVOS_REUTILIZABLES
