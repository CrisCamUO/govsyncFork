/**
 * Control reutilizable de carga de un archivo fuente.
 *
 * TARJETA: [UX-02] Componente reutilizable de carga de archivos
 * USADO POR: [HU-02][FE-02], [HU-03][FE-02], [HU-04][FE-02]
 *
 * Un solo componente para las tres cargas. Debe cubrir:
 *   - selección de archivo (.xlsx) por clic o arrastrar-soltar, estado "procesando"
 *   - reporte de lo reconocido (HU-02/CA-5: "cuántas metas")
 *   - error específico con sus detalles (usa [UX-03])
 *   - opción de REEMPLAZAR si ya hay uno cargado (HU-01/CA-6 y HU-06)
 *
 * OJO [HU-03][FE-02]: UN solo control para el archivo presupuestal aunque
 * tenga dos pestañas — así lo exige HU-03/CA-2 —, con confirmación que reporta
 * ambas pestañas por separado.
 *
 * DISEÑO: `onCargar` llega como prop, este componente NUNCA llama a
 * `api.cargarArchivo()` directamente — esa función sigue bloqueada
 * ([HU-02..04][BE-04/BE-06], el endpoint no existe todavía). Así el
 * componente sirve por igual a las tres rutas de subida (PDT, EJECUCION,
 * PROYECTOS) sin conocer a cuál apunta cada una; el padre decide.
 *
 * `onCargar` firma completa:
 *   onCargar(archivo: File, actualizarProgreso: (porcentaje: number) => void)
 * `actualizarProgreso` es opcional de usar por quien implemente `onCargar`
 * — si nunca se invoca, el componente simplemente no muestra la barra de
 * progreso y se queda con el spinner indeterminado de `Cargando`. Hoy
 * `cliente.js` no tiene ninguna implementación con progreso real (usa
 * `fetch()`, sin `onprogress`) — requeriría una función aislada con
 * `XMLHttpRequest`, propuesta pero no implementada aquí (coordinar con
 * quien mantiene `cliente.js`, [UX-01]).
 *
 * `resultado` llega ya formateado por el padre (ReactNode). Este componente
 * no interpreta campos como `metas_reconocidas` o `filas_ejecucion_reconocidas`
 * — esos varían por tipo y son responsabilidad de cada pantalla `[HU-0x][FE-02]`.
 *
 * `error` sigue la forma de `ErrorApi` (`.message`, `.codigo`, `.detalles`) y
 * se delega tal cual a `Estados.jsx::Error` — [SEC-03] vive en el backend
 * (docs/SEGURIDAD.md), este componente no reimplementa esas reglas; el
 * `accept=".xlsx"` y `TAMANO_MAXIMO_BYTES` de abajo son solo ayuda de UX,
 * no una validación real.
 */

import { useId, useState } from "react";
import { Cargando, Error as EstadoError } from "./Estados.jsx";

const TAMANO_MAXIMO_BYTES = 2_097_152; // 2 MB — acordado con Cristhian,
// archivos reales hoy < 200 KB (ver docs/DECISIONES.md D12)

function tieneExtensionValida(nombreArchivo) {
  return nombreArchivo.toLowerCase().endsWith(".xlsx");
}

export default function CargaDeArchivo({
  tipo,
  etiqueta,
  cargado,
  resultado,
  error,
  onCargar,
}) {
  const [enviando, setEnviando] = useState(false);
  const [progreso, setProgreso] = useState(null);
  const [avisoExtension, setAvisoExtension] = useState(false);
  const [avisoTamano, setAvisoTamano] = useState(false);
  const idEntrada = useId();

  async function procesarArchivo(archivo) {
    if (!archivo) return;

    if (!tieneExtensionValida(archivo.name)) {
      setAvisoExtension(true);
      setAvisoTamano(false);
      return;
    }

    if (archivo.size > TAMANO_MAXIMO_BYTES) {
      setAvisoTamano(true);
      setAvisoExtension(false);
      return;
    }

    setAvisoExtension(false);
    setAvisoTamano(false);
    setProgreso(null);
    setEnviando(true);
    try {
      await onCargar(archivo, (porcentaje) => setProgreso(porcentaje));
    } finally {
      setEnviando(false);
    }
  }

  async function manejarSeleccion(evento) {
    const archivo = evento.target.files?.[0];
    // Permite volver a seleccionar el mismo archivo después de un error o
    // aviso, ya que un input de archivo no dispara "change" dos veces con
    // el mismo valor si no se limpia.
    evento.target.value = "";
    await procesarArchivo(archivo);
  }

  function manejarArrastrarSobre(evento) {
    // Requerido por la especificación HTML para que "drop" dispare.
    evento.preventDefault();
  }

  async function manejarSoltar(evento) {
    evento.preventDefault();
    const archivo = evento.dataTransfer.files?.[0];
    await procesarArchivo(archivo);
  }

  if (enviando) {
    return (
      <div className="carga-de-archivo" data-tipo={tipo}>
        <Cargando mensaje={`Subiendo ${etiqueta}…`} />
        {progreso !== null && (
          <p className="carga-de-archivo-progreso">
            <progress value={progreso} max={100} />
            <span>{progreso}%</span>
          </p>
        )}
      </div>
    );
  }

  const etiquetaAccion = cargado ? "Reemplazar" : "Cargar";

  return (
    <div
      className="carga-de-archivo"
      data-tipo={tipo}
      onDragOver={manejarArrastrarSobre}
      onDrop={manejarSoltar}
    >
      <label htmlFor={idEntrada}>
        {etiquetaAccion} {etiqueta}
      </label>
      <input
        id={idEntrada}
        type="file"
        accept=".xlsx"
        onChange={manejarSeleccion}
      />

      {avisoExtension && (
        <p className="carga-de-archivo-aviso">
          Solo se aceptan archivos .xlsx.
        </p>
      )}

      {avisoTamano && (
        <p className="carga-de-archivo-aviso">
          El archivo supera el tamaño máximo permitido (
          {TAMANO_MAXIMO_BYTES / 1_048_576} MB).
        </p>
      )}

      {error && <EstadoError error={error} />}

      {!error && resultado && (
        <div className="carga-de-archivo-resultado">{resultado}</div>
      )}
    </div>
  );
}
