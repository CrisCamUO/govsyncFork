import { useState } from "react";
import { api } from "../api/cliente.js";
import { Cargando, Error as EstadoError } from "../components/Estados.jsx";

/**
 * Asistente de creación de un corte.
 *
 * TARJETAS: [HU-01][FE-02] Formulario con calendario restringido
 *           [HU-01][FE-03] Panel de fuentes obligatorias y reutilizadas
 *           [HU-02][FE-02] Pantalla de carga del PDT
 *           [HU-03][FE-02] Pantalla de carga presupuestal
 *           [HU-04][FE-02] Carga de la plantilla BPIN
 *           [HU-04][FE-03] Vista previa de códigos extraídos y descartados
 *
 * FLUJO
 *   Paso 1  vigencia y fecha — el calendario NO permite fechas futuras (CA-2),
 *           pero el rechazo también debe venir del backend: ocultar la opción
 *           en el frontend no es una validación.
 *   Paso 2  carga de los tres archivos. El PDT y la plantilla del municipio
 *           aparecen ya cargados si hay un corte anterior (CA-5), con opción de
 *           reemplazarlos (CA-6). El de ejecución siempre se pide (CA-7).
 *   Paso 3  registrar. El botón solo procede con los tres archivos; si falta
 *           alguno se indica CUÁL (CA-3).
 */

export default function NuevoCorte() {
  const [vigencia, setVigencia] = useState("");
  const [fechaCorte, setFechaCorte] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const hoy = new Date();
  const fechaMaxima = [
    hoy.getFullYear(),
    String(hoy.getMonth() + 1).padStart(2, "0"),
    String(hoy.getDate()).padStart(2, "0"),
  ].join("-");

  async function manejarEnvio(evento) {
    evento.preventDefault();

    const vigenciaNumerica = Number(vigencia);

    setError(null);
    setEnviando(true);

    try {
      await api.crearCorte(vigenciaNumerica, fechaCorte);
    } catch (errorApi) {
      setError(errorApi);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section>
      <form onSubmit={manejarEnvio}>
        <h1>Crear corte de seguimiento</h1>

        <div>
          <label htmlFor="vigencia">Vigencia</label>
          <input
            id="vigencia"
            name="vigencia"
            type="number"
            value={vigencia}
            onChange={(evento) => setVigencia(evento.target.value)}
            required
          />
        </div>

        <div>
          <label htmlFor="fecha-corte">Fecha del corte</label>
          <input
            id="fecha-corte"
            name="fechaCorte"
            type="date"
            max={fechaMaxima}
            value={fechaCorte}
            onChange={(evento) => {
              const nuevaFecha = evento.target.value;
              if (nuevaFecha <= fechaMaxima) {
                setFechaCorte(nuevaFecha);
              }
            }}
            required
          />
        </div>
        <button type="submit" disabled={enviando}>
          Continuar
        </button>
        {enviando && <Cargando mensaje="Creando corte…" />}
        <EstadoError error={error} />
      </form>
    </section>
  );
}
