import Link from "next/link";

import { destinos } from "@/lib/api";
import { hoyISO, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import BarraBusqueda from "@/componentes/BarraBusqueda";
import Marca from "@/componentes/Marca";
import MenuCuenta from "@/componentes/MenuCuenta";
import { Ubicacion } from "@/componentes/Iconos";
import estilos from "./page.module.css";

export default async function Inicio() {
  const desde = hoyISO(21);
  const hasta = hoyISO(24);
  const populares = await destinos().catch(() => []);

  return (
    <>
      <header className={estilos.barra}>
        <div className={estilos.barraInterna}>
          <Marca />
          <div className={estilos.acciones}>
            <Link href="/publicar" className={estilos.publicar}>
              Sumá tu alojamiento
            </Link>
            <MenuCuenta />
          </div>
        </div>
      </header>

      <main>
        <section className={estilos.hero}>
          <div className={estilos.heroInterno}>
            <h1 className={estilos.titulo}>
              Encontrá dónde quedarte, reservá con quien te recibe.
            </h1>
            <p className={estilos.bajada}>
              Alojamientos de todo el país, con el precio total a la vista antes de pagar.
            </p>
            <BarraBusqueda valores={{ desde, hasta, personas: 2 }} />
          </div>
        </section>

        {populares.length > 0 && (
          <section className={estilos.destinos}>
            <h2 className={estilos.subtitulo}>Destinos con alojamientos publicados</h2>
            <div className={estilos.aviso}>
              <AvisoDemo />
            </div>
            <ul>
              {populares.slice(0, 12).map((d) => (
                <li key={d.slug}>
                  <Link href={`/alojamientos-en/${d.slug}`}>
                    <Ubicacion className={estilos.icono} />
                    <span>
                      <strong>{d.nombre}</strong>
                      <span className={estilos.provincia}>{d.provincia}</span>
                    </span>
                    <span className={`${estilos.cuenta} cifra`}>
                      {plural(d.publicaciones, "alojamiento", "alojamientos")}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </>
  );
}
