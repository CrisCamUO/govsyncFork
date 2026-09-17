"""Punto de entrada de la aplicación GovSync.

Monolito modular: un solo despliegue, módulos con frontera explícita y cinco
capas lógicas (API, Aplicación, Dominio, Persistencia, Base de datos).

Este archivo arranca tal cual está. Cada integrante REGISTRA SU ROUTER aquí
cuando su tarjeta [FE-01] esté lista; hasta entonces solo responde /salud.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errores import registrar_manejadores
from app.modules.cortes.api.router import router as router_cortes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def crear_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GovSync API",
        version="0.1.0",
        description="Seguimiento al Plan de Desarrollo Territorial · Santa Rosa, Cauca",
    )

    # CORS restringido a los orígenes declarados; nunca '*' con credenciales.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    registrar_manejadores(app)

    app.include_router(router_cortes, prefix="/api/v1")
    # TODO [HU-07][FE-01] app.include_router(router_trazabilidad, prefix="/api/v1")

    @app.get("/health", tags=["Operación"], summary="Verificación de estado para despliegue")
    def health() -> dict[str, str]:
        """[DEV-07]: ruta real exigida por la tarjeta. No depende de la BD,
        para responder incluso si la migración inicial sigue rota."""
        return {"estado": "ok"}

    @app.get("/api/v1/salud", tags=["Operación"], summary="Verificación de estado")
    def salud() -> dict[str, str]:
        """Alias de /health, mantenido bajo el prefijo /api/v1 por
        compatibilidad. /health es la fuente de verdad (ver docstring de
        health() y PLANDETRABAJO.md, nota de la tarjeta 6.5)."""
        return health()

    return app


app = crear_app()
