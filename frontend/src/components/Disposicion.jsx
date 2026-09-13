/**
 * Layout base de GovSync.
 *
 * TARJETA: [UX-01] Layout base, enrutamiento y cliente HTTP
 *
 * Define la estructura común de navegación y el área donde React Router
 * renderiza cada pantalla.
 */
import { NavLink, Outlet } from "react-router-dom";

export default function Disposicion() {
  return (
    <>
      <header>
        <nav aria-label="Navegación principal">
          <NavLink to="/" end>
            GovSync
          </NavLink>

          <NavLink to="/cortes/nuevo">Crear corte</NavLink>
          <NavLink to="/cortes">Cortes</NavLink>
          <NavLink to="/matriz">Matriz</NavLink>
        </nav>
      </header>

      <main>
        <Outlet />
      </main>
    </>
  );
}
