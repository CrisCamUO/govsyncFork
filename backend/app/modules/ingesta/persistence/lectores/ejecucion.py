"""Lector del archivo presupuestal: pestañas de ejecución y contratación.

CAPA: Persistencia
TARJETAS: [HU-03][BE-01] lector de las dos pestañas
          [HU-03][BE-02] preservación de ceros a la izquierda
          [HU-03][BE-04] validación de presencia de ambas pestañas
          [HU-03][BE-05] detección de archivo que no corresponde
CUBRE: HU-03 / CA-2, CA-4, CA-5, CA-7

=============================================================================
ANATOMÍA DEL ARCHIVO REAL (ver docs/DATOS.md)
=============================================================================
UN archivo, DOS pestañas, procesadas como conjuntos independientes (CA-2). NO
se piden por separado.

La pestaña de ejecución se llama 'Formato Resumido Ejecucion Gast' (Excel
trunca a 31 caracteres), no 'EJECUCION'. La de contratación sí es
'CONTRATACION'.

EJECUCIÓN — 485 filas:
  - UltimoNivel: 374 hojas / 111 SUBTOTALES jerárquicos. Los subtotales YA
    contienen la suma de sus hojas. Sumar sin filtrar DUPLICA el dinero.
  - CodigoRubroNivel: 484 únicos de 485 (1 duplicado, 0 entre las hojas). Es
    la llave utilizable.
  - CodigoRubroCcpet: 343 únicos de 485 (142 duplicados). NO sirve como llave.
  - CodigoBpin: poblado en 3 de 485 filas. El BPIN confiable NO está aquí.

CONTRATACIÓN — 319 filas:
  - 270 contratos únicos: un contrato tiene 1..N registros presupuestales.
    Modelar como DOS entidades para no duplicar el contrato ni inflar sus
    valores al sumar.
  - 'Codigo Bpin' poblado en 200 de 319 (63%). Un tercio no cruzará, por
    diseño de los datos de origen. No es un defecto del sistema.
  - 'CodigoRubro': los 92 valores distintos coinciden TODOS con
    CodigoRubroNivel de ejecución. Cobertura 100%.
  - 45 filas repiten (NumeroContrato, Numero Registro) con rubros distintos.

=============================================================================
CRITERIOS
=============================================================================
CA-2: procesar ambas pestañas como conjuntos independientes.
CA-4: si falta 'CONTRATACION' o 'EJECUCION', rechazar señalando CUÁL falta.
CA-5: si el archivo no es el presupuestal (p. ej. suben el PDT), rechazar.
CA-7: conservar el código de indicador con sus ceros a la izquierda.
"""

from __future__ import annotations

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun

ALIAS_EJECUCION = (
    "EJECUCION",
    "Formato Resumido Ejecucion Gast",
    "Formato Resumido Ejecucion Gastos",
)
ALIAS_CONTRATACION = ("CONTRATACION", "CONTRATACIÓN")

# TODO [HU-03][BE-03] Las dos grafías del código de indicador son EL MISMO
# dato y se resuelven por alias, sin duplicar columnas:
#     "cod_indicador_producto": ("CodigoIndicadorCcpet", "Cod Indicador Ccpet")
OBLIGATORIAS_EJECUCION: dict[str, tuple[str, ...]] = {}
OBLIGATORIAS_CONTRATACION: dict[str, tuple[str, ...]] = {}


def resolver_hojas(contenido: bytes, nombre_archivo: str) -> tuple[str | None, str | None]:
    """HU-03/CA-2: localiza (hoja_ejecucion, hoja_contratacion), cada una de
    forma independiente — "conjuntos independientes, sin exigir carga por
    separado". Ninguna búsqueda depende de que la otra tenga éxito.

    `None` en cualquiera de las dos posiciones significa "no encontrada";
    decidir qué hacer con eso (CA-4: rechazar nombrando cuál falta) es de
    `leer()`, [HU-03][BE-04].
    """
    libro = _comun.abrir_libro(contenido, nombre_archivo)
    try:
        nombres = libro.sheetnames
        return (
            _comun.resolver_hoja(nombres, ALIAS_EJECUCION),
            _comun.resolver_hoja(nombres, ALIAS_CONTRATACION),
        )
    finally:
        libro.close()


class LectorEjecucion(LectorArchivoFuente):
    tipo = TipoArchivo.EJECUCION

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        raise NotImplementedError("[HU-03][BE-01]")
