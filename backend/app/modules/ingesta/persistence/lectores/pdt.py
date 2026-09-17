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

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun
from app.shared.errors import ArchivoInvalido

ALIAS_HOJA = ("Plan indicativo - Productos", "Plan indicativo Productos")


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
        raise NotImplementedError("[HU-02][BE-03]")
