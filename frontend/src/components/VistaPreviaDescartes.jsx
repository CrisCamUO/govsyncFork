/**
 * Vista previa de códigos descartados al cargar la plantilla BPIN.
 *
 * TARJETA: [HU-04][FE-03] Vista previa de códigos extraídos y descartados
 * CUBRE: CA-4, CA-5
 *
 * «Los descartes son la información más valiosa de esta pantalla»
 * (comentario del propio lector, `proyectos.py`) — por eso prioriza en vez
 * de mostrar una lista plana: D14 (docs/DECISIONES.md) clasifica cada
 * descarte por `categoria`, distinguiendo un intento real de código que
 * falló (`POSIBLE_CERO_PERDIDO`/`LONGITUD_LARGA`) de ruido de texto libre —
 * una fecha, un año, un porcentaje — que nunca pretendió ser un código
 * (`LONGITUD_CORTA`).
 *
 * PROPS, NO CONSUMO DE API: recibe `descartes` ya resuelto (la respuesta de
 * `POST /cortes/{id}/archivos/PROYECTOS`, campo `descartes` — ver
 * `ArchivoFuenteRespuestaParcial`/`DescarteRespuesta` en
 * `cortes/api/router.py`). Este componente no llama a `api.cargarArchivo`;
 * quien construya el flujo de carga (Paso 2 de `NuevoCorte.jsx`,
 * [HU-04][FE-02]) es quien decide cuándo pasarle el resultado, igual que ya
 * hace `CargaDeArchivo.jsx` con su prop `resultado`.
 *
 * Se integra pasando el `<VistaPreviaDescartes descartes={...} />` que
 * devuelve como la prop `resultado` de `CargaDeArchivo` cuando
 * `tipo === "PROYECTOS"` — sin que este componente conozca nada de
 * `CargaDeArchivo` ni de `NuevoCorte.jsx`.
 */

// PROPUESTA DE TEXTO, NO DECIDIDA — verificado contra PLANDETRABAJO.md,
// ESPECIFICACIONES_TECNICAS.md y DECISIONES.md: ninguno define copy de
// interfaz para estas tres categorías (D14 solo las nombra a nivel técnico:
// POSIBLE_CERO_PERDIDO/LONGITUD_CORTA/LONGITUD_LARGA). Estos tres títulos
// los redacté yo mismo para que el componente fuera demostrable — quien
// revise esta pantalla con la administradora (o Emilse, si hay oportunidad)
// debería poder cambiarlos sin que se sienta como tocar código terminado.
const ETIQUETAS_CATEGORIA = {
  posible_cero_perdido: {
    titulo: "Posible código con el cero perdido",
    prioridad: "alta",
  },
  longitud_larga: {
    titulo: "Posible código mal formado",
    prioridad: "alta",
  },
  longitud_corta: {
    titulo: "Probablemente no es un código",
    prioridad: "baja",
  },
};

function agruparPorCategoria(descartes) {
  const grupos = new Map();
  for (const descarte of descartes) {
    const clave = descarte.categoria;
    if (!grupos.has(clave)) {
      grupos.set(clave, []);
    }
    grupos.get(clave).push(descarte);
  }
  // Prioridad alta primero: es la información más valiosa de la pantalla.
  return [...grupos.entries()].sort(([a], [b]) => {
    const prioridadA = ETIQUETAS_CATEGORIA[a]?.prioridad === "alta" ? 0 : 1;
    const prioridadB = ETIQUETAS_CATEGORIA[b]?.prioridad === "alta" ? 0 : 1;
    return prioridadA - prioridadB;
  });
}

export default function VistaPreviaDescartes({ descartes }) {
  if (!descartes || descartes.length === 0) {
    return null;
  }

  const grupos = agruparPorCategoria(descartes);

  return (
    <div className="vista-previa-descartes">
      {/* Propuesta de texto, no decidida — mismo caso que ETIQUETAS_CATEGORIA arriba. */}
      <p className="vista-previa-descartes-resumen">
        {descartes.length === 1
          ? "1 fragmento descartado — revísalo antes de continuar."
          : `${descartes.length} fragmentos descartados — revísalos antes de continuar.`}
      </p>

      {grupos.map(([categoria, items]) => {
        const etiqueta = ETIQUETAS_CATEGORIA[categoria] ?? {
          titulo: categoria,
          prioridad: "baja",
        };
        return (
          <section
            key={categoria}
            className="vista-previa-descartes-grupo"
            data-prioridad={etiqueta.prioridad}
          >
            <h3>{etiqueta.titulo}</h3>
            <ul>
              {items.map((descarte, indice) => (
                <li key={`${descarte.valor_crudo}-${indice}`}>
                  <span className="codigo">{descarte.valor_crudo}</span>
                  <span className="vista-previa-descartes-motivo">
                    {descarte.motivo}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
