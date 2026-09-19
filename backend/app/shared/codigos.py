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

import re
from dataclasses import dataclass
from enum import StrEnum

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


#: Separadores admitidos entre códigos de una celda multivalor
#: ([HU-04][BE-03]): coma, punto y coma, guion, espacio y salto de línea,
#: en cualquier combinación y en cualquier orden dentro del mismo archivo.
_SEPARADORES_MULTIVALOR = re.compile(r"[,;\-\s]+")


class CategoriaDescarte(StrEnum):
    """Por qué un candidato numérico terminó en `descartes`, distinguiendo
    tres situaciones estructurales muy distintas que antes compartían un
    único motivo genérico (hallazgo de Juan David sobre [HU-04][BE-03],
    ver docs/DECISIONES.md D14). NO cambia qué termina en `codigos` vs
    `descartes` — solo clasifica lo segundo para que quien lo consuma
    (p. ej. la vista previa de [HU-04][FE-03]) pueda priorizar.

    Basada puramente en la LONGITUD del candidato frente a
    `LONGITUD_INDICADOR`/`TOLERANCIA_CERO_PERDIDO`, ya calculadas — no se
    introduce ningún supuesto nuevo sobre formatos de fecha, porcentaje o
    conteo (eso sería meter juicio de negocio en una función mecánica).
    """

    #: Longitud == LONGITUD_INDICADOR - TOLERANCIA_CERO_PERDIDO (8, hoy).
    #: Candidato con más probabilidad real de ser un código de 9 con el
    #: cero comido por Excel — mismo criterio que ya usa
    #: `desde_crudo`/`_normalizar_a_longitud`, aquí solo para clasificar
    #: (no se normaliza: sigue sin fabricarse un código que no existe).
    #: Prioridad alta de revisión.
    POSIBLE_CERO_PERDIDO = "posible_cero_perdido"
    #: Longitud menor a LONGITUD_INDICADOR y distinta de la anterior
    #: (1 a `LONGITUD_INDICADOR - TOLERANCIA_CERO_PERDIDO - 1` dígitos).
    #: Casi siempre ruido de texto libre: un año, un conteo, un
    #: porcentaje sin "%". Prioridad baja de revisión.
    LONGITUD_CORTA = "longitud_corta"
    #: Longitud mayor a LONGITUD_INDICADOR y no múltiplo de ella (si fuera
    #: múltiplo, ya se habría segmentado en códigos válidos). Casi siempre
    #: un intento real fallido: un BPIN, un monto sin separadores.
    #: Prioridad alta de revisión.
    LONGITUD_LARGA = "longitud_larga"


@dataclass(frozen=True, slots=True)
class DescarteIndicador:
    """Fragmento de una celda multivalor que parecía un código pero se
    descartó, con el motivo (contrato explícito de [HU-04][BE-03]: "todo
    código descartado queda registrado con su motivo") y una `categoria`
    estructural para poder priorizar la revisión (ver `CategoriaDescarte`).
    """

    valor_crudo: str
    motivo: str
    categoria: CategoriaDescarte


@dataclass(frozen=True, slots=True)
class ResultadoExtraccionIndicadores:
    """Resultado de `CodigoIndicadorProducto.extraer_todos`: los códigos
    válidos y, por separado, lo descartado con su motivo."""

    codigos: list[CodigoIndicadorProducto]
    descartes: list[DescarteIndicador]


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
    def extraer_todos(cls, texto: object) -> ResultadoExtraccionIndicadores:
        """Separa los indicadores multivalor de una sola celda (HU-04/CA-4).

        La celda real del archivo de Proyectos contiene bloques como:

            459903100
            Entidades, organismos y dependencias asistidos técnicamente
            $ 1.218.264.452

            459902300
            Sistema de Gestión implementado
            $230.000.000,00

        REABIERTA 2026-09-19 ([HU-04][BE-03], ver docs/DECISIONES.md D13):
        la tarjeta exige, con texto literal, dos cosas que la versión
        anterior de este método no cumplía:

        1. "Separadores distintos en el mismo archivo: coma, punto y coma,
           salto de línea, guion, espacio." Antes solo se partía por
           `"\\n"`.
        2. "Todo código descartado queda registrado con su motivo." Antes,
           un candidato inválido simplemente no se agregaba a la lista —
           sin dejar rastro. Por eso el retorno cambió de
           `list[CodigoIndicadorProducto]` a `ResultadoExtraccionIndicadores`
           (BREAKING CHANGE de contrato, deliberado: el descarte con motivo
           es parte del contrato de dominio de esta tarjeta, no un detalle
           de presentación de FE-03).

        DISEÑO — por qué un único split con varios delimitadores sigue
        siendo seguro: la salvaguarda original (nunca usar una regex de
        "9 dígitos en cualquier parte" sobre el bloque completo) se
        conserva. `_SEPARADORES_MULTIVALOR` solo reconoce coma, punto y
        coma, guion, espacio y salto de línea como separadores — un monto
        como `$ 1.218.264.452` o un nombre de producto nunca quedan
        compuestos SOLO de dígitos ASCII tras partir por esos caracteres
        (conservan `$`, `.` o letras), así que jamás se confunden con un
        candidato de código. Un monto sin símbolos y sin separadores
        (`1218264452`, 10 dígitos) si se evalúa como candidato — ver punto
        siguiente.

        CASOS BORDE (tarjeta, sección "casos borde obligatorios"):

        - Candidato de exactamente 9 dígitos ASCII -> código válido.
        - Candidato de N dígitos ASCII con N múltiplo de 9 (códigos
          pegados sin separador) -> se segmenta en bloques de 9 en el
          orden en que aparecen. N que NO es múltiplo de 9 (y distinto de
          9) -> "es dato inválido: se reporta, no se adivina" — se agrega a
          `descartes` con el motivo, NUNCA se trunca ni se rellena para
          forzarlo a 9.
        - Candidato que no es una cadena de solo dígitos ASCII (nombre de
          producto, monto con `$`/`.`/`,`, texto libre) -> se ignora en
          silencio: nunca pretendió ser un código, así que no es "un
          código descartado" en el sentido de la tarjeta. Registrarlo
          igual inundaría la lista de descartes con cada palabra de cada
          nombre de producto de cada celda.
        - Celda vacía, solo espacios, o sin ningún dígito -> códigos y
          descartes vacíos, sin error.

        SUPUESTO (no confirmado con la clienta, no crítico para el modelo
        de datos): no se aplica la tolerancia de "un cero perdido" de
        `desde_crudo` aquí. Esa tolerancia existe para cuando pandas leyó
        la celda ENTERA como número y perdió el cero al convertir a texto;
        aquí cada candidato ya es texto tal cual lo escribió el municipio,
        así que uno de 8 dígitos no es "un 9 con el cero comido" — ahora
        SÍ se registra en `descartes` (antes se perdía en silencio), pero
        sigue sin normalizarse a 9 dígitos por la misma razón que antes:
        fabricaría un código que no existe en la celda real.

        LIMITACIÓN CONOCIDA (ruido, no corrupción de datos): un monto con
        coma decimal en formato colombiano (`$230.000.000,00`) queda
        partido por la coma en `$230.000.000` (ignorado, tiene símbolos) y
        `00` (candidato de 2 dígitos -> SE REGISTRA como descarte, aunque
        nunca fue un código). La tarjeta no da forma de distinguir una
        coma "separadora de códigos" de una coma "decimal de un monto" sin
        arriesgar dejar pasar un separador real; se prefirió cumplir el
        texto literal de la tarjeta (registrar todo candidato numérico de
        longitud distinta de 9) y aceptar el ruido en la lista de
        descartes de montos, ya que NO fabrica códigos falsos ni afecta
        `codigos` — solo agrega entradas de revisión manual. Pendiente de
        confirmar con el equipo si esto debe filtrarse (ver
        docs/DECISIONES.md D13).

        PENDIENTE S-3 (tarjeta, sin implementar aquí a propósito): "¿debe
        verificarse que cada código exista en el PDT ya cargado?" — la
        propia tarjeta lo marca PENDIENTE y, de confirmarse, dependería de
        HU-02 (el PDT cargado). No se convierte esa duda en requisito.

        CATEGORIZACIÓN DE DESCARTES (2026-09-19, ver docs/DECISIONES.md
        D14, hallazgo de Juan David): un número suelto dentro de texto
        libre real ("Meta 4 de 12...", "...el 2024-09-19", "Avance del
        45%...") también cae en `descartes` con el mismo motivo genérico
        que un intento de código realmente roto — nunca pretendió ser un
        código, pero `extraer_todos` no puede saberlo por contexto
        semántico (fecha/porcentaje/conteo es juicio de negocio que esta
        función mecánica no debe adivinar). Se resuelve SIN cambiar qué
        termina en `codigos` vs `descartes` — solo clasificando el
        descarte por longitud (dato que ya se calcula) en
        `CategoriaDescarte`, para que quien construya una vista de
        revisión (p. ej. [HU-04][FE-03]) pueda priorizar
        `POSIBLE_CERO_PERDIDO`/`LONGITUD_LARGA` (probable código real
        perdido) sobre `LONGITUD_CORTA` (probable ruido de texto libre).

        No se deduplica: si el mismo código aparece dos veces en la celda
        (dos bloques distintos con el mismo indicador, o un bloque de 18
        dígitos que se segmenta en dos iguales), CA-4 no pide colapsarlos
        y hacerlo perdería información real de conteo.
        """
        if not isinstance(texto, str):
            return ResultadoExtraccionIndicadores(codigos=[], descartes=[])
        codigos: list[CodigoIndicadorProducto] = []
        descartes: list[DescarteIndicador] = []
        longitud_cero_perdido = LONGITUD_INDICADOR - TOLERANCIA_CERO_PERDIDO
        for fragmento in _SEPARADORES_MULTIVALOR.split(texto):
            candidato = fragmento.strip()
            if not candidato:
                continue
            if not (candidato.isascii() and candidato.isdigit()):
                # Nunca pretendió ser un código (nombre, monto, símbolo):
                # no es "un código descartado" en el sentido de la tarjeta.
                continue
            if len(candidato) == LONGITUD_INDICADOR:
                codigos.append(cls(candidato))
            elif len(candidato) % LONGITUD_INDICADOR == 0:
                # Códigos pegados sin separador, total múltiplo de 9.
                for inicio in range(0, len(candidato), LONGITUD_INDICADOR):
                    codigos.append(cls(candidato[inicio : inicio + LONGITUD_INDICADOR]))
            else:
                if len(candidato) == longitud_cero_perdido:
                    categoria = CategoriaDescarte.POSIBLE_CERO_PERDIDO
                elif len(candidato) < LONGITUD_INDICADOR:
                    categoria = CategoriaDescarte.LONGITUD_CORTA
                else:
                    categoria = CategoriaDescarte.LONGITUD_LARGA
                descartes.append(
                    DescarteIndicador(
                        valor_crudo=candidato,
                        motivo=(
                            f"{len(candidato)} dígitos: ni {LONGITUD_INDICADOR} "
                            f"ni múltiplo de {LONGITUD_INDICADOR} (no se adivina "
                            "dónde cortarlo)."
                        ),
                        categoria=categoria,
                    )
                )
        return ResultadoExtraccionIndicadores(codigos=codigos, descartes=descartes)


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
