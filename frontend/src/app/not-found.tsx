import Link from "next/link";

import Encabezado from "@/componentes/Encabezado";
import estilos from "./no-encontrado.module.css";

export default function NoEncontrado() {
  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <p className={estilos.codigo}>404</p>
        <h1>No encontramos esa página</h1>
        <p className={estilos.cuerpo}>
          Puede que el alojamiento ya no esté publicado, o que el enlace esté mal escrito.
        </p>
        <Link href="/buscar" className={estilos.accion}>
          Buscar alojamiento
        </Link>
      </main>
    </>
  );
}
