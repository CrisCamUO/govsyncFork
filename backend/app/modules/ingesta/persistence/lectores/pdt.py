"""Lector del Plan Indicativo (PDT) exportado de SisPT.

CAPA: Persistencia
TARJETAS: [HU-02][BE-01] localización de pestaña
          [HU-02][BE-02] validación de columnas mínimas
          [HU-02][BE-03] detección de archivo que no corresponde
CUBRE: HU-02 / CA-2, CA-3, CA-4, CA-6

=============================================================================
ANATOMÍA DEL ARCHIVO REAL (ver docs/DATOS.md)
=============================================================================
6 pestañas. SOLO 'Plan indicativo - Productos' contiene metas (CA-2). Las otras
cinco ('Líneas estratégicas', 'Indicadores de resultado', 'Plan indicativo SGR
- Productos', 'Iniciativas SGR', 'Iniciativas PATR') NO se interpretan.

Encabezado en la FILA 2. 86 columnas, 144 filas de metas.

Columnas que importan:
  - 'Código de indicador de producto (MGA)'   <- LA LLAVE (9 dígitos)
  - 'Producto (MGA)', 'Indicador de Producto(MGA)'
  - 'Principal'                                <- Sí=135 / No=9
  - 'Programación del producto bien o servicio <año>'
  - 'Total <año>'

'Código de indicador de producto (SisPT)' contiene 'IP-63' y NO es la llave.

=============================================================================
CRITERIOS
=============================================================================
CA-2: reconocer específicamente la pestaña de productos.
CA-3: verificar columnas mínimas (código de indicador, meta programada por
      vigencia, marca "Principal"). Si falta alguna -> rechazo TOTAL indicando
      cuál.
CA-4: si el archivo no es un PDT (p. ej. suben el de ejecución), rechazar
      indicándolo, SIN intentar adivinar el contenido.
CA-6: aporta a la matriz el código de indicador y el nombre del producto.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun
from app.shared.codigos import CodigoIndicadorProducto
from app.shared.errors import ArchivoInvalido

ALIAS_HOJA = ("Plan indicativo - Productos", "Plan indicativo Productos")

# HU-02/CA-6: columnas que aportan a la matriz pero NO son obligatorias (si
# faltan, no se rechaza el archivo — solo quedan como None en cada meta). El
# fixture real muestra que "Indicador de Producto(MGA)" trae en realidad la
# unidad de medida ("Kilómetros", "Número"), no un segundo código.
OPCIONALES: dict[str, tuple[str, ...]] = {
    "nombre_producto": ("Producto (MGA)",),
    "unidad_medida": ("Indicador de Producto(MGA)",),
}


def _meta_a_decimal(crudo: object) -> Decimal | None:
    """Convierte la celda de meta programada a Decimal.

    A diferencia de `_comun.numero` (pensado para montos con formato de pesos
    colombiano, con `$` y separadores de miles), el PDT programa metas como
    números planos (ver `tests/fabricas.py::construir_pdt`) — no hace falta
    ese formato aquí. Devuelve None si la celda no es un número reconocible;
    quien llama decide si eso amerita una advertencia.
    """
    texto = _comun.texto(crudo)
    if texto is None:
        return None
    try:
        return Decimal(texto.replace(" ", ""))
    except InvalidOperation:
        return None


def _es_principal(crudo: object) -> bool | None:
    """Interpreta la marca "Principal" (Sí/No). None si no es reconocible.

    Reutiliza `normalizar_encabezado` para la comparación (tildes,
    mayúsculas, espacios) aunque el dato no sea un encabezado: el propósito
    aquí también es comparar contra un valor esperado, no mostrarlo.
    """
    normalizado = _comun.normalizar_encabezado(crudo)
    if normalizado == "si":
        return True
    if normalizado == "no":
        return False
    return None


def resolver_hoja_pdt(contenido: bytes, nombre_archivo: str) -> str:
    """HU-02/CA-2 (tercer punto de la tarjeta): localiza la pestaña de metas.

    A diferencia de `_comun.resolver_hoja` (que devuelve `None` para permitir
    búsquedas independientes, como en `[HU-03][BE-01]` con Ejecución y
    Contratación), el PDT tiene UNA sola pestaña obligatoria: su ausencia
    siempre es un rechazo, con excepción que identifica el problema — tal
    como pide el texto de la tarjeta, no solo su docstring de resumen.
    """
    libro = _comun.abrir_libro(contenido, nombre_archivo)
    try:
        hoja = _comun.resolver_hoja(libro.sheetnames, ALIAS_HOJA)
    finally:
        libro.close()

    if hoja is None:
        raise ArchivoInvalido(
            f"«{nombre_archivo}» no contiene la pestaña «{ALIAS_HOJA[0]}» del Plan Indicativo.",
            detalles={"motivo": "hoja_no_encontrada", "hojas_esperadas": list(ALIAS_HOJA)},
        )
    return hoja


# HU-02/CA-3: columnas mínimas cuyo nombre NO cambia entre vigencias. La
# tercera columna que exige el CA ("meta programada por vigencia") no puede
# vivir aquí como alias fijo — ver alias_columna_programacion() abajo.
OBLIGATORIAS: dict[str, tuple[str, ...]] = {
    "codigo_indicador": ("Código de indicador de producto (MGA)",),
    "principal": ("Principal",),
}


def alias_columna_programacion(vigencia: int) -> str:
    """Nombre real de la columna de meta programada para `vigencia`.

    [HU-02][BE-03] debe fusionar esta columna a OBLIGATORIAS antes de llamar
    a `exigir_columnas`, porque el nombre depende de un valor que solo se
    conoce en tiempo de ejecución (la vigencia del corte):

        obligatorias = {
            **OBLIGATORIAS,
            "programacion_anio": (alias_columna_programacion(vigencia),),
        }
    """
    return f"Programación del producto bien o servicio {vigencia}"


class LectorPDT(LectorArchivoFuente):
    tipo = TipoArchivo.PDT

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        """Extrae y transforma el Plan Indicativo (HU-02/CA-2, CA-3, CA-4, CA-6).

        CA-4 no tiene una regla propia: si el archivo no trae la pestaña de
        metas, `resolver_hoja_pdt` ya lo rechaza (CA-2) — no hace falta una
        heurística aparte para "adivinar" que el archivo no corresponde, que
        es justo lo que CA-4 pide evitar.

        Una fila con código de indicador inválido o marca "Principal" no
        reconocible se descarta individualmente (con advertencia), en vez de
        rechazar el archivo completo: a diferencia de una columna faltante
        (CA-3, error estructural), un dato de fila es un problema de esa fila.
        """
        hoja = resolver_hoja_pdt(contenido, nombre_archivo)

        obligatorias = {
            **OBLIGATORIAS,
            "programacion_anio": (alias_columna_programacion(vigencia),),
        }
        columnas = {**obligatorias, **OPCIONALES}

        # Ancla para encontrar la fila de encabezado: SOLO el código de
        # indicador (columna estable, nunca ambigua con la fila de título de
        # sección). Si se exigieran aquí las 3 obligatorias, una columna
        # faltante haría fallar la búsqueda del encabezado ANTES de llegar a
        # `exigir_columnas`, con un mensaje que lista todas las esperadas en
        # vez de nombrar solo la que falta (CA-3 exige nombrar la que falta).
        ancla_encabezado = OBLIGATORIAS["codigo_indicador"]
        fila_encabezado = _comun.localizar_fila_encabezado(contenido, hoja, ancla_encabezado)
        df = _comun.leer_hoja(contenido, hoja, fila_encabezado)

        mapeo = _comun.mapear_columnas(df, columnas)
        _comun.exigir_columnas(mapeo, obligatorias, nombre_archivo, hoja)

        metas: list[dict[str, Any]] = []
        advertencias: list[str] = []
        for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
            crudo_codigo = fila[mapeo["codigo_indicador"]]
            codigo = CodigoIndicadorProducto.desde_crudo(crudo_codigo)
            if codigo is None:
                advertencias.append(
                    f"Fila {posicion}: código de indicador inválido "
                    f"({crudo_codigo!r}); se descarta."
                )
                continue

            principal = _es_principal(fila[mapeo["principal"]])
            if principal is None:
                advertencias.append(
                    f"Fila {posicion} (código {codigo.valor}): marca «Principal» no reconocible "
                    f"({fila[mapeo['principal']]!r}); se descarta."
                )
                continue

            meta_cuatrienio = _meta_a_decimal(fila[mapeo["programacion_anio"]])
            if meta_cuatrienio is None:
                advertencias.append(
                    f"Fila {posicion} (código {codigo.valor}): meta programada no es un número "
                    f"reconocible ({fila[mapeo['programacion_anio']]!r})."
                )

            metas.append(
                {
                    "cod_indicador_producto": codigo.valor,
                    "principal": principal,
                    "meta_cuatrienio": meta_cuatrienio,
                    "nombre_producto": (
                        _comun.texto(fila[mapeo["nombre_producto"]])
                        if "nombre_producto" in mapeo
                        else None
                    ),
                    "unidad_medida": (
                        _comun.texto(fila[mapeo["unidad_medida"]])
                        if "unidad_medida" in mapeo
                        else None
                    ),
                }
            )

        return ResultadoLectura(
            tipo=TipoArchivo.PDT,
            filas={"metas": metas},
            conteos={"metas": len(metas)},
            advertencias=advertencias,
        )
