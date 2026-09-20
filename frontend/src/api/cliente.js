/**
 * Cliente HTTP único de GovSync.
 *
 * TARJETA: [UX-01] Layout base, enrutamiento y cliente HTTP
 *
 * Centraliza tres cosas que no deben repetirse en cada componente: la URL
 * base, las cabeceras y la traducción de los errores del backend a un objeto
 * de error uniforme.
 *
 * El backend responde los errores de negocio con esta forma (ver
 * app/core/errores.py):
 *
 *     { "codigo": "...", "mensaje": "...", "detalles": { ... } }
 *
 * `detalles` es lo que hace accionable un error: trae `columnas_faltantes`,
 * `pestanas_faltantes` o `archivos_faltantes` según el caso. [UX-03] depende
 * de que este cliente NO los descarte.
 */
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ErrorApi extends Error {
  constructor(mensaje, { estado, codigo, detalles } = {}) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
    this.codigo = codigo;
    this.detalles = detalles ?? {};
  }
}
async function solicitar(ruta, { metodo = "GET", cuerpo, archivo } = {}) {
  const headers = {
    Accept: "application/json",
  };

  const opciones = {
    method: metodo,
    headers,
  };

  if (archivo) {
    const formulario = new FormData();
    formulario.append("archivo", archivo);
    opciones.body = formulario;
  } else if (cuerpo !== undefined) {
    headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }

  let respuesta;

  try {
    respuesta = await fetch(`${BASE}${ruta}`, opciones);
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor.", {
      codigo: "error_red",
      detalles: {},
    });
  }

  const contenido = await respuesta.text();
  let datos = null;

  if (contenido) {
    try {
      datos = JSON.parse(contenido);
    } catch {
      datos = null;
    }
  }

  if (!respuesta.ok) {
    throw new ErrorApi(datos?.mensaje ?? "No se pudo completar la solicitud.", {
      estado: respuesta.status,
      codigo: datos?.codigo,
      detalles: datos?.detalles,
    });
  }

  return datos;
}

export const api = {
  /**
   * HU-01/CA-1, CA-2. Crea un corte en estado BORRADOR.
   *
   * `fechaCorte` viaja como `fecha_corte` porque así lo declara el DTO
   * `CorteEntrada` del backend (cortes/api/router.py). Formato "YYYY-MM-DD".
   * Una fecha futura no se valida aquí: el dominio la rechaza con un 422 que
   * trae `detalles.fecha_corte` y `detalles.hoy`.
   */
  crearCorte: (vigencia, fechaCorte) =>
    solicitar("/api/v1/cortes", {
      metodo: "POST",
      cuerpo: { vigencia, fecha_corte: fechaCorte },
    }),

  /** HU-01/CA-8. Histórico completo de cortes. */
  listarCortes: () => solicitar("/api/v1/cortes"),

  /**
   * HU-01/CA-8. Detalle de un corte. Un id inexistente devuelve 404 con
   * `codigo: "recurso_no_encontrado"`.
   */
  obtenerCorte: (id) => solicitar(`/api/v1/cortes/${id}`),

  /**
   * HU-01/CA-3, CA-4. Transición BORRADOR -> REGISTRADO.
   *
   * `POST /cortes/{id}/registrar` -- el endpoint ya existe (expuesto sobre
   * `Corte.registrar()`/`ServicioCortes.registrar_corte()`, ya implementados
   * y probados). 409 con `detalles.archivos_faltantes` si falta alguna de
   * las tres fuentes; 404 si el corte no existe.
   */
  registrarCorte: (id) =>
    solicitar(`/api/v1/cortes/${id}/registrar`, { metodo: "POST" }),

  /**
   * HU-02/CA-1, HU-03/CA-1, HU-04/CA-1: sube el archivo fuente `tipo` para
   * `corteId`. `POST /cortes/{corteId}/archivos/{tipo}` -- el endpoint ya
   * existe y esta probado para los 3 tipos (PDT/EJECUCION/PROYECTOS,
   * `test_router_cortes.py`); esta funcion reemplaza el TODO que decia
   * "bloqueado" (verificado 2026-09-20, backend ya cierra de punta a punta).
   *
   * 201 con `{ tipo, nombre_archivo, filas_reconocidas, descartes }`
   * (`ArchivoFuenteRespuestaParcial`, forma provisional -- todavia no incluye
   * `advertencias` a nivel de fila, solo el conteo total). 422 con
   * `codigo: "archivo_invalido"` y `detalles.motivo` en
   * `"hoja_no_encontrada"` (pestana/archivo incorrecto, D15) o
   * `"columnas_faltantes"` (con `detalles.columnas_faltantes`). 404/409 si
   * el corte no existe o no esta en BORRADOR.
   */
  cargarArchivo: (corteId, tipo, archivo) =>
    solicitar(`/api/v1/cortes/${corteId}/archivos/${tipo}`, {
      metodo: "POST",
      archivo,
    }),

  /**
   * HU-07/CA-1. Matriz de relación de un corte, paginada.
   *
   * `GET /matriz-relacion/{corteId}` ([HU-07][FE-01], montado en main.py).
   * 404 con `codigo: "recurso_no_encontrado"` si el corte no existe. 409 con
   * `detalles.archivos_faltantes` si falta alguna de las tres fuentes.
   */
  matriz: (corteId, pagina = 1, tamanoPagina = 50) =>
    solicitar(
      `/api/v1/matriz-relacion/${corteId}?pagina=${pagina}&tamano_pagina=${tamanoPagina}`,
    ),
};
