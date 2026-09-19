"""Traducción centralizada de errores de dominio a respuestas HTTP.

Capa: API. Es el ÚNICO lugar que conoce el mapa error de negocio -> código HTTP.
Los casos de uso lanzan excepciones de dominio y no saben nada de HTTP.

Seguridad (OWASP A05 — mala configuración de seguridad): un error no previsto
nunca devuelve la traza ni el mensaje interno al cliente; se registra en el log
del servidor y se responde con un mensaje genérico.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.shared.errors import (
    ArchivoInvalido,
    CredencialesInvalidas,
    GovSyncError,
    OperacionNoPermitida,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)

_log = logging.getLogger("govsync")

_MAPA_HTTP: dict[type[GovSyncError], int] = {
    CredencialesInvalidas: status.HTTP_401_UNAUTHORIZED,
    OperacionNoPermitida: status.HTTP_409_CONFLICT,
    RecursoNoEncontrado: status.HTTP_404_NOT_FOUND,
    ReglaDeNegocioViolada: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ArchivoInvalido: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(GovSyncError)
    async def _manejar_error_dominio(_: Request, exc: GovSyncError) -> JSONResponse:
        codigo_http = _MAPA_HTTP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=codigo_http,
            content={
                "codigo": exc.codigo,
                "mensaje": exc.mensaje,
                "detalles": exc.detalles,
            },
        )

    @app.exception_handler(Exception)
    async def _manejar_error_no_previsto(request: Request, exc: Exception) -> JSONResponse:
        _log.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "codigo": "error_interno",
                "mensaje": "Ocurrió un error inesperado procesando la solicitud.",
                "detalles": {},
            },
        )
