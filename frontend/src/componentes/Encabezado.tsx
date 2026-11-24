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
        <nav>
          <Link href="/buscar">Buscar alojamiento</Link>
          <Link href="/salones">Salones</Link>
          <Link href="/excursiones">Excursiones</Link>
          <Link href="/publicar" className={estilos.publicar}>
            Sumá tu alojamiento
          </Link>
          <MenuCuenta />
        </nav>
      </div>
    </header>
  );
}
