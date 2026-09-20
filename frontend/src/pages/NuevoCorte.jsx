import { useState } from "react";
import { api } from "../api/cliente.js";
import CargaDeArchivo from "../components/CargaDeArchivo.jsx";
import { Cargando, Error as EstadoError } from "../components/Estados.jsx";
import VistaPreviaDescartes from "../components/VistaPreviaDescartes.jsx";

/**
 * Asistente de creación de un corte.
 *
 * TARJETAS: [HU-01][FE-02] Formulario con calendario restringido
 *           [HU-01][FE-03] Panel de fuentes obligatorias y reutilizadas
 *           [HU-02][FE-02] Pantalla de carga del PDT y confirmación de
 *                           columnas (CA-1, CA-3, CA-4, CA-5) — YA
 *                           IMPLEMENTADO, ver paso 2 abajo.
 *           [HU-03][FE-02] Pantalla de carga presupuestal
 *           [HU-04][FE-02] Carga de la plantilla BPIN (CA-1, CA-2) — YA
 *                           IMPLEMENTADO, ver paso 2 abajo. Tarjeta de Karold, adelantada
 *                           aquí porque no había respuesta de coordinación;
 *                           mismo precedente que sentó Juan Esteban con PDT
 *                           bajo su propia tarjeta [HU-02][FE-02] — revisar
 *                           antes de fusionar.
 *           [HU-04][FE-03] Vista previa de códigos extraídos y descartados —
 *                           YA IMPLEMENTADO (componente `VistaPreviaDescartes`,
 *                           PR #79), integrado aquí en el paso 2 de PROYECTOS.
 *
 * FLUJO
 *   Paso 1  vigencia y fecha — el calendario NO permite fechas futuras (CA-2),
 *           pero el rechazo también debe venir del backend: ocultar la opción
 *           en el frontend no es una validación. Al enviar, el corte creado
 *           (con su `id`) queda en estado local y se avanza al paso 2 — antes
 *           el resultado de `crearCorte` se descartaba; [HU-02][FE-02] es el
 *           primer consumidor real de ese `id`.
 *   Paso 2  carga de archivos. Implementa PDT ([HU-02][FE-02], CA-1, CA-3,
 *           CA-4, CA-5) y PROYECTOS ([HU-04][FE-02]/[FE-03]) — EJECUCION
 *           ([HU-03][FE-02]) sigue sin adelantarse, tarjeta aparte. Tampoco
 *           se adelanta la reutilización automática de un corte anterior
 *           (HU-01/CA-5, CA-6): eso es [HU-01][FE-03].
 *   Paso 3  registrar. Bloqueado: `POST /cortes/{id}/registrar` no existe
 *           todavía como endpoint (ver TODO en `api/cliente.js`), aunque el
 *           dominio/aplicación ya están listos ([HU-01][BE-05]).
 *
 * [HU-02][FE-02], D15 (docs/DECISIONES.md): el backend distingue solo DOS
 * `detalles.motivo` para el rechazo del PDT — `hoja_no_encontrada` cubre a
 * la vez "pestaña no encontrada" (CA-2) y "archivo incorrecto" (CA-4);
 * `columnas_faltantes` es el único que además trae qué columna falta
 * (CA-3). Se muestra `error.message` del backend tal cual (ya es
 * específico, `EstadoError` ya lo despliega junto con `detalles`), sin
 * fabricar un tercer mensaje propio en este componente. Es un SUPUESTO,
 * pendiente de que el equipo lo confirme — ver D15 para la alternativa
 * descartada.
 */

export default function NuevoCorte() {
  const [vigencia, setVigencia] = useState("");
  const [fechaCorte, setFechaCorte] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const [corte, setCorte] = useState(null);
  const [resultadoPdt, setResultadoPdt] = useState(null);
  const [errorPdt, setErrorPdt] = useState(null);
  const [resultadoProyectos, setResultadoProyectos] = useState(null);
  const [errorProyectos, setErrorProyectos] = useState(null);
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
      const corteCreado = await api.crearCorte(vigenciaNumerica, fechaCorte);
      setCorte(corteCreado);
    } catch (errorApi) {
      setError(errorApi);
    } finally {
      setEnviando(false);
    }
  }

  // [HU-02][FE-02]: `CargaDeArchivo` nunca captura el error de `onCargar`
  // (solo envuelve el estado "enviando" en un try/finally, ver su
  // docstring) — este componente es quien debe atraparlo y pasarlo de
  // vuelta como prop `error`, nunca dejar que se propague sin manejar.
  async function subirPdt(archivo) {
    setErrorPdt(null);
    try {
      const resultado = await api.cargarArchivo(corte.id, "PDT", archivo);
      setResultadoPdt(resultado);
    } catch (errorApi) {
      setErrorPdt(errorApi);
    }
  }

  // [HU-04][FE-02]: mismo criterio que subirPdt — CargaDeArchivo nunca
  // captura el error de onCargar, este componente lo atrapa y lo pasa de
  // vuelta como prop error.
  async function subirProyectos(archivo) {
    setErrorProyectos(null);
    try {
      const resultado = await api.cargarArchivo(corte.id, "PROYECTOS", archivo);
      setResultadoProyectos(resultado);
    } catch (errorApi) {
      setErrorProyectos(errorApi);
    }
  }

  if (corte) {
    return (
      <section>
        <h1>Cargar archivos del corte</h1>
        <p>
          Corte de vigencia {corte.vigencia}, fecha {corte.fecha_corte}.
        </p>

        <CargaDeArchivo
          tipo="PDT"
          etiqueta="Plan Indicativo"
          cargado={Boolean(resultadoPdt)}
          resultado={
            resultadoPdt &&
            // HU-02/CA-5: "confirma visualmente cuántas metas fueron
            // reconocidas" — `filas_reconocidas` es el conteo genérico que
            // expone `ArchivoFuenteRespuestaParcial`; esta pantalla es la
            // que sabe que para PDT esas filas son "metas" (el componente
            // compartido no lo interpreta, ver su docstring).
            `${resultadoPdt.filas_reconocidas} metas reconocidas.`
          }
          error={errorPdt}
          onCargar={subirPdt}
        />

        <CargaDeArchivo
          tipo="PROYECTOS"
          etiqueta="Plantilla de proyectos BPIN"
          cargado={Boolean(resultadoProyectos)}
          resultado={
            resultadoProyectos && (
              <>
                {/* [HU-04][FE-02]: confirmación del conteo genérico, mismo
                    criterio que ya usa PDT — esta pantalla es la que sabe
                    que para PROYECTOS esas filas son "proyectos". */}
                <p>
                  {resultadoProyectos.filas_reconocidas} proyectos reconocidos.
                </p>

                {/* [HU-04][FE-02]/CA-2: mensaje explícito exigido por la
                    tarjeta — evita que la administradora crea que el
                    sistema rechazó el archivo por no tener estructura
                    estándar. El backend ya lo conserva tal cual
                    (HU-04/CA-2, lectores/proyectos.py), esto solo lo
                    comunica. */}
                <p className="carga-de-archivo-nota">
                  El archivo se conservó tal cual fue cargado, aunque su
                  estructura no sea estándar.
                </p>

                {/* [HU-04][FE-03]: ya construido en PR #79, solo se integra. */}
                <VistaPreviaDescartes
                  descartes={resultadoProyectos.descartes}
                />
              </>
            )
          }
          error={errorProyectos}
          onCargar={subirProyectos}
        />
      </section>
    );
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
