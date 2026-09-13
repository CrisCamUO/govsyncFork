"""Pruebas del validador transversal de archivos (capa Aplicación).

TARJETA: [SEC-03]
CUBRE: firma real vs. extensión, tamaño previo a la lectura, sanitización del
nombre (path traversal, byte nulo), rechazo de .xlsm (por extensión y por
inspección del ZIP), archivo vacío / corrupto / que no es un libro.

Los libros se construyen en memoria: el .xlsx válido con openpyxl (igual que
tests/fabricas.py) y las variantes maliciosas manipulando el ZIP a mano.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from openpyxl import Workbook

from app.modules.cortes.application.validacion_archivos import validar_archivo_cargado
from app.shared.errors import ArchivoInvalido


def _xlsx_valido() -> bytes:
    libro = Workbook()
    libro.active["A1"] = "hola"
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _con_entrada_extra(contenido: bytes, nombre: str, datos: bytes = b"x") -> bytes:
    """Reescribe el ZIP añadiendo una entrada (p. ej. xl/vbaProject.bin)."""
    destino = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(contenido)) as entrada,
        zipfile.ZipFile(destino, "w") as salida,
    ):
        for item in entrada.infolist():
            salida.writestr(item, entrada.read(item.filename))
        salida.writestr(nombre, datos)
    return destino.getvalue()


def _zip_con(entradas: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)
    return buffer.getvalue()


def _motivo(exc_info: pytest.ExceptionInfo[ArchivoInvalido]) -> str:
    return exc_info.value.detalles["motivo"]


def test_xlsx_valido_devuelve_el_nombre_saneado() -> None:
    assert validar_archivo_cargado(_xlsx_valido(), "Plan Indicativo.xlsx") == "Plan Indicativo.xlsx"


def test_sanitiza_el_path_traversal_y_conserva_el_basename() -> None:
    assert validar_archivo_cargado(_xlsx_valido(), "../../etc/pdt.xlsx") == "pdt.xlsx"


def test_rechaza_nombre_con_byte_nulo() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_xlsx_valido(), "pdt\x00.xlsx")
    assert _motivo(exc) == "nombre_invalido"


def test_rechaza_nombre_vacio() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_xlsx_valido(), "   ")
    assert _motivo(exc) == "nombre_vacio"


def test_rechaza_extension_no_permitida() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_xlsx_valido(), "datos.txt")
    assert _motivo(exc) == "extension_no_permitida"


def test_rechaza_xlsm_por_extension() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_xlsx_valido(), "macro.xlsm")
    assert _motivo(exc) == "extension_no_permitida"


def test_rechaza_xlsm_renombrado_a_xlsx_por_vbaproject() -> None:
    contenido = _con_entrada_extra(_xlsx_valido(), "xl/vbaProject.bin")
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(contenido, "disfrazado.xlsx")
    assert _motivo(exc) == "libro_con_macros"


def test_rechaza_archivo_vacio() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(b"", "pdt.xlsx")
    assert _motivo(exc) == "archivo_vacio"


def test_rechaza_tamano_excedido_antes_de_inspeccionar() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_xlsx_valido(), "pdt.xlsx", tamano_max=32)
    assert _motivo(exc) == "tamano_excedido"


def test_rechaza_contenido_que_no_es_zip() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(b"esto no es un xlsx", "pdt.xlsx")
    assert _motivo(exc) == "firma_invalida"


def test_rechaza_zip_corrupto() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(b"PK\x03\x04" + b"\x00" * 200, "pdt.xlsx")
    assert _motivo(exc) == "zip_corrupto"


def test_rechaza_zip_con_crc_danado() -> None:
    # Directorio central intacto (abre bien) pero un byte de datos alterado:
    # una carga truncada o manipulada en tránsito.
    bueno = _zip_con(
        {
            "[Content_Types].xml": b"<Types/>",
            "xl/worksheets/sheet1.xml": b"<worksheet>" + b"Z" * 64 + b"</worksheet>",
        }
    )
    i = bueno.index(b"Z" * 64)
    malo = bueno[:i] + b"Q" + bueno[i + 1 :]
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(malo, "pdt.xlsx")
    assert _motivo(exc) == "zip_corrupto"


def test_rechaza_zip_sin_estructura_de_libro() -> None:
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(_zip_con({"cualquier.txt": b"x"}), "pdt.xlsx")
    assert _motivo(exc) == "estructura_invalida"


def test_rechaza_libro_sin_hojas() -> None:
    contenido = _zip_con({"[Content_Types].xml": b"<Types/>"})
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(contenido, "pdt.xlsx")
    assert _motivo(exc) == "sin_hojas"


def test_rechaza_libro_con_content_types_que_declara_macros() -> None:
    contenido = _zip_con(
        {
            "[Content_Types].xml": b"<Types><Override ContentType='...macroEnabled.12'/></Types>",
            "xl/worksheets/sheet1.xml": b"<worksheet/>",
        }
    )
    with pytest.raises(ArchivoInvalido) as exc:
        validar_archivo_cargado(contenido, "pdt.xlsx")
    assert _motivo(exc) == "libro_con_macros"
