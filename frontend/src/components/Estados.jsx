/**
 * Estados de interfaz reutilizables: cargando, vacío y error.
 *
 * TARJETA: [UX-04] Estados compartidos de carga, vacío y error
 * USADO POR: [UX-02], [HU-02][FE-02], [HU-03][FE-02], [HU-04][FE-02],
 *            [HU-07][FE-02]
 *
 * Se centralizan para que cada pantalla los trate igual.
 *
 * LO IMPORTANTE ESTÁ EN `Error`: un error del backend puede traer `detalles`
 * (qué columna o pestaña falta). Mostrarlos es la diferencia entre «no se pudo
 * cargar» y un mensaje accionable — que es justamente lo que piden
 * HU-02/CA-3, HU-03/CA-4 y HU-01/CA-3.
 */

export function Cargando({ mensaje = "Cargando…" }) {
  return (
    <div role="status" aria-live="polite">
      <p>{mensaje}</p>
    </div>
  );
}

export function Vacio({ titulo, descripcion, accion }) {
  return (
    <div className="estado-vacio">
      {titulo && <p className="estado-vacio-titulo">{titulo}</p>}
      {descripcion && <p className="estado-vacio-descripcion">{descripcion}</p>}
      {accion && <div className="estado-vacio-accion">{accion}</div>}
    </div>
  );
}

export function SinCorrespondencia({ texto = "Sin correspondencia" }) {
  return <span className="estado-sin-correspondencia">{texto}</span>;
}

// [UX-03] Este componente se llama igual que el `Error` nativo de JS. Si el
// archivo que lo consume también hace `throw new Error(...)`, importar con
// alias: import { Error as EstadoError } from "./Estados.jsx".

//: Claves de `detalles` documentadas hoy (ver comentario de api/cliente.js).
// Cualquier clave nueva que el backend agregue se muestra igual, con una
// etiqueta genérica — nunca se descarta en silencio.
const ETIQUETAS_DETALLE_CONOCIDAS = {
  columnas_faltantes: "Columnas faltantes",
  pestanas_faltantes: "Pestañas faltantes",
  archivos_faltantes: "Archivos faltantes",
};

function etiquetaGenerica(clave) {
  const texto = clave.replaceAll("_", " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function listarDetalles(detalles) {
  return Object.entries(detalles)
    .filter(([, valor]) =>
      Array.isArray(valor) ? valor.length > 0 : Boolean(valor),
    )
    .map(([clave, valor]) => {
      const etiqueta =
        ETIQUETAS_DETALLE_CONOCIDAS[clave] ?? etiquetaGenerica(clave);
      const texto = Array.isArray(valor) ? valor.join(", ") : String(valor);
      return { clave, texto: `${etiqueta}: ${texto}` };
    });
}

export function Error({ error, onReintentar }) {
  if (!error) return null;

  const mensaje = error.message || "Ocurrió un error inesperado.";
  const detalles = error.detalles ?? {};
  const items = listarDetalles(detalles);

  return (
    <div className="estado-error" role="alert">
      <p className="estado-error-mensaje">{mensaje}</p>

      {error.codigo && (
        <p className="estado-error-codigo">
          Código: <span className="codigo">{error.codigo}</span>
        </p>
      )}

      {items.length > 0 && (
        <ul className="estado-error-detalles">
          {items.map(({ clave, texto }) => (
            <li key={clave}>{texto}</li>
          ))}
        </ul>
      )}

      {onReintentar && (
        <button
          type="button"
          className="estado-error-reintentar"
          onClick={onReintentar}
        >
          Reintentar
        </button>
      )}
    </div>
  );
}
