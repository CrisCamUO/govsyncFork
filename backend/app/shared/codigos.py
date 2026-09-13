"""Objetos de valor de códigos de dominio.

CAPA: Dominio (kernel compartido)
TARJETA: [TRANS-01] Objeto de valor CodigoIndicador (9 dígitos)
BLOQUEA A: HU-02, HU-03, HU-04, HU-07

=============================================================================
POR QUÉ ESTA ES LA PRIMERA TAREA DEL SPRINT
=============================================================================
HU-02 (SisPT), HU-03 (CCPET) y HU-04 (separación multivalor) necesitan la
MISMA normalización. Implementarla tres veces produce tres comportamientos
distintos ante el mismo dato, y el cruce de HU-07 falla sin que nadie sepa
por qué.

=============================================================================
EVIDENCIA MEDIDA SOBRE LOS ARCHIVOS REALES DE SANTA ROSA
=============================================================================
El código de indicador de producto de 9 dígitos es la ÚNICA llave presente en
las cuatro fuentes:

    PDT "Código de indicador de producto (MGA)" ∩ Ejecución CodigoIndicadorCcpet
        -> 119 de 120
    Proyectos (códigos extraídos de la celda) ∩ PDT indicador MGA
        -> 67 de 67
    Ejecución CodigoIndicadorCcpet ∩ Contratación "Cod Indicador Ccpet"
        -> 40 de 40

NO usar "Código de indicador de producto (SisPT)" del PDT como llave: contiene
identificadores del tipo "IP-63" y su intersección con los códigos CCPET es
CERO. (La guía GovSync_guia_implementacion_postgresql.md §3.4 afirma lo
contrario; esa medición se hizo contra esta columna equivocada.)

Cuatro códigos reales EMPIEZAN EN CERO:
    040110500, 040600400, 040600500, 040601600
Por eso el valor es SIEMPRE texto y nunca un entero.

=============================================================================
QUÉ DEBE HACER (de la tarjeta)
=============================================================================
- Recibir el valor tal cual viene de pandas (str, int, float, NaN).
- Conservar los ceros a la izquierda: nunca convertir a int.
- Validar longitud de 9 dígitos.
- Rechazar con excepción de dominio si el valor no es normalizable.
- Ser inmutable y comparable por valor.

CUIDADO CON UN CASO BORDE: si Excel entregó el código como número, pudo perder
UN cero a la izquierda (los códigos de sector van de 01 a 45, nunca 00). Se
puede rellenar de 8 a 9 dígitos, pero rellenar cualquier número corto fabrica
códigos inexistentes: '12345' NO es '000012345'.

RESTRICCIÓN ARQUITECTÓNICA: sin imports de pandas, SQLAlchemy, FastAPI ni
openpyxl en este archivo. Lo verifica tests/test_arquitectura.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.errors import ReglaDeNegocioViolada

#: Longitud canónica del código de indicador de producto (MGA / CCPET).
LONGITUD_INDICADOR = 9
#: Longitud canónica del BPIN vigente (los de 13 dígitos anteriores a 2025 se
#: tratarán en la ingesta / HU-04, no en este objeto de valor).
LONGITUD_BPIN = 15
#: Máximo relleno de ceros a la izquierda tolerado: solo recupera el cero que
#: Excel pudo comerse al leer un código de 9 dígitos como número (9 -> 8).
TOLERANCIA_CERO_PERDIDO = 1


def _es_cadena_de_digitos(valor: object, longitud: int) -> bool:
    """True si `valor` es un str de exactamente `longitud` dígitos ASCII."""
    return isinstance(valor, str) and len(valor) == longitud and valor.isascii() and valor.isdigit()


def _a_texto(crudo: object) -> str | None:
    """Normaliza un valor de celda de Excel a texto de dígitos, o None.

    Acepta lo que pandas suele entregar (str, int, float, NaN, None). NO limpia
    separadores ni símbolos: "$ 1.218.264.452" debe quedar descartado más
    adelante por no ser solo dígitos.
    """
    if crudo is None or isinstance(crudo, bool):
        return None
    if isinstance(crudo, int):
        return str(crudo)
    if isinstance(crudo, float):
        if crudo != crudo:  # NaN
            return None
        if not crudo.is_integer():
            return None
        return str(int(crudo))
    if isinstance(crudo, str):
        return crudo.strip() or None
    return None


def _normalizar_a_longitud(texto: str, longitud: int, *, tolerancia: int = 0) -> str | None:
    """Devuelve `texto` ajustado a `longitud` dígitos, o None si no es válido.

    - Exactamente `longitud` dígitos: se devuelve tal cual.
    - Entre `longitud - tolerancia` y `longitud - 1` dígitos: se rellena con
      ceros a la izquierda (recupera el cero que Excel comió).
    - Cualquier otro caso: None (no se fabrican códigos que no existen).
    """
    if not (texto.isascii() and texto.isdigit()):
        return None
    if len(texto) == longitud:
        return texto
    if longitud - tolerancia <= len(texto) < longitud:
        return texto.zfill(longitud)
    return None


@dataclass(frozen=True, slots=True)
class CodigoIndicadorProducto:
    """Código de 9 dígitos que identifica un indicador de producto."""

    valor: str

    def __post_init__(self) -> None:
        if not _es_cadena_de_digitos(self.valor, LONGITUD_INDICADOR):
            raise ReglaDeNegocioViolada(
                f"Código de indicador de producto inválido: {self.valor!r}. "
                f"Se esperan {LONGITUD_INDICADOR} dígitos como texto.",
            )

    @classmethod
    def desde_crudo(cls, crudo: object) -> CodigoIndicadorProducto | None:
        """Normaliza un valor de Excel. Devuelve None si no es un código válido."""
        texto = _a_texto(crudo)
        if texto is None:
            return None
        normalizado = _normalizar_a_longitud(
            texto, LONGITUD_INDICADOR, tolerancia=TOLERANCIA_CERO_PERDIDO
        )
        if normalizado is None:
            return None
        return cls(normalizado)

    @classmethod
    def extraer_todos(cls, texto: object) -> list[CodigoIndicadorProducto]:
        """Separa los indicadores multivalor de una sola celda (HU-04/CA-4).

        La celda real del archivo de Proyectos contiene bloques como:

            459903100
            Entidades, organismos y dependencias asistidos técnicamente
            $ 1.218.264.452

            459902300
            Sistema de Gestión implementado
            $230.000.000,00

        DISEÑO: se evalúa LÍNEA POR LÍNEA (`texto.split("\\n")`), nunca con una
        expresión regular sobre el bloque completo. Un `re.findall(r"\\d{9}")`
        ingenuo, aplicado al texto entero, puede "encontrar" 9 dígitos dentro de
        un monto sin separadores (`$ 1.218.264.452` -> `1218264452`, 10 dígitos
        contiguos) o dentro de un BPIN de 15 si alguno apareciera en la celda —
        exactamente el fragmento que la tarjeta pide evitar. Al exigir que la
        LÍNEA COMPLETA, ya recortada de espacios, sean nueve dígitos ASCII y
        nada más, un monto o un BPIN de 15 nunca puede calzar por longitud.

        SUPUESTO (no confirmado con la clienta, no crítico para el modelo de
        datos): no se aplica la tolerancia de "un cero perdido" de
        `desde_crudo` aquí. Esa tolerancia existe para cuando pandas leyó la
        celda ENTERA como número y perdió el cero al convertir a texto; aquí
        cada línea ya es texto tal cual lo escribió el municipio, así que un
        candidato de 8 dígitos no es "un 9 con el cero comido", es casi
        seguro un monto o fragmento sin el símbolo `$` — normalizarlo
        fabricaría un código que no existe. Si la clienta confirma que SÍ debe
        recuperarse en este caso, es un cambio acotado a esta función.

        No se deduplica: si el mismo código aparece dos veces en la celda
        (dos bloques distintos con el mismo indicador), CA-4 no pide
        colapsarlos y hacerlo perdería información real de conteo.
        """
        if not isinstance(texto, str):
            return []
        codigos: list[CodigoIndicadorProducto] = []
        for linea in texto.split("\n"):
            candidato = linea.strip()
            if _es_cadena_de_digitos(candidato, LONGITUD_INDICADOR):
                codigos.append(cls(candidato))
        return codigos


@dataclass(frozen=True, slots=True)
class CodigoBpin:
    """Código BPIN de 15 dígitos."""

    valor: str

    def __post_init__(self) -> None:
        if not _es_cadena_de_digitos(self.valor, LONGITUD_BPIN):
            raise ReglaDeNegocioViolada(
                f"Código BPIN inválido: {self.valor!r}. "
                f"Se esperan {LONGITUD_BPIN} dígitos como texto.",
            )

    @classmethod
    def desde_crudo(cls, crudo: object) -> CodigoBpin | None:
        texto = _a_texto(crudo)
        if texto is None:
            return None
        normalizado = _normalizar_a_longitud(texto, LONGITUD_BPIN)
        if normalizado is None:
            return None
        return cls(normalizado)
