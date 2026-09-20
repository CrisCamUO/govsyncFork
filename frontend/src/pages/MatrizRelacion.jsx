/**
 * Matriz de relación del corte.
 *
 * TARJETAS: [HU-07][FE-02] Tabla de la matriz de relación
 *           [HU-07][FE-03] Representación explícita de la información no relacionada
 *           [HU-07][FE-04] Integración y rendimiento de la tabla
 *
 * ALCANCE DE FE-02 (CA-3 a CA-6): tabla con las seis columnas confirmadas
 * (código BPIN, indicador y/o producto, ejecución, contrato).
 *
 * CORRECCIÓN DE CONTRATO (2026-09-19): esta nota decía que el backend envía
 * las columnas junto con los datos. No es así: `GET /matriz-relacion/{id}`
 * (`trazabilidad/api/router.py::MatrizRespuesta`) solo devuelve `filas`; la
 * lista `COLUMNAS` del router es hoy una constante interna que no viaja en
 * el JSON. Los encabezados de abajo están fijos en este archivo, en el
 * mismo orden y claves que esa constante. Si el backend llega a exponer
 * `columnas` en la respuesta, este archivo debe pasar a consumirla en vez
 * de mantener su propia copia.
 *
 * DOS COSAS QUE NO SE PUEDEN PERDER EN ESTA PANTALLA
 *
 * 1. Lo que no se pudo relacionar viaja como `null` desde el backend (NULL
 *    explícito, nunca una celda vacía ambigua ni un "N/A" inventado). FE-02
 *    usa `SinCorrespondencia` (`components/Estados.jsx`, ya existe y está
 *    documentada como consumida por esta tarjeta) para esas celdas. Una
 *    representación más elaborada de este caso (agrupar, distinguir motivos)
 *    es [HU-07][FE-03], no de aquí.
 *
 * 2. Los códigos se muestran con la clase `.codigo` (monoespaciada): es lo
 *    que hace visible el cero a la izquierda de 040110500. Nunca `Number()`
 *    ni `parseInt()` sobre `cod_bpin`, `cod_indicador_producto` ni
 *    `cod_indicador_ejecucion`.
 *
 * FUERA DE ALCANCE (no adelantar [HU-07][FE-03]/[FE-04] aquí): paginación o
 * scroll infinito real (se pide solo la primera página), agrupar
 * visualmente relaciones múltiples (CA-7 ya no las colapsa el backend; esta
 * pantalla se limita a no deduplicar `filas`), o un estilo distinto para
 * "sin cruce" más allá del texto de `SinCorrespondencia`.
 */
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api/cliente.js";
import {
  Cargando,
  Error as EstadoError,
  SinCorrespondencia,
  Vacio,
} from "../components/Estados.jsx";

//: Mismo orden y claves que `trazabilidad/api/router.py::COLUMNAS` — ver
//: la nota de corrección de contrato arriba.
const COLUMNAS = [
  { clave: "cod_bpin", titulo: "Cód. BPIN" },
  { clave: "cod_indicador_producto", titulo: "Cód. indicador (SisPT)" },
  { clave: "nombre_producto", titulo: "Nombre del producto" },
  { clave: "cod_indicador_ejecucion", titulo: "Cód. indicador (ejecución)" },
  { clave: "numero_contrato", titulo: "Núm. contrato" },
  { clave: "descripcion_contrato", titulo: "Descripción" },
];

const CLAVES_CODIGO = new Set([
  "cod_bpin",
  "cod_indicador_producto",
  "cod_indicador_ejecucion",
]);

function Celda({ clave, valor }) {
  if (valor === null || valor === undefined) {
    return <SinCorrespondencia />;
  }
  return CLAVES_CODIGO.has(clave) ? (
    <span className="codigo">{valor}</span>
  ) : (
    valor
  );
}

export default function MatrizRelacion() {
  const { corteId } = useParams();
  const [intento, setIntento] = useState(0);
  // `clave` identifica a qué petición pertenece `datos`/`error`: mientras no
  // coincida con `claveActual`, la petición sigue en curso. Evita reiniciar
  // el estado con un setState síncrono al inicio del efecto (ver
  // react-hooks/set-state-in-effect) — el único setState de este efecto
  // ocurre dentro de los callbacks de la promesa.
  const [resultado, setResultado] = useState({
    clave: null,
    datos: null,
    error: null,
  });

  const claveActual = corteId ? `${corteId}:${intento}` : null;

  useEffect(() => {
    if (!corteId) return;

    const clave = `${corteId}:${intento}`;
    let vigente = true;

    api
      .matriz(corteId)
      .then((datos) => {
        if (vigente) setResultado({ clave, datos, error: null });
      })
      .catch((errorApi) => {
        if (vigente) setResultado({ clave, datos: null, error: errorApi });
      });

    return () => {
      vigente = false;
    };
  }, [corteId, intento]);

  const cargando = Boolean(claveActual) && resultado.clave !== claveActual;
  const error = resultado.clave === claveActual ? resultado.error : null;
  const matriz = resultado.clave === claveActual ? resultado.datos : null;

  const reintentar = useCallback(() => setIntento((n) => n + 1), []);

  if (!corteId) {
    return (
      <Vacio
        titulo="Ningún corte seleccionado"
        descripcion="Elige un corte desde el histórico para ver su matriz de relación."
      />
    );
  }

  if (cargando) {
    return <Cargando mensaje="Cargando matriz de relación…" />;
  }

  if (error) {
    return <EstadoError error={error} onReintentar={reintentar} />;
  }

  if (!matriz || matriz.total_filas === 0) {
    return (
      <Vacio
        titulo="Sin datos para mostrar"
        descripcion="Este corte no tiene metas registradas en la matriz de relación."
      />
    );
  }

  return (
    <section className="matriz-relacion">
      <h1>Matriz de relación</h1>

      <div className="matriz-relacion-tabla-contenedor">
        <table className="matriz-relacion-tabla">
          <thead>
            <tr>
              {COLUMNAS.map((columna) => (
                <th key={columna.clave}>{columna.titulo}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matriz.filas.map((fila, indice) => (
              <tr key={`${fila.cod_indicador_producto}-${indice}`}>
                {COLUMNAS.map((columna) => (
                  <td key={columna.clave}>
                    <Celda clave={columna.clave} valor={fila[columna.clave]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
