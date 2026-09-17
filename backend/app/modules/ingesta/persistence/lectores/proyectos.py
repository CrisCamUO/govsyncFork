"""Lector de la plantilla de proyectos BPIN del municipio.

CAPA: Persistencia
TARJETAS: [HU-04][BE-01] almacenamiento tal cual
          [HU-04][BE-02] extracción de columnas necesarias
          [HU-04][BE-03] separación de celdas multivalor
CUBRE: HU-04 / CA-2, CA-3, CA-4, CA-5

=============================================================================
ESTE LECTOR ES DELIBERADAMENTE MÁS PERMISIVO QUE LOS OTROS DOS
=============================================================================
HU-04/CA-2 dice que el archivo se almacena «tal cual» lo entrega el municipio,
«incluso si su estructura interna no está completamente estandarizada», y
CA-3 acota la extracción a las columnas necesarias «sin validar el resto».

La tarjeta lleva la etiqueta "Pendiente de estandarización de fuente".

NO rechazar por columnas monetarias ausentes ni por filas incompletas: solo
exigir poder ubicar BPIN e indicador de producto.

=============================================================================
ANATOMÍA DEL ARCHIVO REAL (ver docs/DATOS.md)
=============================================================================
- 1 pestaña nombrada con el año ('2026'). No hay nombre estándar: probar cada
  hoja y tomar la primera que tenga las columnas requeridas.
- 134 filas, 48 columnas, 221 RANGOS DE CELDAS COMBINADAS. Una fila de
  proyecto va seguida de filas que solo traen datos de contrato.
- 38 proyectos reales entre las 134 filas.
- Uno de los 38 BPIN no cumple el formato de 15 dígitos: conservarlo sin
  normalizar en vez de rechazar el archivo (CA-2).
- 'Indicador de producto' es MULTIVALOR dentro de una celda:

      459903100
      Entidades, organismos y dependencias asistidos técnicamente
      $ 1.218.264.452

      459902300
      Sistema de Gestión implementado
      $230.000.000,00

  Un split("\\n") produciría nombres y montos como si fueran códigos.
  67 códigos únicos, todos presentes en el PDT.

=============================================================================
OJO CON [HU-04][FE-03]
=============================================================================
La pantalla de vista previa necesita saber qué se DESCARTÓ y POR QUÉ, no solo
qué se extrajo. Este lector debe devolver también los fragmentos descartados
con su motivo: «los descartes son la información más valiosa de esa pantalla».
Diseñar ResultadoLectura.filas para llevar esa información desde el principio.
"""

from __future__ import annotations

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun
from app.shared.errors import ArchivoInvalido

OBLIGATORIAS: dict[str, tuple[str, ...]] = {
    "bpin": ("Código BPIN", "Codigo BPIN", "BPIN"),
    "indicador_producto_raw": ("Indicador de producto", "Indicador producto"),
}

#: Filas a inspeccionar por hoja antes de descartarla, igual que
#: `_comun.localizar_fila_encabezado`.
_MAX_FILAS_ENCABEZADO = 8


def resolver_hoja_proyectos(contenido: bytes, nombre_archivo: str) -> tuple[str, int]:
    """HU-04/CA-2: prueba cada hoja del libro y devuelve la primera que tenga,
    en alguna de sus primeras filas, TODAS las columnas obligatorias por
    alias.

    A diferencia de `resolver_hoja_pdt`/`resolver_hojas`, aquí no hay nombre
    de hoja que buscar: el municipio la nombra con el año, sin convención
    fija (docstring del módulo). Por eso se busca por contenido, no por
    nombre, y se recorren TODAS las hojas del libro en vez de una lista de
    alias de nombre.

    Devuelve `(hoja, fila_encabezado)` para no recorrer las filas una segunda
    vez al leer la hoja completa después.
    """
    libro = _comun.abrir_libro(contenido, nombre_archivo)
    try:
        grupos_alias = [
            {_comun.normalizar_encabezado(a) for a in alias} for alias in OBLIGATORIAS.values()
        ]
        for nombre_hoja in libro.sheetnames:
            filas = libro[nombre_hoja].iter_rows(max_row=_MAX_FILAS_ENCABEZADO, values_only=True)
            for indice, fila in enumerate(filas):
                valores_norm = {_comun.normalizar_encabezado(v) for v in fila if v is not None}
                if all(grupo & valores_norm for grupo in grupos_alias):
                    return nombre_hoja, indice
    finally:
        libro.close()

    columnas_esperadas = [alias[0] for alias in OBLIGATORIAS.values()]
    raise ArchivoInvalido(
        f"«{nombre_archivo}» no tiene ninguna hoja con las columnas obligatorias: "
        f"{', '.join(columnas_esperadas)}.",
        detalles={"motivo": "hoja_no_encontrada", "columnas_esperadas": columnas_esperadas},
    )


class LectorProyectos(LectorArchivoFuente):
    tipo = TipoArchivo.PROYECTOS

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        raise NotImplementedError("[HU-04][BE-01]")
