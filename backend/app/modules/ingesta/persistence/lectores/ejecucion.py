"""Lector del archivo presupuestal: pestañas de ejecución y contratación.

CAPA: Persistencia
TARJETAS: [HU-03][BE-01] lector de las dos pestañas
          [HU-03][BE-02] preservación de ceros a la izquierda
          [HU-03][BE-04] validación de presencia de ambas pestañas
          [HU-03][BE-05] detección de archivo que no corresponde
CUBRE: HU-03 / CA-2, CA-4, CA-5, CA-7 (numeración interna del código,
       reconciliada con `docs/TRAZABILIDAD.md`; el documento de la HU en
       Obsidian las numera CA01-CA06 — mismo contenido, orden distinto)

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

from typing import Any

from app.modules.ingesta.domain.contratos import (
    LectorArchivoFuente,
    ResultadoLectura,
    TipoArchivo,
)
from app.modules.ingesta.persistence.lectores import _comun
from app.shared.codigos import CodigoIndicadorProducto
from app.shared.errors import ArchivoInvalido

ALIAS_EJECUCION = (
    "EJECUCION",
    "Ejecucion resumida",
    "Formato Resumido Ejecucion Gast",
    "Formato Resumido Ejecucion Gastos",
)
ALIAS_CONTRATACION = ("CONTRATACION", "CONTRATACIÓN")

# [HU-03][BE-03]: las dos grafías del código de indicador son EL MISMO dato;
# se declaran ambas en las dos pestañas porque `mapear_columnas` (_comun.py)
# resuelve por alias sin duplicar columnas — cada pestaña real solo tendrá
# una de las dos grafías, nunca ambas.
_ALIAS_COD_INDICADOR_PRODUCTO = ("CodigoIndicadorCcpet", "Cod Indicador Ccpet")

OBLIGATORIAS_EJECUCION: dict[str, tuple[str, ...]] = {
    "cod_indicador_producto": _ALIAS_COD_INDICADOR_PRODUCTO,
}
OBLIGATORIAS_CONTRATACION: dict[str, tuple[str, ...]] = {
    "cod_indicador_producto": _ALIAS_COD_INDICADOR_PRODUCTO,
}

# HU-03/CA06 (alimenta la matriz con número y descripción del contrato):
# opcionales, no obligatorias — si faltan, la fila no se descarta, solo
# quedan en None. "Objeto" es el campo estándar de contratación pública para
# el propósito del contrato; "Descripcion Rubro Ccpet" describe el rubro
# presupuestal, no el contrato, así que no sirve aquí aunque el nombre se
# parezca (confirmado con el listado real de columnas de CONTRATACION).
OPCIONALES_CONTRATACION: dict[str, tuple[str, ...]] = {
    "numero_contrato": ("NumeroContrato",),
    "descripcion_contrato": ("Objeto",),
}


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


def _localizar_fila_encabezado_por_alias(
    contenido: bytes, hoja: str, alias: tuple[str, ...]
) -> int:
    """Como `_comun.localizar_fila_encabezado`, pero para una columna con más
    de un nombre real posible (alias), nunca los dos a la vez en el mismo
    archivo — ver `_ALIAS_COD_INDICADOR_PRODUCTO`.

    `_comun.localizar_fila_encabezado` exige que TODAS las columnas de
    `requeridas` aparezcan juntas (semántica AND): pasarle las dos grafías
    directamente nunca encontraría la fila, porque cada pestaña real solo
    trae una. Se prueba cada alias por separado (semántica OR) y se usa el
    primero que encuentre.
    """
    ultimo_error: ArchivoInvalido | None = None
    for candidato in alias:
        try:
            return _comun.localizar_fila_encabezado(contenido, hoja, (candidato,))
        except ArchivoInvalido as exc:
            ultimo_error = exc
    assert ultimo_error is not None
    raise ultimo_error


def _leer_pestana(
    contenido: bytes,
    nombre_archivo: str,
    hoja: str,
    obligatorias: dict[str, tuple[str, ...]],
    opcionales: dict[str, tuple[str, ...]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extrae las filas de una pestaña (ejecución o contratación).

    Preserva ceros a la izquierda del código de indicador vía
    `CodigoIndicadorProducto` (CA-7) y descarta con advertencia las filas
    cuyo código no sea normalizable — mismo patrón que
    `pdt.py::LectorPDT.leer`. Las columnas de `opcionales` nunca rechazan el
    archivo: si faltan, la fila las trae en `None`.
    """
    columnas = {**obligatorias, **opcionales}
    ancla_encabezado = obligatorias["cod_indicador_producto"]
    fila_encabezado = _localizar_fila_encabezado_por_alias(contenido, hoja, ancla_encabezado)
    df = _comun.leer_hoja(contenido, hoja, fila_encabezado)

    mapeo = _comun.mapear_columnas(df, columnas)
    _comun.exigir_columnas(mapeo, obligatorias, nombre_archivo, hoja)

    filas: list[dict[str, Any]] = []
    advertencias: list[str] = []
    for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
        crudo_codigo = fila[mapeo["cod_indicador_producto"]]
        codigo = CodigoIndicadorProducto.desde_crudo(crudo_codigo)
        if codigo is None:
            advertencias.append(
                f"«{hoja}», fila {posicion}: código de indicador inválido "
                f"({crudo_codigo!r}); se descarta."
            )
            continue

        fila_datos: dict[str, Any] = {"cod_indicador_producto": codigo.valor}
        for clave in opcionales:
            fila_datos[clave] = _comun.texto(fila[mapeo[clave]]) if clave in mapeo else None
        filas.append(fila_datos)

    return filas, advertencias


class LectorEjecucion(LectorArchivoFuente):
    tipo = TipoArchivo.EJECUCION

    def leer(self, contenido: bytes, nombre_archivo: str, vigencia: int) -> ResultadoLectura:
        """Extrae y transforma el archivo presupuestal ([HU-03][BE-04], [BE-05]).

        CA-4 (pestaña faltante) y CA-5 (archivo incorrecto) comparten la
        misma señal de `resolver_hojas`: si NINGUNA de las dos pestañas
        aparece, lo más probable es que no sea el archivo presupuestal en
        absoluto (CA-5); si falta SOLO una, es el archivo correcto pero
        incompleto (CA-4, nombrando cuál falta) — no hace falta una
        heurística aparte para distinguir los dos casos.
        """
        hoja_ejecucion, hoja_contratacion = resolver_hojas(contenido, nombre_archivo)

        if hoja_ejecucion is None and hoja_contratacion is None:
            raise ArchivoInvalido(
                f"«{nombre_archivo}» no corresponde al formato esperado del archivo "
                "presupuestal: no se encontró ninguna de sus dos pestañas.",
                detalles={"motivo": "archivo_no_corresponde"},
            )
        if hoja_ejecucion is None or hoja_contratacion is None:
            faltante = "EJECUCION" if hoja_ejecucion is None else "CONTRATACION"
            raise ArchivoInvalido(
                f"«{nombre_archivo}» no contiene la pestaña «{faltante}».",
                detalles={"motivo": "pestana_faltante", "pestana_faltante": faltante},
            )

        filas_ejecucion, advertencias_ejecucion = _leer_pestana(
            contenido, nombre_archivo, hoja_ejecucion, OBLIGATORIAS_EJECUCION, {}
        )
        filas_contratacion, advertencias_contratacion = _leer_pestana(
            contenido,
            nombre_archivo,
            hoja_contratacion,
            OBLIGATORIAS_CONTRATACION,
            OPCIONALES_CONTRATACION,
        )

        return ResultadoLectura(
            tipo=TipoArchivo.EJECUCION,
            filas={"ejecucion": filas_ejecucion, "contratacion": filas_contratacion},
            conteos={
                "ejecucion": len(filas_ejecucion),
                "contratacion": len(filas_contratacion),
            },
            advertencias=[*advertencias_ejecucion, *advertencias_contratacion],
        )
