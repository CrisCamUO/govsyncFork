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

  // TODO [HU-01][FE-01] registrarCorte(id) -> POST /cortes/{id}/registrar.
  //      BLOQUEADO: el endpoint no existe todavía. Depende de [HU-01][BE-05],
  //      donde Corte.registrar() y ServicioCortes.registrar_corte() siguen en
  //      NotImplementedError.
  // TODO [HU-02..04][FE-01] cargarArchivo(corteId, tipo, archivo) ->
  //      POST /cortes/{id}/archivos/{tipo}. BLOQUEADO: el endpoint no existe
  //      ([HU-02..04][BE-04/BE-06]); no hay ningún UploadFile en el backend.
  //      `solicitar` ya trae lista la rama FormData con el campo "archivo".

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
