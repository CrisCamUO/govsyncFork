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

OBLIGATORIAS: dict[str, tuple[str, ...]] = {
    "bpin": ("Código BPIN", "Codigo BPIN", "BPIN"),
    "indicador_producto_raw": ("Indicador de producto", "Indicador producto"),
}


class LectorProyectos(LectorArchivoFuente):
    tipo = TipoArchivo.PROYECTOS

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        raise NotImplementedError("[HU-04][BE-01]")
