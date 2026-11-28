import Link from "next/link";

import Marca from "./Marca";
import MenuCuenta from "./MenuCuenta";
import estilos from "./Encabezado.module.css";

/** Barra simple para las pantallas que no llevan el buscador encima. */
export default function Encabezado() {
  return (
    <header className={estilos.barra}>
      <div className={estilos.interna}>
        <Marca />
        {/* Las secciones van aparte de la cuenta: en un celular bajan a su propia fila. */}
        <nav className={estilos.secciones} aria-label="Secciones">
          <Link href="/buscar" className={estilos.buscar}>
            Buscar alojamiento
          </Link>
          <Link href="/salones">Salones</Link>
          <Link href="/excursiones">Excursiones</Link>
          <Link href="/traslados">Traslados</Link>
        </nav>
        <div className={estilos.cuenta}>
          <Link href="/publicar" className={estilos.publicar}>
            Sumá tu alojamiento
          </Link>
          <MenuCuenta />
        </div>
      </div>
    </header>
  );
}
