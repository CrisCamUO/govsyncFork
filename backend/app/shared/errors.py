"""Excepciones de dominio compartidas.

Capa: dominio. Sin dependencias de framework — la capa API las traduce a
códigos HTTP en un único manejador (app/core/exception_handlers.py).
"""

from __future__ import annotations


class GovSyncError(Exception):
    """Raíz de todos los errores de negocio de GovSync."""

    codigo = "govsync_error"

    def __init__(self, mensaje: str, detalles: dict | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class ReglaDeNegocioViolada(GovSyncError):
    codigo = "regla_de_negocio_violada"


class RecursoNoEncontrado(GovSyncError):
    codigo = "recurso_no_encontrado"


class OperacionNoPermitida(GovSyncError):
    codigo = "operacion_no_permitida"


class CredencialesInvalidas(GovSyncError):
    codigo = "credenciales_invalidas"


class ArchivoInvalido(GovSyncError):
    """El archivo cargado no corresponde al formato esperado.

    Cubre HU02-CA02, HU02-CA04, HU03-CA04 y HU03-CA05: el rechazo es total,
    nunca parcial, y el mensaje debe indicar QUÉ falta.
    """

    codigo = "archivo_invalido"


class TipoArchivoNoDisponible(GovSyncError):
    """La carga de este TipoArchivoFuente aún no está implementada.

    Guard temporal de [HU-02][FE-01]: hoy solo PDT cierra completo en
    ServicioCortes.cargar_archivo(). Retirar esta excepción (y su guard en
    cortes/api/router.py) cuando RepositorioDatosCorteSQL.reemplazar_presupuesto
    ([HU-03][BE-06]) y LectorProyectos.leer ([HU-04][BE-01]) dejen de lanzar
    NotImplementedError. Sin este guard, ambos casos producían un 500
    genérico sin mapear.
    """

    codigo = "tipo_archivo_no_implementado"
