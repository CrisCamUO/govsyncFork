"""Validador transversal de archivos cargados.

CAPA: Aplicación
TARJETA: [SEC-03] Validación transversal de archivos cargados
BLOQUEA: HU-02, HU-03, HU-04

De la tarjeta: «La validación de archivos es una responsabilidad única en la
capa de Aplicación: no vive en la API, no se repite en cada caso de uso.»

Esta es la PUERTA GENÉRICA: se aplica una sola vez, antes de que cualquier
lector (estrategia por tipo) toque el contenido. Lo específico de cada fuente
—qué pestaña, qué columnas— es de los lectores (HU-02/03/04), no de aquí.

=============================================================================
CHECKLIST DE [SEC-03] Y DÓNDE SE CUBRE
=============================================================================
1. Extensión declarada vs. firma real del contenido      -> aquí
2. Tamaño máximo antes de leer en memoria                 -> el corte por
   streaming es del router (único punto donde el stream del UploadFile aún no
   está en RAM); aquí se revalida `len(contenido)` como defensa en profundidad.
3. Sanitización del nombre de archivo (path traversal)    -> aquí
4. Rechazo de libros con macros (.xlsm)                   -> aquí (se inspecciona
   el ZIP: un .xlsm renombrado a .xlsx no engaña este control).
5. Las hojas obligatorias existen antes de procesar       -> aquí se comprueba
   la estructura mínima (es un .xlsx legible con al menos una hoja); el nombre
   concreto de cada pestaña lo resuelve el lector con su lógica de alias.

RESTRICCIÓN: aquí NO se abre el contenido con pandas ni openpyxl (eso es la
etapa Extract, en persistence/). Solo `zipfile` + `io` de la stdlib: valida la
envoltura sin pagar el parseo ni arrastrar dependencias de sistema (libmagic).
"""

from __future__ import annotations

import io
import zipfile

from app.shared.errors import ArchivoInvalido

#: Firma de un ZIP con contenido (todo .xlsx lo es). La variante "PK\x05\x06"
#: corresponde a un ZIP vacío; exigir esta descarta también libros truncados.
FIRMA_ZIP = b"PK\x03\x04"

#: Ruta interna que solo aparece en libros con proyecto de macros VBA.
_ENTRADA_VBA = "xl/vbaProject.bin"

#: Nombre de la pieza de metadatos obligatoria de todo libro OOXML.
_CONTENT_TYPES = "[Content_Types].xml"

#: Marca del tipo de contenido de un libro con macros dentro de
#: [Content_Types].xml: atrapa el .xlsm cuyo vbaProject.bin fue borrado pero
#: cuyo Content_Types quedó declarándolo.
_MARCA_MACROS = b"macroEnabled"

#: Tope por defecto. Coincide con `Settings.max_upload_bytes`; el llamador
#: (`cargar_archivo`) debería pasar `get_settings().max_upload_bytes` explícito.
TAMANO_MAX_POR_DEFECTO = 25 * 1024 * 1024

_EXTENSIONES_POR_DEFECTO = frozenset({".xlsx"})


def sanitizar_nombre(nombre: str) -> str:
    """Devuelve solo el nombre base, sin componentes de ruta ni caracteres de
    control. Lanza `ArchivoInvalido` si el nombre es inservible.

    El nombre no se usa como identificador funcional (lo dice la ESPEC), pero se
    guarda y puede registrarse o mostrarse: un `../../etc/passwd` o un byte nulo
    no deben llegar a un log ni a un `open()`.
    """
    if not isinstance(nombre, str) or not nombre.strip():
        raise ArchivoInvalido(
            "El nombre del archivo está vacío.",
            detalles={"motivo": "nombre_vacio"},
        )
    base = nombre.replace("\\", "/").split("/")[-1].strip()
    if not base or base in {".", ".."} or any(ord(c) < 32 for c in base):
        raise ArchivoInvalido(
            f"El nombre del archivo no es válido: {nombre!r}.",
            detalles={"motivo": "nombre_invalido"},
        )
    return base


def _verificar_extension(nombre: str, extensiones_ok: frozenset[str]) -> None:
    punto = nombre.rfind(".")
    extension = nombre[punto:].lower() if punto > 0 else ""
    if extension not in extensiones_ok:
        permitidas = ", ".join(sorted(extensiones_ok))
        raise ArchivoInvalido(
            f"La extensión {extension or '(ninguna)'} no está permitida. Se aceptan: {permitidas}.",
            detalles={"motivo": "extension_no_permitida", "extension": extension},
        )


def _verificar_tamano(contenido: bytes, tamano_max: int) -> None:
    if not contenido:
        raise ArchivoInvalido(
            "El archivo está vacío.",
            detalles={"motivo": "archivo_vacio"},
        )
    if len(contenido) > tamano_max:
        raise ArchivoInvalido(
            f"El archivo pesa {len(contenido)} bytes; el máximo es {tamano_max}.",
            detalles={
                "motivo": "tamano_excedido",
                "tamano": len(contenido),
                "tamano_max": tamano_max,
            },
        )


def _verificar_estructura_y_macros(contenido: bytes) -> None:
    if not contenido.startswith(FIRMA_ZIP):
        raise ArchivoInvalido(
            "El contenido no es un archivo .xlsx (le falta la firma de un ZIP).",
            detalles={"motivo": "firma_invalida"},
        )
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            nombres = set(libro.namelist())
            if libro.testzip() is not None:
                raise ArchivoInvalido(
                    "El archivo .xlsx está corrupto.",
                    detalles={"motivo": "zip_corrupto"},
                )
            if _CONTENT_TYPES not in nombres:
                raise ArchivoInvalido(
                    "El archivo no tiene la estructura de un libro de Excel.",
                    detalles={"motivo": "estructura_invalida"},
                )
            if not any(n.startswith("xl/worksheets/") and n.endswith(".xml") for n in nombres):
                raise ArchivoInvalido(
                    "El libro no contiene ninguna hoja.",
                    detalles={"motivo": "sin_hojas"},
                )
            if _ENTRADA_VBA in nombres or _MARCA_MACROS in libro.read(_CONTENT_TYPES):
                raise ArchivoInvalido(
                    "El archivo contiene macros (.xlsm). Solo se aceptan libros sin macros.",
                    detalles={"motivo": "libro_con_macros"},
                )
    except zipfile.BadZipFile as exc:
        raise ArchivoInvalido(
            "El archivo .xlsx está corrupto o no es un ZIP válido.",
            detalles={"motivo": "zip_corrupto"},
        ) from exc


def validar_archivo_cargado(
    contenido: bytes,
    nombre_archivo: str,
    *,
    tamano_max: int = TAMANO_MAX_POR_DEFECTO,
    extensiones_ok: frozenset[str] = _EXTENSIONES_POR_DEFECTO,
) -> str:
    """Puerta única de [SEC-03]. Devuelve el nombre de archivo saneado.

    Lanza `ArchivoInvalido` (-> HTTP 422) ante cualquier incumplimiento, ANTES
    de que el pipeline ETL lea el contenido. El rechazo es total: nunca datos
    parciales (HU-02/CA-3).
    """
    nombre = sanitizar_nombre(nombre_archivo)
    _verificar_extension(nombre, extensiones_ok)
    _verificar_tamano(contenido, tamano_max)
    _verificar_estructura_y_macros(contenido)
    return nombre
