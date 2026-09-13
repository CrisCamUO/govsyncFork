/**
 * Enrutamiento de la aplicación.
 *
 * TARJETA: [UX-01] Layout base, enrutamiento y cliente HTTP
 *
 * Las rutas se agregan a medida que existen sus pantallas. Mientras tanto se
 * muestra un marcador de posición: así `npm run dev` arranca y confirma que la
 * cadena de herramientas funciona, sin fingir que la pantalla ya está hecha.
 */
import { Route, Routes } from "react-router-dom";

import Disposicion from "./components/Disposicion.jsx";

function Pendiente() {
  return (
    <section
      style={{ maxWidth: 640, margin: "4rem auto", padding: "0 1.5rem" }}
    >
      <h1>GovSync</h1>
      <p className="apagado">
        Esqueleto del Sprint 1. Las pantallas se implementan según
        <code> PLAN-DE-TRABAJO.md</code>.
      </p>
      <p>
        Backend:{" "}
        <a href="http://localhost:8000/docs">http://localhost:8000/docs</a>
      </p>
    </section>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Disposicion />}>
        {/* TODO [HU-01][FE-02] <Route path="/cortes" element={<Cortes />} /> */}
        {/* TODO [HU-01][FE-02] <Route path="/cortes/nuevo" element={<NuevoCorte />} /> */}
        {/* TODO [HU-07][FE-02] <Route path="/matriz/:corteId?" element={<MatrizRelacion />} /> */}
        <Route path="*" element={<Pendiente />} />
      </Route>
    </Routes>
  );
}
