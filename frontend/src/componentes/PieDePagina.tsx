import Link from "next/link";

import { NOMBRE } from "./Marca";
import estilos from "./PieDePagina.module.css";

/* Los textos legales tienen que estar visibles desde cualquier pantalla
   (docs/01 §5 R11), no solo en el momento de aceptarlos. */
export default function PieDePagina() {
  return (
    <footer className={estilos.pie}>
      <div className={estilos.interno}>
        <p className={estilos.marca}>{NOMBRE}</p>
        <nav>
          <Link href="/buscar">Buscar alojamiento</Link>
          <Link href="/publicar">Sumá tu alojamiento</Link>
          <Link href="/terminos">Términos y condiciones</Link>
          <Link href="/privacidad">Privacidad</Link>
        </nav>
      </div>
    </footer>
  );
}
