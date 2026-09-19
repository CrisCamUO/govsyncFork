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

FUERA DE ALCANCE DE [HU-04][BE-01] (registrado, no bloqueante): la
implementación actual de `leer()` solo agrega advertencias de texto
(`ResultadoLectura.advertencias`), igual que `pdt.py`/`ejecucion.py`. NO
construye la estructura granular de "fragmentos descartados con motivo" que
pide FE-03 — eso es trabajo de la pantalla de vista previa (frontend), y no
hay ninguna CA de BE-01/02/03 que exija ese formato en el backend todavía.
Si FE-03 lo necesita, es un cambio de forma en `ResultadoLectura.filas`, no
de la lógica de extracción de abajo.

=============================================================================
EXTENSIÓN [HU-04][BE-01]: implementación de leer()
=============================================================================
DECISIÓN TÉCNICA — deduplicación proyecto/contrato: tras propagar las
columnas combinadas (`_comun.rellenar_celdas_combinadas`), una fila de
"solo contrato" queda IDÉNTICA a la fila de proyecto de la que cuelga en las
tres columnas propagadas (bpin, nombre_proyecto, indicador_producto_raw) —
es la peculiaridad 6 documentada en `_comun.py`. Se colapsan con
`drop_duplicates(subset=<esas columnas>, keep="first")`: conserva la PRIMERA
aparición de cada grupo (la fila de proyecto real) y descarta sus filas de
contrato asociadas, que no aportan nada a `Proyecto` (HU-04/BE-01 solo
almacena el proyecto; el contrato de esa fila ya se persiste, por separado,
vía CONTRATACION en `ejecucion.py`/`[HU-03][BE-06]`, cruzando por BPIN/código
de rubro más adelante — no es responsabilidad de este lector).

LIMITACIÓN CONOCIDA (MENOR, sin CA que la contradiga): si el archivo real
tuviera una fila de proyecto con BPIN/nombre/indicador genuinamente en blanco
(no documentado en la anatomía real: los 38 proyectos reales siempre traen
las tres), `rellenar_celdas_combinadas` la fusionaría con el proyecto
anterior en vez de tratarla como un proyecto sin identificar. No hay
evidencia de que esto ocurra en los datos reales (ver ANATOMÍA arriba).

BPIN: se guarda con `_comun.texto()` (sin pasar por `CodigoBpin.desde_crudo`)
porque CA-2 exige conservarlo TAL CUAL — uno de los 38 reales no cumple el
formato de 15 dígitos, y normalizarlo/rechazarlo violaría "tal cual, incluso
si su estructura interna no está completamente estandarizada".

Indicadores: `CodigoIndicadorProducto.extraer_todos` (ya implementada y
probada, [HU-04][BE-03]) hace la separación línea por línea; `leer()` solo
la invoca y guarda los valores como texto plano en
`proyectos["codigos_indicador"]` — sin deduplicar (mismo criterio que
`extraer_todos`: un código repetido en la celda es información real, no un
error). La deduplicación por `UniqueConstraint(proyecto_id,
cod_indicador_producto)` de `ProyectoIndicadorORM` es responsabilidad de la
etapa Load (`reemplazar_proyectos`, todavía sin implementar — [HU-04][BE-04]),
no de este lector: mismo principio de una responsabilidad por función que ya
separa extracción (aquí) de persistencia (`repositorios.py`).
"""

from __future__ import annotations

from typing import Any

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun
from app.shared.codigos import CodigoIndicadorProducto
from app.shared.errors import ArchivoInvalido

OBLIGATORIAS: dict[str, tuple[str, ...]] = {
    "bpin": ("Código BPIN", "Codigo BPIN", "BPIN"),
    "indicador_producto_raw": ("Indicador de producto", "Indicador producto"),
}

# CA-3 ([HU-04][BE-02]): la única columna de proyecto, aparte de las dos
# obligatorias, que HU-04 necesita para "tal cual" (CA-2) es el nombre — el
# resto de columnas del archivo real (datos de contrato) no se validan ni se
# extraen (docstring del módulo, "sin validar el resto").
OPCIONALES: dict[str, tuple[str, ...]] = {
    "nombre_proyecto": ("Nombre del proyecto", "Nombre proyecto"),
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
        """[HU-04][BE-01]: extrae proyecto + indicadores, tal cual (CA-2).

        Ver "EXTENSIÓN [HU-04][BE-01]" en el docstring del módulo para la
        deduplicación proyecto/contrato y las demás decisiones.
        """
        hoja, fila_encabezado = resolver_hoja_proyectos(contenido, nombre_archivo)
        df = _comun.leer_hoja(contenido, hoja, fila_encabezado)

        columnas = {**OBLIGATORIAS, **OPCIONALES}
        mapeo = _comun.mapear_columnas(df, columnas)
        _comun.exigir_columnas(mapeo, OBLIGATORIAS, nombre_archivo, hoja)

        columnas_a_propagar = [mapeo[clave] for clave in columnas if clave in mapeo]
        df = _comun.rellenar_celdas_combinadas(df, columnas_a_propagar)
        # Colapsa cada grupo (proyecto + sus filas de solo-contrato) a UNA
        # fila: ver DECISIÓN TÉCNICA en el docstring del módulo.
        df = df.drop_duplicates(subset=columnas_a_propagar, keep="first")

        proyectos: list[dict[str, Any]] = []
        advertencias: list[str] = []
        for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
            bpin = _comun.texto(fila[mapeo["bpin"]])
            indicador_raw = _comun.texto(fila[mapeo["indicador_producto_raw"]])
            if bpin is None and indicador_raw is None:
                # Defensivo: no debería ocurrir (resolver_hoja_proyectos ya
                # exigió encontrar ambas columnas en esta hoja) — ver
                # LIMITACIÓN CONOCIDA del docstring del módulo.
                advertencias.append(
                    f"«{hoja}», fila {posicion}: sin BPIN ni indicador tras "
                    "propagar celdas combinadas; se descarta."
                )
                continue

            codigos = CodigoIndicadorProducto.extraer_todos(indicador_raw)
            if indicador_raw is not None and not codigos:
                advertencias.append(
                    f"«{hoja}», fila {posicion} (BPIN {bpin!r}): ningún "
                    "indicador reconocible en la celda; se conserva el "
                    "proyecto sin indicadores."
                )

            proyectos.append(
                {
                    "bpin": bpin,
                    "nombre_proyecto": (
                        _comun.texto(fila[mapeo["nombre_proyecto"]])
                        if "nombre_proyecto" in mapeo
                        else None
                    ),
                    "indicador_producto_raw": indicador_raw,
                    "codigos_indicador": [c.valor for c in codigos],
                }
            )

        return ResultadoLectura(
            tipo=TipoArchivo.PROYECTOS,
            filas={"proyectos": proyectos},
            conteos={"proyectos": len(proyectos)},
            advertencias=advertencias,
        )
