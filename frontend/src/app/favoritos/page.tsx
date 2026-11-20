import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { misFavoritos } from "@/lib/api";
import { plural } from "@/lib/formato";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import BotonFavorito from "@/componentes/BotonFavorito";
import Encabezado from "@/componentes/Encabezado";
import estilos from "./favoritos.module.css";

export const metadata: Metadata = { title: "Favoritos", robots: { index: false } };

export default async function Favoritos() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/favoritos");
  const token = (await tokenActual())!;
  const guardados = await misFavoritos(token).catch(() => []);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Guardados</h1>
        {guardados.length === 0 ? (
          <div className={estilos.vacio}>
            <h2>Todavía no guardaste ninguno</h2>
            <p>
              Tocá el corazón de cualquier alojamiento en los resultados y lo vas a encontrar
              acá.
            </p>
            <Link href="/buscar" className={estilos.accion}>
              Buscar alojamiento
            </Link>
          </div>
        ) : (
          <ul className={estilos.grilla}>
            {guardados.map((f) => (
              <li key={f.publicacion_id}>
                <article className={estilos.tarjeta}>
                  <div className={estilos.foto}>
                    <Link href={`/alojamiento/${f.slug}`}>
                      {f.fotos[0] ? (
                        <img src={f.fotos[0].url} alt={`${f.titulo}, foto`} loading="lazy" />
                      ) : (
                        <span className={estilos.sinFoto}>Sin fotos</span>
                      )}
                    </Link>
                    <BotonFavorito publicacionId={f.publicacion_id} inicial />
                  </div>
                  <h2>
                    <Link href={`/alojamiento/${f.slug}`}>{f.titulo}</Link>
                  </h2>
                  <p className={estilos.detalle}>
                    {[f.subtipo, f.localidad, f.provincia].filter(Boolean).join(" · ")}
                  </p>
                  <p className={estilos.detalle}>
                    Hasta {plural(f.capacidad_maxima, "persona", "personas")}
                  </p>
                </article>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
