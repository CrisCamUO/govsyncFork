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

from datetime import date

from app.modules.cortes.domain.entidades import ArchivoFuente, Corte
from app.modules.cortes.domain.puertos import RepositorioCortes, RepositorioDatosCorte


class ServicioCortes:
    def __init__(
        self,
        repo_cortes: RepositorioCortes,
        repo_datos: RepositorioDatosCorte,
        confirmar_transaccion,
        revertir_transaccion,
        hoy: date | None = None,
    ) -> None:
        self._cortes = repo_cortes
        self._datos = repo_datos
        self._commit = confirmar_transaccion
        self._rollback = revertir_transaccion
        self._hoy = hoy or date.today()

    def crear_corte(self, vigencia: int, fecha_corte: date) -> Corte:
        """HU-01 / CA-1, CA-5, CA-7, CA-8.

        La validacion de fecha futura (CA-2) se delega al dominio, no se
        reimplementa aqui. Tras guardar el corte en BORRADOR, se reutilizan
        automaticamente PDT y PROYECTOS del ultimo corte REGISTRADO de la
        MISMA vigencia (CA-5, D-05); EJECUCION nunca se reutiliza (CA-7).
        Todo dentro de la misma transaccion: si copiar los datos de origen
        falla, no queda ni el corte a medio crear.
        """
        Corte.validar_fecha(fecha_corte, self._hoy)
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

    def cargar_archivo(self, corte_id, tipo, contenido: bytes, nombre_archivo: str):
        """HU-02, HU-03, HU-04 y HU-06 (reemplazo del archivo)."""
        raise NotImplementedError("[HU-02][BE-04] / [HU-03][BE-06] / [HU-04][BE-04]")

    def registrar_corte(self, corte_id):
        """HU-01 / CA-3 y CA-4."""
        raise NotImplementedError("[HU-01][BE-05]")

    def listar_cortes(self) -> list[Corte]:
        return self._cortes.listar()
