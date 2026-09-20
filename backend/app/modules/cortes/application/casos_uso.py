"""Casos de uso del módulo de cortes.

CAPA: Aplicación
TARJETAS: [HU-01][BE-03] CrearCorte
          [HU-01][BE-04] Regla de reutilización de fuentes entre cortes
          [HU-01][BE-05] Registro del corte y transición a REGISTRADO
          [HU-02][BE-04] CargarPlanIndicativo
          [HU-03][BE-06] CargarPresupuestal
          [HU-04][BE-04] CargarPlantillaBPIN

Orquesta dominio + repositorios + lectores y CONTROLA LA TRANSACCIÓN. No
importa FastAPI ni SQLAlchemy: recibe los puertos ya construidos desde
`core/dependencias.py` (inyección de dependencias).

=============================================================================
FRONTERAS DEL PIPELINE ETL — NO MEZCLARLAS
=============================================================================
    EXTRACT + TRANSFORM   el lector (estrategia por tipo), FUERA de la
                          transacción de escritura
    LOAD                  el repositorio, DENTRO de la transacción

Si la transformación falla, no se abrió ninguna transacción. Si el Load falla,
se revierte completo. En ningún caso quedan datos parciales — que es lo que
exige HU-02/CA-3.

=============================================================================
VALIDACIÓN DE ARCHIVOS: AQUÍ, NO EN LA API
=============================================================================
[SEC-03] dice: «La validación de archivos es una responsabilidad única en la
capa de Aplicación: no vive en la API, no se repite en cada caso de uso.»

Checklist de esa tarjeta:
  - Extensión declarada vs. MIME real del contenido
  - Tamaño máximo configurable, verificado ANTES de leer en memoria
  - Sanitización del nombre de archivo (path traversal)
  - Rechazo de libros con macros (.xlsm)
  - Verificación de que las hojas obligatorias existen antes de procesar
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from app.modules.cortes.application.validacion_archivos import (
    TAMANO_MAX_POR_DEFECTO,
    validar_archivo_cargado,
)
from app.modules.cortes.domain.entidades import ArchivoFuente, Corte, TipoArchivoFuente
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte
from app.shared.errors import OperacionNoPermitida, RecursoNoEncontrado

if TYPE_CHECKING:
    from app.modules.ingesta.domain.contratos import LectorArchivoFuente, ResultadoLectura


class ServicioCortes:
    def __init__(
        self,
        repo_cortes: RepositorioCortes,
        repo_datos: RepositorioDatosCorte,
        confirmar_transaccion,
        revertir_transaccion,
        lectores: dict[TipoArchivoFuente, LectorArchivoFuente] | None = None,
        hoy: date | None = None,
        tamano_max_archivo: int = TAMANO_MAX_POR_DEFECTO,
    ) -> None:
        """`lectores`: DECISIÓN TÉCNICA de [HU-02][BE-04] (Strategy, ya
        prescrito por el docstring de `ingesta/domain/contratos.py`: "un
        `if tipo == ...` central mezclaría tres conjuntos de reglas"). Se
        inyecta un mapeo tipo->lector en vez de que `cargar_archivo`
        instancie lectores concretos: así la capa Aplicación solo depende
        de la abstracción `LectorArchivoFuente` (DIP), igual que ya hace con
        `RepositorioCortes`/`RepositorioDatosCorte`. El composition root
        (`core/dependencias.py`) es quien arma este mapeo con los lectores
        reales. Por eso es un parámetro CON DEFAULT (`None` -> `{}`): los
        tests y llamadores existentes de `ServicioCortes(...)` que no cargan
        archivos siguen funcionando sin cambios (R2 del plan de trabajo).
        """
        self._cortes = repo_cortes
        self._datos = repo_datos
        self._commit = confirmar_transaccion
        self._rollback = revertir_transaccion
        self._lectores: dict[TipoArchivoFuente, LectorArchivoFuente] = lectores or {}
        self._hoy = hoy or date.today()
        self._tamano_max_archivo = tamano_max_archivo

    def crear_corte(self, vigencia: int, fecha_corte: date) -> Corte:
        """HU-01 / CA-1, CA-5, CA-7, CA-8.

        La validacion de fecha futura (CA-2) se delega al dominio, no se
        reimplementa aqui. D11 (docs/DECISIONES.md): se rechaza con 409 si
        ya existe un corte en BORRADOR, sin importar su vigencia — el
        indice unico parcial de la BD es el respaldo contra la condicion de
        carrera, no el mecanismo principal. D9: se rechaza con 409 si ya
        existe un corte con la misma vigencia y fecha_corte exacta, por la
        misma razon (el indice unico `ux_corte_vigencia_fecha` es el
        respaldo, no el mecanismo principal). Tras guardar el corte en
        BORRADOR, se reutilizan automaticamente PDT y PROYECTOS del ultimo
        corte REGISTRADO de la MISMA vigencia (CA-5, D-05); EJECUCION nunca
        se reutiliza (CA-7). Todo dentro de la misma transaccion: si copiar
        los datos de origen falla, no queda ni el corte a medio crear.
        """
        Corte.validar_fecha(fecha_corte, self._hoy)
        if self._cortes.existe_borrador_activo():
            raise OperacionNoPermitida(
                "Ya existe un corte en BORRADOR. Corríjalo o regístrelo antes de crear uno nuevo.",
                detalles={"motivo": "borrador_activo_existente"},
            )
        if self._cortes.existe_corte_duplicado(vigencia, fecha_corte):
            raise OperacionNoPermitida(
                f"Ya existe un corte con vigencia {vigencia} y fecha de corte "
                f"{fecha_corte.isoformat()}.",
                detalles={
                    "motivo": "vigencia_fecha_duplicada",
                    "vigencia": vigencia,
                    "fecha_corte": fecha_corte.isoformat(),
                },
            )
        corte = Corte(vigencia=vigencia, fecha_corte=fecha_corte)
        try:
            corte_guardado = self._cortes.guardar(corte)
            self._reutilizar_fuentes(corte_guardado)
            self._commit()
        except Exception:
            self._rollback()
            raise
        return corte_guardado

    def _reutilizar_fuentes(self, corte: Corte) -> None:
        """HU-01/BE-04: copia PDT y PROYECTOS del ultimo corte REGISTRADO de
        la misma vigencia (CA-5). No hace nada si no existe uno (primer corte
        de la vigencia) o si esa fuente no aplica (CA-7, EJECUCION).

        CA-6 (reemplazar un archivo reutilizado) no se implementa aqui: ya lo
        resuelve `registrar_archivo`/`reemplazar_*` (HU-06), que SIEMPRE
        sustituye el archivo de ese tipo sin importar si estaba reutilizado.
        """
        origen = self._cortes.ultimo_registrado(vigencia=corte.vigencia)
        if origen is None:
            return
        for tipo, archivo_origen in origen.archivos.items():
            if not corte.puede_reutilizar(tipo):
                continue
            filas_copiadas = self._datos.copiar_datos(origen.id, corte.id, tipo)
            archivo_nuevo = ArchivoFuente(
                tipo=tipo,
                nombre_archivo=archivo_origen.nombre_archivo,
                filas_reconocidas=filas_copiadas,
                reutilizado=True,
                corte_origen_id=origen.id,
            )
            self._cortes.registrar_archivo(corte.id, archivo_nuevo)
            corte.archivos[tipo] = archivo_nuevo

    def cargar_archivo(
        self,
        corte_id: uuid.UUID,
        tipo: TipoArchivoFuente,
        contenido: bytes,
        nombre_archivo: str,
    ) -> ArchivoFuente:
        """HU-02/CA-1, HU-03/CA-1, HU-04/CA-1 y HU-06 (reemplazo del archivo).

        Respeta la frontera del pipeline ETL documentada en el docstring del
        módulo: EXTRACT+TRANSFORM (SEC-03 + el lector de `tipo`, vía
        `_lectores`, Strategy) se ejecuta COMPLETO antes de abrir ninguna
        escritura. Si el archivo es inválido o el lector lo rechaza, no se
        abrió transacción y no hay nada que revertir. LOAD
        (`repo_datos.reemplazar_*`) y el registro del `ArchivoFuente` sí
        viajan dentro de la misma transacción: si el Load falla, se revierte
        completo (HU-02/CA-3: rechazo total, nunca datos parciales).

        SUPUESTO (MENOR — registrado, no bloqueante): no se restringe el
        estado del corte (BORRADOR vs REGISTRADO). Ninguna CA de HU-02/03/04
        lo exige explícitamente; corregir un archivo de un corte ya
        REGISTRADO es HU-05/HU-06, todavía sin implementar. Si el equipo
        decide que solo debe poder cargarse contra un corte en BORRADOR, hay
        que agregar esa validación aquí explícitamente.
        """
        corte = self._cortes.obtener(corte_id)
        if corte is None:
            raise RecursoNoEncontrado(f"No existe un corte con id {corte_id}.")

        lector = self._lectores.get(tipo)
        if lector is None:
            raise ValueError(
                f"No hay un lector registrado para el tipo de archivo {tipo!r}. "
                "Revisar el mapeo `lectores` con el que se construyó ServicioCortes."
            )

        # --- EXTRACT + TRANSFORM: fuera de la transacción de escritura -----
        nombre_saneado = validar_archivo_cargado(
            contenido, nombre_archivo, tamano_max=self._tamano_max_archivo
        )
        resultado = lector.leer(contenido, nombre_saneado, corte.vigencia)

        # --- LOAD: dentro de la transacción ---------------------------------
        try:
            filas_cargadas = self._cargar_resultado(corte_id, tipo, resultado)
            archivo = ArchivoFuente(
                tipo=tipo,
                nombre_archivo=nombre_saneado,
                filas_reconocidas=filas_cargadas,
                reutilizado=False,
                corte_origen_id=None,
                descartes=resultado.descartes,
                descartes=resultado.descartes,
                conteos=resultado.conteos,
                codigos=resultado.codigos,
            )
            self._cortes.registrar_archivo(corte_id, archivo)
            self._commit()
        except Exception:
            self._rollback()
            raise
        corte.archivos[tipo] = archivo
        return archivo

    def _cargar_resultado(
        self, corte_id: uuid.UUID, tipo: TipoArchivoFuente, resultado: ResultadoLectura
    ) -> int:
        """Despacho de la etapa Load por tipo (Strategy): cada fuente llena
        tablas distintas de `RepositorioDatosCorte` — un método por tipo, no
        uno genérico. Mismo criterio que `LectorArchivoFuente` (Strategy) en
        `ingesta/domain/contratos.py`; ver docstring de esa clase.

        Las tres fuentes SÍ están implementadas: `lectores/pdt.py`,
        `lectores/ejecucion.py` y `lectores/proyectos.py` producen sus claves
        respectivas de `ResultadoLectura.filas`, y `RepositorioDatosCorteSQL`
        las persiste con `reemplazar_metas`/`reemplazar_presupuesto`/
        `reemplazar_proyectos` (ver el docstring de cada uno para el orden de
        escritura y la resolución de FKs).
        """
        if tipo is TipoArchivoFuente.PDT:
            return self._datos.reemplazar_metas(corte_id, resultado.filas["metas"])
        if tipo is TipoArchivoFuente.EJECUCION:
            return self._datos.reemplazar_presupuesto(
                corte_id,
                resultado.filas["rubros"],
                resultado.filas["contratos"],
                resultado.filas["registros"],
            )
        if tipo is TipoArchivoFuente.PROYECTOS:
            return self._datos.reemplazar_proyectos(corte_id, resultado.filas["proyectos"])
        raise ValueError(f"Tipo de archivo sin manejador de carga: {tipo!r}")

    def registrar_corte(self, corte_id) -> Corte:
        """HU-01 / CA-3 y CA-4.

        La regla (que archivos exige, que mensaje da si falta alguno) vive en
        el dominio: `Corte.registrar()` lanza OperacionNoPermitida y no
        cambia el estado si falta algo. Aqui solo se orquesta: buscar,
        delegar la regla, persistir la transicion y confirmar la transaccion.
        """
        corte = self._cortes.obtener(corte_id)
        if corte is None:
            raise RecursoNoEncontrado(f"No existe un corte con id {corte_id}.")
        corte.registrar()
        try:
            self._cortes.confirmar_registro(corte)
            self._commit()
        except Exception:
            self._rollback()
            raise
        return corte

    def corregir_corte(self, corte_id, vigencia: int, fecha_corte: date) -> Corte:
        """D11 (docs/DECISIONES.md): corrige vigencia/fecha de un corte en
        BORRADOR, sin pasar por rechazar-y-crear-uno-nuevo.

        Mismo patrón que `registrar_corte`: buscar, validar duplicado (D9)
        excluyendo al propio corte, delegar la regla al dominio (estado
        BORRADOR y fecha no futura, `Corte.corregir()`), persistir y
        confirmar la transacción. El chequeo de duplicado va ANTES de
        `corte.corregir()` a propósito: `corte` es el mismo objeto que
        guarda el repositorio (por referencia, no por copia) — mutarlo
        antes de saber si la operación completa va a tener éxito dejaría
        vigencia/fecha corregidas visibles en memoria aunque el 409 de
        duplicado aborte la operación sin persistir nada.
        """
        corte = self._cortes.obtener(corte_id)
        if corte is None:
            raise RecursoNoEncontrado(f"No existe un corte con id {corte_id}.")
        if self._cortes.existe_corte_duplicado(vigencia, fecha_corte, excluir_id=corte_id):
            raise OperacionNoPermitida(
                f"Ya existe un corte con vigencia {vigencia} y fecha de corte "
                f"{fecha_corte.isoformat()}.",
                detalles={
                    "motivo": "vigencia_fecha_duplicada",
                    "vigencia": vigencia,
                    "fecha_corte": fecha_corte.isoformat(),
                },
            )
        corte.corregir(vigencia, fecha_corte, self._hoy)
        try:
            self._cortes.confirmar_correccion(corte)
            self._commit()
        except Exception:
            self._rollback()
            raise
        return corte

    def listar_cortes(self) -> list[Corte]:
        return self._cortes.listar()

    def obtener_corte(self, corte_id) -> Corte:
        """[HU-01][FE-01] GET /cortes/{id}: detalle de un corte.

        Agregado por [HU-01][FE-01] (capa API) para soportar el detalle por
        id. No cambia ningun metodo existente; requiere coordinacion con
        Juan Esteban antes de fusionar, porque toca la capa de aplicacion
        (ver docs/TRAZABILIDAD.md y CODEOWNERS).
        """
        corte = self._cortes.obtener(corte_id)
        if corte is None:
            raise RecursoNoEncontrado(f"No existe un corte con id {corte_id}.")
        return corte
