"""Utilidades compartidas por los lectores de Excel.

CAPA: Persistencia (infraestructura). Aquí SÍ se permite pandas y openpyxl.
TARJETAS: [HU-02][BE-01], [HU-02][BE-02], [HU-03][BE-01], [HU-03][BE-03]

=============================================================================
REGLA NO NEGOCIABLE: TODA LECTURA CON dtype=str
=============================================================================
pandas infiere int64 en las columnas de códigos y destruye los ceros a la
izquierda. En los archivos reales hay 4 códigos que empiezan en cero
(040110500, 040600400, 040600500, 040601600); leerlos como número los
convierte en 8 dígitos y rompe TODOS los cruces (HU-03/CA-7).

=============================================================================
PECULIARIDADES DE LOS ARCHIVOS REALES QUE ESTAS UTILIDADES DEBEN ABSORBER
=============================================================================
Ver docs/DATOS.md para el detalle medido.

1. El PDT trae una fila de títulos de sección ('PARTE ESTRATÉGICA') ENCIMA del
   encabezado real; el archivo de ejecución no. En vez de fijar un número
   mágico por archivo, buscar la primera fila que contenga las columnas
   requeridas.

2. La pestaña de ejecución NO se llama 'EJECUCION': Excel trunca los nombres
   de hoja a 31 caracteres y en el archivo real quedó como
   'Formato Resumido Ejecucion Gast'. Comparar normalizado y por prefijo.

3. Los encabezados traen tildes, saltos de línea y espacios finales
   inconsistentes entre cortes.

4. El mismo dato se llama 'CodigoIndicadorCcpet' en Ejecución y
   'Cod Indicador Ccpet' en Contratación (HU-03/CA-3): resolver por alias, sin
   duplicar columnas.

5. Montos en formato colombiano conviven con valores planos y decimales:
   '$ 1.218.264.452', '$230.000.000,00', '133200000', '0.3774091922543439'.
   Usar Decimal, no float: son cifras de presupuesto público.

6. El archivo de Proyectos usa 221 rangos de celdas COMBINADAS verticalmente:
   una fila de proyecto seguida de filas que solo traen datos de contrato. Sin
   propagar el valor hacia abajo, esos contratos quedan huérfanos.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
import pandas as pd

from app.shared.errors import ArchivoInvalido


def normalizar_encabezado(texto: object) -> str:
    """Quita tildes, colapsa espacios y saltos de línea, pasa a minúsculas.

    Para COMPARAR (nombre de hoja, nombre de columna) contra un alias
    declarado en el código — no para datos que se muestran a la
    administradora (para eso está `texto()`, que preserva el original).
    """
    if texto is None:
        return ""
    if isinstance(texto, float) and texto != texto:  # NaN
        return ""
    sin_tildes = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    colapsado = re.sub(r"\s+", " ", sin_tildes).strip()
    return colapsado.lower()


def abrir_libro(contenido: bytes, nombre_archivo: str):
    """Abre el .xlsx como libro de solo lectura.

    SEGURIDAD [SEC-03]: la firma real del archivo y la ausencia de macros ya
    se validaron en `cortes/application/validacion_archivos.py` ANTES de que
    el contenido llegue aquí — esta función no repite esa validación. Si algo
    igual sale mal al abrir (defensa en profundidad, no la ruta esperada), se
    traduce a `ArchivoInvalido` en vez de dejar escapar la excepción cruda de
    openpyxl/zipfile.

    `read_only=True` y `data_only=True`: no evalúa fórmulas ni carga estilos,
    acota el uso de memoria en archivos grandes.
    """
    try:
        return openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        detalle = f" «{nombre_archivo}»" if nombre_archivo else ""
        raise ArchivoInvalido(
            f"No se pudo abrir el archivo{detalle} como libro de Excel.",
            detalles={"motivo": "libro_no_abre"},
        ) from exc


def resolver_hoja(nombres_reales: list[str], alias: tuple[str, ...]) -> str | None:
    """Encuentra la hoja cuyo nombre coincide con alguno de los alias.

    Compara normalizado y también por prefijo, en las dos direcciones (ver
    peculiaridad 2 arriba): el nombre real puede ser el alias truncado a 31
    caracteres por Excel, o viceversa si el alias declarado es más corto.
    Coincidencia exacta tiene prioridad sobre coincidencia por prefijo.
    """
    alias_normalizados = [normalizar_encabezado(a) for a in alias]

    for nombre in nombres_reales:
        if normalizar_encabezado(nombre) in alias_normalizados:
            return nombre

    for nombre in nombres_reales:
        normalizado = normalizar_encabezado(nombre)
        for alias_norm in alias_normalizados:
            if normalizado.startswith(alias_norm) or alias_norm.startswith(normalizado):
                return nombre

    return None


def localizar_fila_encabezado(
    contenido: bytes, hoja: str, requeridas: tuple[str, ...], max_filas: int = 8
) -> int:
    """Detecta en qué fila está el encabezado real (peculiaridad 1).

    Recorre las primeras `max_filas` filas de `hoja` y devuelve el índice
    (0-based, coincide con el parámetro `header` de `pandas.read_excel`) de
    la primera que contenga TODAS las columnas de `requeridas` — sin asumir
    un número de fila fijo, porque el PDT trae una fila de título de sección
    encima y el archivo de ejecución no.
    """
    libro = abrir_libro(contenido, "")
    try:
        try:
            ws = libro[hoja]
        except KeyError as exc:
            raise ArchivoInvalido(
                f"La hoja «{hoja}» no existe en el archivo.",
                detalles={"motivo": "hoja_no_encontrada", "hoja": hoja},
            ) from exc

        requeridas_norm = {normalizar_encabezado(r) for r in requeridas}
        for indice, fila in enumerate(ws.iter_rows(max_row=max_filas, values_only=True)):
            valores_norm = {normalizar_encabezado(v) for v in fila if v is not None}
            if requeridas_norm <= valores_norm:
                return indice

        raise ArchivoInvalido(
            f"No se encontró la fila de encabezado en la hoja «{hoja}»; "
            f"se esperaban las columnas: {', '.join(requeridas)}.",
            detalles={"motivo": "encabezado_no_encontrado", "hoja": hoja},
        )
    finally:
        libro.close()


def leer_hoja(contenido: bytes, hoja: str, fila_encabezado: int) -> pd.DataFrame:
    """Lee una hoja completa COMO TEXTO y descarta filas totalmente vacías.

    `dtype=str` no es opcional (ver la REGLA NO NEGOCIABLE del docstring del
    módulo): sin ella, pandas infiere int64 en las columnas de código y
    destruye los ceros a la izquierda antes de que `CodigoIndicadorProducto`
    tenga oportunidad de recuperarlos.
    """
    df = pd.read_excel(
        io.BytesIO(contenido),
        sheet_name=hoja,
        header=fila_encabezado,
        dtype=str,
        engine="openpyxl",
    )
    df.columns = [normalizar_encabezado(c) for c in df.columns]
    return df.dropna(how="all")


def mapear_columnas(df: pd.DataFrame, requeridas: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Resuelve nombres lógicos -> nombres reales de columna, por alias.

    Es lo que hace equivalentes 'CodigoIndicadorCcpet' y 'Cod Indicador Ccpet'
    sin duplicar columnas (HU-03/CA-3, HU-07).

    Best-effort: si ningún alias de una clave lógica aparece en `df`, esa
    clave simplemente no queda en el resultado. El rechazo formal por columna
    faltante es responsabilidad de `exigir_columnas` ([HU-02][BE-02]), no de
    esta función — mantiene una sola responsabilidad por función.

    La comparación tolera diferencias de tildes, mayúsculas y espacios (ver
    peculiaridad 3) reutilizando `normalizar_encabezado` — la misma
    normalización que usa el resto del módulo para comparar nombres de hoja y
    de columna, en vez de una segunda implementación paralela ([HU-03][BE-03]
    la introdujo por separado porque en su momento `normalizar_encabezado`
    todavía era un stub; consolidado aquí para no mantener dos normalizaciones
    del mismo tipo de dato). Ante varios alias presentes para la misma clave
    lógica, gana el primero en el orden declarado en `requeridas`.
    """
    columnas_reales = list(df.columns)
    normalizadas = {normalizar_encabezado(str(c)): c for c in columnas_reales}

    resultado: dict[str, str] = {}
    for logico, alias in requeridas.items():
        for candidato in alias:
            real = normalizadas.get(normalizar_encabezado(candidato))
            if real is not None:
                resultado[logico] = real
                break
    return resultado


def exigir_columnas(
    mapeo: dict[str, str],
    obligatorias: dict[str, tuple[str, ...]],
    nombre_archivo: str,
    hoja: str,
) -> None:
    """Rechaza la carga COMPLETA si falta alguna columna obligatoria.

    HU-02/CA-3: el rechazo es total y el mensaje dice QUÉ falta. No se
    incorporan datos parciales.

    No resuelve el `mapeo` (eso es `mapear_columnas`, [HU-03][BE-03]): solo
    verifica que cada nombre lógico de `obligatorias` haya sido resuelto. Los
    alias de `obligatorias` no se usan para buscar — solo para nombrar la
    columna que falta en un mensaje legible.
    """
    faltantes = [logico for logico in obligatorias if logico not in mapeo]
    if not faltantes:
        return

    nombres_legibles = [obligatorias[logico][0] for logico in faltantes]
    raise ArchivoInvalido(
        f"«{nombre_archivo}» no tiene las columnas obligatorias de «{hoja}»: "
        f"{', '.join(nombres_legibles)}.",
        detalles={
            "motivo": "columnas_faltantes",
            "hoja": hoja,
            "columnas_faltantes": nombres_legibles,
        },
    )


def texto(valor: object) -> str | None:
    """Normaliza una celda a texto limpio, o None si está vacía.

    A diferencia de `normalizar_encabezado`, conserva mayúsculas y tildes: es
    para datos que se muestran a la administradora (nombre de producto), no
    para comparar contra un alias declarado en el código.
    """
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:  # NaN
        return None
    limpio = str(valor).strip()
    return limpio or None


#: Todo lo que no sea dígito, coma, punto o signo menos se descarta (símbolo
#: de moneda, espacios). No se usa para VALIDAR el formato, solo para limpiar
#: antes de decidir qué representan '.' y ',' (ver `numero()`).
_LIMPIA_MONEDA = re.compile(r"[^0-9,.\-]")

#: Un entero agrupado en miles con '.' (formato colombiano SIN decimales):
#: uno o más grupos de EXACTAMENTE 3 dígitos después del primero, sin coma.
#: El peso colombiano no maneja 3 decimales (models.py usa Numeric(20, 2)),
#: así que un único punto seguido de exactamente 3 dígitos es casi siempre
#: separador de miles ('133.200' -> 133200), nunca un decimal fraccionario.
_PATRON_MILES_SIN_DECIMAL = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def numero(valor: object) -> Decimal | None:
    """Convierte una celda a Decimal tolerando el formato colombiano.

    Ver peculiaridad 5: en los archivos reales conviven '$ 1.218.264.452'
    (miles con punto, sin decimales), '$230.000.000,00' (miles con punto,
    decimales con coma), '133200000' (plano) y '0.3774091922543439' (decimal
    plano, ya sea que la celda llegue como texto por el `dtype=str` de
    `leer_hoja` o, en llamadas directas a esta función, como el
    float/int/Decimal nativo de una prueba).

    Regla de desambiguación (no hay forma de acertar 100% sin contexto, pero
    esta cubre los cuatro casos documentados):
      1. Si hay coma: es formato colombiano con decimales -> el punto es
         separador de miles (se elimina) y la coma es el separador decimal
         (se convierte a punto).
      2. Si no hay coma pero el texto entero son grupos de miles de 3 dígitos
         separados por punto (`_PATRON_MILES_SIN_DECIMAL`): el punto es
         separador de miles -> se elimina, sin agregar decimales.
      3. En cualquier otro caso (un solo punto con un número de dígitos
         distinto de 3, o ningún separador): se trata como un decimal plano,
         tal cual.

    Decimal y no float: la aritmética binaria introduce error de redondeo en
    pesos. Devuelve None si la celda está vacía o no es reconocible como
    número — igual que `texto()`/`_meta_a_decimal` en los demás lectores: es
    responsabilidad de quien llama decidir si eso amerita una advertencia o
    un rechazo.
    """
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:  # NaN
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto_valor = _LIMPIA_MONEDA.sub("", str(valor).strip())
    if not texto_valor or texto_valor in {"-", "."}:
        return None

    if "," in texto_valor:
        texto_valor = texto_valor.replace(".", "").replace(",", ".")
    elif _PATRON_MILES_SIN_DECIMAL.match(texto_valor):
        texto_valor = texto_valor.replace(".", "")

    try:
        return Decimal(texto_valor)
    except InvalidOperation:
        return None


def fecha(valor: object) -> date | None:
    """Convierte una celda a `date`, tolerando que llegue como texto.

    [HU-03][BE-06]: por el `dtype=str` de `leer_hoja`, una celda de fecha de
    Excel llega como el texto de un timestamp de pandas
    ('2026-01-13 00:00:00'), no como `datetime`/`date` nativo — salvo que se
    llame directo (pruebas), donde sí puede llegar como objeto. Se soportan
    ambos casos. Devuelve None si no es reconocible; es responsabilidad de
    quien llama decidir si eso amerita una advertencia.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, float) and valor != valor:  # NaN
        return None

    texto_valor = str(valor).strip()
    if not texto_valor:
        return None
    texto_valor = texto_valor.split(" ")[0].split("T")[0]
    for patron in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto_valor, patron).date()
        except ValueError:
            continue
    return None


def rellenar_celdas_combinadas(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Propaga hacia abajo el valor de celdas verticalmente combinadas.

    Ver peculiaridad 6. Sin esto, [HU-04] pierde contratos.

    Excel solo guarda el valor en la celda superior izquierda de un rango
    combinado; al leer con pandas, las demás llegan como None/NaN. `ffill()`
    propaga el último valor no nulo de cada columna hacia abajo, en el mismo
    orden en que aparecen las filas en el archivo — que es exactamente lo que
    Excel muestra visualmente para una celda combinada.
    """
    df = df.copy()
    df[columnas] = df[columnas].ffill()
    return df
