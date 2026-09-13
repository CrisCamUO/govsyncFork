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
// eslint-disable-next-line no-unused-vars -- UX-01 define el helper; FE-01 lo consumirá.
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
  // TODO [HU-01][FE-01] crearCorte, listarCortes, obtenerCorte, registrarCorte
  // TODO [HU-02..04][FE-01] cargarArchivo(corteId, tipo, archivo)
  // TODO [HU-07][FE-01] matriz(corteId, pagina, tamanoPagina)
};
