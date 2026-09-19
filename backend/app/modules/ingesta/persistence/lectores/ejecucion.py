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
EXTENSIÓN [HU-03][BE-06]: extracción para persistencia (Rubro/Contrato/Registro)
=============================================================================
Las claves "ejecucion"/"contratacion" de ResultadoLectura.filas (arriba) solo
traen el código de indicador — es lo único que necesitaba HU-03/CA-6 (matriz)
cuando se escribieron. `reemplazar_presupuesto` (casos_uso.py/repositorios.py)
necesita las filas COMPLETAS de Rubro/Contrato/RegistroPresupuestal, así que
se agregan tres claves nuevas ("rubros", "contratos", "registros") sin tocar
las existentes — aditivo, no rompe ningún consumidor actual.

DECISIÓN TÉCNICA (delegada al equipo, sin objeción — 2026-09-18):
`ContratoORM.llave_sustituta` (comentario CT2: "NumeroContrato no es llave
única") queda SIEMPRE NULL. Se agrupa por NumeroContrato tal cual, verificado
contra los 999 registros reales de Santa Rosa: en los 34 casos donde se repite
NumeroContrato, NIT y Objeto SIEMPRE coinciden (solo varía "Valor Contrato",
consistente con múltiples CDP contra el mismo contrato) — no se encontró un
solo caso de dos contratos distintos compartiendo número. LIMITACIÓN CONOCIDA:
si otro municipio sí tiene NumeroContrato genuinamente duplicado entre dos
contratos, esta extracción los fusionaría incorrectamente. Si eso ocurre, hay
que calcular una llave real (fuera de alcance de esta entrega, sin criterio
definido por nadie del equipo a la fecha).

`valor_contrato`/`valor_pagado` del contrato agrupado: se toma el MÁXIMO
visto entre sus filas (aproximación al total; los valores parciales de CDP
son siempre <= el total). `RegistroPresupuestal.valor_pagos` queda NULL: la
columna "Pagos" del archivo real es a nivel de contrato, no hay desglose por
CDP/registro individual en la fuente.

`Rubro.codigo_rubro_completo` se llena con el mismo valor que
`codigo_rubro_nivel`: verificado que "CodigoRubro" de CONTRATACION coincide
100% con "CodigoRubroNivel" de ejecución (docstring arriba), así que no hay
un segundo dato distinto que extraer para ese propósito.

CodigoRubroNivel tiene EXACTAMENTE 1 duplicado en los datos reales (ver
arriba) pese al UniqueConstraint(corte_id, codigo_rubro_nivel) de RubroORM:
se descarta la fila repetida (se conserva la primera) con advertencia, en vez
de dejar que el INSERT falle con un error de integridad crudo.

La fila "TOTALES" (CodigoRubroCcpet=999999999, CodigoRubroNivel vacío) se
descarta: es un renglón de agregación del reporte, no un rubro real.

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

# --- [HU-03][BE-06]: columnas para Rubro (persistencia) ---------------------

#: CodigoRubroNivel siempre está en el archivo real (es la llave utilizable,
#: ver docstring del módulo): ausente => estructura del archivo rota, se
#: rechaza total. UltimoNivel también, porque es NOT NULL en la BD.
OBLIGATORIAS_RUBRO: dict[str, tuple[str, ...]] = {
    "codigo_rubro_nivel": ("CodigoRubroNivel",),
    "ultimo_nivel": ("UltimoNivel",),
}

# El resto son opcionales: si falta alguna, la fila la trae en None en vez de
# rechazar el archivo completo — a diferencia de las dos de arriba, ninguna
# de estas es indispensable para que la fila tenga sentido como Rubro.
OPCIONALES_RUBRO: dict[str, tuple[str, ...]] = {
    "codigo_rubro_ccpet": ("CodigoRubroCcpet",),
    "cod_indicador_producto": _ALIAS_COD_INDICADOR_PRODUCTO,
    "codigo_tipo_gasto": ("CodigoTipoGasto",),
    "nombre_financiacion": ("NombreFuenteFinanciacionCcpet",),
    "codigo_sector_ccpet": ("CodigoSectorCcpet",),
    "codigo_producto_ccpet": ("CodigoProductoCcpet",),
    "apropiacion_definitiva": ("ApropiacionDefinitiva",),
    "disponibilidad_acumulada": ("DisponibilidadAcumulada",),
    "compromiso_acumulado": ("Compromiso Acumulado",),
    # OrdenPagoAcumulado -> obligacion_acumulada (ver DINERO/obligacion en
    # models.py: "base del % de avance financiero").
    "obligacion_acumulada": ("OrdenPagoAcumulado",),
    "pago_acumulado": ("PagoAcumulado",),
}

# --- [HU-03][BE-06]: columnas para Contrato/RegistroPresupuestal ------------

#: NumeroContrato ancla la fila de CONTRATACION para la extracción de
#: persistencia (distinto del ancla de OBLIGATORIAS_CONTRATACION arriba, que
#: es cod_indicador_producto — esa extracción es la histórica para CA-6, esta
#: es la nueva para reemplazar_presupuesto).
OBLIGATORIAS_CONTRATO: dict[str, tuple[str, ...]] = {
    "numero_contrato": ("NumeroContrato",),
}

OPCIONALES_CONTRATO: dict[str, tuple[str, ...]] = {
    "objeto": ("Objeto",),
    "modalidad_seleccion": ("Modalidad seleccion",),
    "tipo_gasto": ("Tipo Gasto",),
    "nit_contratista": ("Nit Contratista",),
    "nombre_contratista": ("Nombre Contratista",),
    "valor_contrato": ("Valor Contrato",),
    "valor_pagado": ("Pagos",),
    "bpin": ("Codigo Bpin", "CodigoBpin"),
    "cod_indicador_producto": _ALIAS_COD_INDICADOR_PRODUCTO,
    "numero_cdp": ("Numero CDP",),
    "fecha_cdp": ("Fecha CDP",),
    "codigo_rubro_crudo": ("CodigoRubro",),
    "valor_cdp": ("Valor CDP",),
    "numero_registro": ("Numero Registro",),
    "fecha_registro": ("Fecha Registro",),
    "valor_registro_ptal": ("Valor Registro Ptal",),
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


def _texto_opcional(fila, mapeo: dict[str, str], clave: str) -> str | None:
    return _comun.texto(fila[mapeo[clave]]) if clave in mapeo else None


def _monto_opcional(fila, mapeo: dict[str, str], clave: str):
    return _comun.numero(fila[mapeo[clave]]) if clave in mapeo else None


def _fecha_opcional(fila, mapeo: dict[str, str], clave: str):
    return _comun.fecha(fila[mapeo[clave]]) if clave in mapeo else None


def _es_ultimo_nivel(crudo: object) -> bool | None:
    """Interpreta UltimoNivel (True/False). None si no es reconocible.

    Por el `dtype=str` de `leer_hoja`, un booleano de Excel llega como el
    texto 'True'/'False' (str() de un bool de Python) — mismo patrón que
    `_es_principal` en pdt.py.
    """
    normalizado = _comun.normalizar_encabezado(crudo)
    if normalizado in {"true", "verdadero", "si", "sí"}:
        return True
    if normalizado in {"false", "falso", "no"}:
        return False
    return None


def _leer_rubros(
    contenido: bytes, nombre_archivo: str, hoja: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """[HU-03][BE-06]: extrae la pestaña de ejecución completa para Rubro.

    A diferencia de `_leer_pestana` (que solo saca `cod_indicador_producto`
    para la matriz de HU-07), esta función NO descarta una fila por no tener
    un indicador válido: la mayoría de rubros reales no lo traen (ver
    docstring del módulo, "CodigoBpin poblado en 3 de 485") y siguen siendo
    rubros presupuestales válidos que hay que persistir.

    Sí descarta (con advertencia, nunca rechazo total — son problemas de
    fila, no de estructura): la fila TOTALES (codigo_rubro_nivel vacío), una
    fila sin UltimoNivel reconocible (es NOT NULL en la BD, ver models.py) y
    un codigo_rubro_nivel repetido (hay exactamente 1 en los datos reales,
    pese al UniqueConstraint de RubroORM — se conserva la primera aparición).
    """
    columnas = {**OBLIGATORIAS_RUBRO, **OPCIONALES_RUBRO}
    ancla_encabezado = OBLIGATORIAS_RUBRO["codigo_rubro_nivel"]
    try:
        fila_encabezado = _comun.localizar_fila_encabezado(contenido, hoja, ancla_encabezado)
        df = _comun.leer_hoja(contenido, hoja, fila_encabezado)
        mapeo = _comun.mapear_columnas(df, columnas)
        _comun.exigir_columnas(mapeo, OBLIGATORIAS_RUBRO, nombre_archivo, hoja)
    except ArchivoInvalido:
        # A diferencia de HU-02/CA-3 (PDT), ninguna CA de HU-03 exige rechazar
        # TODO el archivo presupuestal si falta esta columna estructural — la
        # extracción histórica de "ejecucion"/"contratacion" (CA-6, arriba) no
        # depende de ella. Se degrada con advertencia: no hay rubros que
        # persistir, pero el resto del archivo (y su matriz de CA-6) sigue
        # siendo válido.
        return [], [
            f"«{hoja}»: no se encontró la columna «{ancla_encabezado[0]}»; "
            "no se pudieron extraer rubros para persistencia (HU-03/BE-06)."
        ]

    rubros: list[dict[str, Any]] = []
    advertencias: list[str] = []
    vistos: set[str] = set()
    for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
        codigo_rubro_nivel = _comun.texto(fila[mapeo["codigo_rubro_nivel"]])
        if codigo_rubro_nivel is None:
            # La fila TOTALES (codigo_rubro_ccpet=999999999) no trae este
            # dato: es un renglón de agregación del reporte, no un rubro.
            continue

        if codigo_rubro_nivel in vistos:
            advertencias.append(
                f"«{hoja}», fila {posicion}: codigo_rubro_nivel repetido "
                f"({codigo_rubro_nivel!r}); se descarta (se conserva la primera aparición)."
            )
            continue

        ultimo_nivel = _es_ultimo_nivel(fila[mapeo["ultimo_nivel"]])
        if ultimo_nivel is None:
            advertencias.append(
                f"«{hoja}», fila {posicion} (rubro {codigo_rubro_nivel}): "
                f"UltimoNivel no reconocible ({fila[mapeo['ultimo_nivel']]!r}); se descarta."
            )
            continue

        vistos.add(codigo_rubro_nivel)
        cod_indicador = None
        if "cod_indicador_producto" in mapeo:
            codigo = CodigoIndicadorProducto.desde_crudo(fila[mapeo["cod_indicador_producto"]])
            cod_indicador = codigo.valor if codigo is not None else None

        rubros.append(
            {
                "codigo_rubro_nivel": codigo_rubro_nivel,
                # Ver DECISIÓN TÉCNICA del docstring del módulo: mismo valor
                # que codigo_rubro_nivel, no hay un segundo dato que extraer.
                "codigo_rubro_completo": codigo_rubro_nivel,
                "ultimo_nivel": ultimo_nivel,
                "codigo_rubro_ccpet": _texto_opcional(fila, mapeo, "codigo_rubro_ccpet"),
                "cod_indicador_producto": cod_indicador,
                "codigo_tipo_gasto": _texto_opcional(fila, mapeo, "codigo_tipo_gasto"),
                "nombre_financiacion": _texto_opcional(fila, mapeo, "nombre_financiacion"),
                "codigo_sector_ccpet": _texto_opcional(fila, mapeo, "codigo_sector_ccpet"),
                "codigo_producto_ccpet": _texto_opcional(fila, mapeo, "codigo_producto_ccpet"),
                "apropiacion_definitiva": _monto_opcional(fila, mapeo, "apropiacion_definitiva"),
                "disponibilidad_acumulada": _monto_opcional(
                    fila, mapeo, "disponibilidad_acumulada"
                ),
                "compromiso_acumulado": _monto_opcional(fila, mapeo, "compromiso_acumulado"),
                "obligacion_acumulada": _monto_opcional(fila, mapeo, "obligacion_acumulada"),
                "pago_acumulado": _monto_opcional(fila, mapeo, "pago_acumulado"),
            }
        )

    return rubros, advertencias


def _leer_contratos_y_registros(
    contenido: bytes, nombre_archivo: str, hoja: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """[HU-03][BE-06]: extrae CONTRATACION completa para Contrato+Registro.

    Modela DOS entidades (ver docstring del módulo, "45 filas repiten
    (NumeroContrato, Numero Registro) con rubros distintos"): un `Contrato`
    por NumeroContrato distinto (deduplicado — ver DECISIÓN TÉCNICA arriba
    sobre `llave_sustituta`) y un `RegistroPresupuestal` por CADA fila cruda
    (una fila = un CDP/registro contra ese contrato).
    """
    columnas = {**OBLIGATORIAS_CONTRATO, **OPCIONALES_CONTRATO}
    ancla_encabezado = OBLIGATORIAS_CONTRATO["numero_contrato"]
    try:
        fila_encabezado = _comun.localizar_fila_encabezado(contenido, hoja, ancla_encabezado)
        df = _comun.leer_hoja(contenido, hoja, fila_encabezado)
        mapeo = _comun.mapear_columnas(df, columnas)
        _comun.exigir_columnas(mapeo, OBLIGATORIAS_CONTRATO, nombre_archivo, hoja)
    except ArchivoInvalido:
        # Mismo criterio que _leer_rubros: degrada con advertencia, no
        # rechaza el archivo completo por una columna que ninguna CA de
        # HU-03 exige como obligatoria a nivel de archivo.
        return (
            [],
            [],
            [
                f"«{hoja}»: no se encontró la columna «{ancla_encabezado[0]}»; "
                "no se pudieron extraer contratos/registros para persistencia (HU-03/BE-06)."
            ],
        )

    advertencias: list[str] = []
    grupos_contrato: dict[str, list[dict[str, Any]]] = {}
    registros: list[dict[str, Any]] = []

    for posicion, (_, fila) in enumerate(df.iterrows(), start=1):
        numero_contrato = _comun.texto(fila[mapeo["numero_contrato"]])
        if numero_contrato is None:
            advertencias.append(f"«{hoja}», fila {posicion}: NumeroContrato vacío; se descarta.")
            continue

        cod_indicador = None
        if "cod_indicador_producto" in mapeo:
            codigo = CodigoIndicadorProducto.desde_crudo(fila[mapeo["cod_indicador_producto"]])
            cod_indicador = codigo.valor if codigo is not None else None

        grupos_contrato.setdefault(numero_contrato, []).append(
            {
                "objeto": _texto_opcional(fila, mapeo, "objeto"),
                "modalidad_seleccion": _texto_opcional(fila, mapeo, "modalidad_seleccion"),
                "tipo_gasto": _texto_opcional(fila, mapeo, "tipo_gasto"),
                "nit_contratista": _texto_opcional(fila, mapeo, "nit_contratista"),
                "nombre_contratista": _texto_opcional(fila, mapeo, "nombre_contratista"),
                "valor_contrato": _monto_opcional(fila, mapeo, "valor_contrato"),
                "valor_pagado": _monto_opcional(fila, mapeo, "valor_pagado"),
                "bpin": _texto_opcional(fila, mapeo, "bpin"),
                "cod_indicador_producto": cod_indicador,
            }
        )

        registros.append(
            {
                "numero_contrato": numero_contrato,
                "codigo_rubro_crudo": _texto_opcional(fila, mapeo, "codigo_rubro_crudo"),
                "numero_cdp": _texto_opcional(fila, mapeo, "numero_cdp"),
                "fecha_cdp": _fecha_opcional(fila, mapeo, "fecha_cdp"),
                "valor_cdp": _monto_opcional(fila, mapeo, "valor_cdp"),
                "numero_registro": _texto_opcional(fila, mapeo, "numero_registro"),
                "fecha_registro": _fecha_opcional(fila, mapeo, "fecha_registro"),
                "valor_registro_ptal": _monto_opcional(fila, mapeo, "valor_registro_ptal"),
            }
        )

    contratos: list[dict[str, Any]] = []
    for numero_contrato, filas_del_contrato in grupos_contrato.items():
        valores_contrato = [
            f["valor_contrato"] for f in filas_del_contrato if f["valor_contrato"] is not None
        ]
        valores_pagado = [
            f["valor_pagado"] for f in filas_del_contrato if f["valor_pagado"] is not None
        ]
        primera = filas_del_contrato[0]
        cod_indicador = next(
            (
                f["cod_indicador_producto"]
                for f in filas_del_contrato
                if f["cod_indicador_producto"]
            ),
            None,
        )
        bpin = next((f["bpin"] for f in filas_del_contrato if f["bpin"]), None)
        contratos.append(
            {
                "numero_contrato": numero_contrato,
                "objeto": primera["objeto"],
                "modalidad_seleccion": primera["modalidad_seleccion"],
                "tipo_gasto": primera["tipo_gasto"],
                "nit_contratista": primera["nit_contratista"],
                "nombre_contratista": primera["nombre_contratista"],
                "valor_contrato": max(valores_contrato) if valores_contrato else None,
                "valor_pagado": max(valores_pagado) if valores_pagado else None,
                "bpin": bpin,
                "cod_indicador_producto": cod_indicador,
            }
        )

    return contratos, registros, advertencias


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

        # [HU-03][BE-06]: extracción completa para persistencia, en paralelo
        # a la extracción histórica de arriba (ver DECISIÓN TÉCNICA del
        # docstring del módulo). Ambas leen la MISMA hoja de nuevo en vez de
        # fusionar las dos pasadas: mantiene cada extracción con una sola
        # responsabilidad (la de CA-6 vs. la de persistencia) en vez de un
        # único bucle sobreacoplado a dos consumidores distintos.
        rubros, advertencias_rubros = _leer_rubros(contenido, nombre_archivo, hoja_ejecucion)
        contratos, registros, advertencias_registros = _leer_contratos_y_registros(
            contenido, nombre_archivo, hoja_contratacion
        )

        return ResultadoLectura(
            tipo=TipoArchivo.EJECUCION,
            filas={
                "ejecucion": filas_ejecucion,
                "contratacion": filas_contratacion,
                "rubros": rubros,
                "contratos": contratos,
                "registros": registros,
            },
            conteos={
                "ejecucion": len(filas_ejecucion),
                "contratacion": len(filas_contratacion),
                "rubros": len(rubros),
                "contratos": len(contratos),
                "registros": len(registros),
            },
            advertencias=[
                *advertencias_ejecucion,
                *advertencias_contratacion,
                *advertencias_rubros,
                *advertencias_registros,
            ],
        )
