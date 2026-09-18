"""Generadores de libros de Excel para las pruebas.

TARJETA: [DEV-05] · usado por las pruebas de [HU-02], [HU-03], [HU-04]

Se construyen EN MEMORIA en vez de versionar archivos binarios: el contenido de
cada caso queda explícito y revisable en el diff, y una variante (falta una
columna, falta una pestaña) se declara aquí en vez de adjuntar otro .xlsx opaco.

Los datos deben reproducir las peculiaridades reales de los archivos de Santa
Rosa (ver docs/DATOS.md):

  - el PDT trae una fila de títulos de sección encima del encabezado;
  - la pestaña de ejecución se llama 'Formato Resumido Ejecucion Gast';
  - hay códigos de indicador que empiezan en cero;
  - la plantilla de proyectos usa celdas verticalmente combinadas y mete
    varios indicadores en una celda separados por saltos de línea;
  - un contrato tiene varios registros presupuestales;
  - hay filas de subtotal con UltimoNivel = False.

Un fixture que no reproduzca estas rarezas deja pasar defectos que sí aparecen
con el archivo real.
"""

from __future__ import annotations

import io

from openpyxl import Workbook

# Códigos usados de forma consistente en las tres fuentes, para que el cruce de
# la matriz sea verificable de punta a punta.
COD_A = "170202300"
COD_B = "040110500"  # empieza en cero: el caso que rompe un dtype numérico
COD_C = "330105300"
BPIN_1 = "202500000050132"
BPIN_2 = "202500000050299"


def _a_bytes(libro: Workbook) -> bytes:
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


#: Nombre real de la pestaña de metas (docstring de lectores/pdt.py).
HOJA_PDT = "Plan indicativo - Productos"
#: Las otras 5 pestañas del archivo real, que NO se interpretan como metas.
HOJAS_SENUELO_PDT = (
    "Líneas estratégicas",
    "Indicadores de resultado",
    "Plan indicativo SGR - Productos",
    "Iniciativas SGR",
    "Iniciativas PATR",
)


def construir_pdt(*, incluir_principal: bool = True) -> bytes:
    """PDT válido, o una variante sin una columna obligatoria (HU-02/CA-3).

    Reproduce dos peculiaridades reales: una fila de título de sección
    ('PARTE ESTRATÉGICA') encima del encabezado, y la columna SisPT con
    valores tipo 'IP-63' que NO es la llave de cruce.
    """
    libro = Workbook()
    libro.remove(libro.active)

    for nombre in HOJAS_SENUELO_PDT:
        libro.create_sheet(nombre)["A1"] = "esta hoja no trae metas"

    hoja = libro.create_sheet(HOJA_PDT)
    hoja.append(["PARTE ESTRATÉGICA"])  # peculiaridad 1: título de sección

    encabezados = [
        "Código de indicador de producto (MGA)",
        "Código de indicador de producto (SisPT)",
        "Producto (MGA)",
        "Indicador de Producto(MGA)",
    ]
    if incluir_principal:
        encabezados.append("Principal")
    encabezados += ["Programación del producto bien o servicio 2026", "Total 2026"]
    hoja.append(encabezados)

    fila_a = ["040110500", "IP-63", "Vías terciarias mantenidas", "Kilómetros"]
    if incluir_principal:
        fila_a.append("Sí")
    hoja.append([*fila_a, 10, 1218264452])

    fila_b = [COD_A, "IP-40", "Entidades asistidas técnicamente", "Número"]
    if incluir_principal:
        fila_b.append("No")
    hoja.append([*fila_b, 5, 230000000])

    return _a_bytes(libro)


#: Nombre real, truncado a 31 caracteres por Excel (docstring de ejecucion.py).
HOJA_EJECUCION = "Formato Resumido Ejecucion Gast"
HOJA_CONTRATACION = "CONTRATACION"


def construir_ejecucion(
    *, incluir_ejecucion: bool = True, incluir_contratacion: bool = True
) -> bytes:
    """Archivo presupuestal válido, o sin alguna pestaña (HU-03/CA-4)."""
    libro = Workbook()
    libro.remove(libro.active)

    if incluir_ejecucion:
        hoja = libro.create_sheet(HOJA_EJECUCION)
        hoja.append(["CodigoRubroNivel", "UltimoNivel", "CodigoIndicadorCcpet"])
        hoja.append(["1.2.3", True, COD_B])
    if incluir_contratacion:
        hoja = libro.create_sheet(HOJA_CONTRATACION)
        hoja.append(["NumeroContrato", "Cod Indicador Ccpet", "Codigo Bpin", "Objeto"])
        hoja.append(["C-001", COD_B, BPIN_1, "Mantenimiento de vías terciarias"])
    if not incluir_ejecucion and not incluir_contratacion:
        libro.create_sheet("Otra hoja")["A1"] = "sin datos relevantes"

    return _a_bytes(libro)


#: La plantilla real la nombra el municipio con el año, sin convención fija.
HOJA_PROYECTOS = "2026"


def construir_proyectos(*, incluir_bpin: bool = True) -> bytes:
    """Plantilla con celdas combinadas y un indicador multivalor (HU-04/CA-4).

    Reproduce la peculiaridad real: una fila de proyecto (BPIN e indicador)
    seguida de una fila que solo trae datos de contrato, con las columnas de
    proyecto combinadas verticalmente entre las dos. Sin propagar el valor
    hacia abajo, la fila de contrato queda huérfana (peculiaridad 6).
    """
    libro = Workbook()
    libro.remove(libro.active)
    hoja = libro.create_sheet(HOJA_PROYECTOS)

    # "No CONTRATO" nunca se combina: es lo único que trae la fila de
    # contrato, y lo que evita que `leer_hoja` la descarte con
    # `dropna(how="all")` al llegar vacía en las columnas de proyecto.
    encabezados = ["Nombre del proyecto", "Indicador de producto", "No CONTRATO"]
    if incluir_bpin:
        encabezados = ["Código BPIN", *encabezados]
    hoja.append(encabezados)

    columnas_combinadas = len(encabezados) - 1  # todas menos "No CONTRATO"

    indicador_multivalor = f"{COD_A}\n{COD_C}"
    fila_proyecto = ["Mejoramiento de vías terciarias del municipio", indicador_multivalor, None]
    if incluir_bpin:
        fila_proyecto = [BPIN_1, *fila_proyecto]
    hoja.append(fila_proyecto)
    hoja.append([*([None] * columnas_combinadas), "C-2026-001"])  # solo trae contrato

    for columna in range(1, columnas_combinadas + 1):
        hoja.merge_cells(start_row=2, end_row=3, start_column=columna, end_column=columna)

    return _a_bytes(libro)
