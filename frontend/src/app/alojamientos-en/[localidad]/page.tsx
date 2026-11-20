import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, destino as traerDestino, destinos } from "@/lib/api";
import { hoyISO, pesos, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import BarraBusqueda from "@/componentes/BarraBusqueda";
import Encabezado from "@/componentes/Encabezado";
import { ICONOS_COMODIDAD, Rayo } from "@/componentes/Iconos";
import Paginado from "@/componentes/Paginado";
import estilos from "./destino.module.css";

type Params = {
  params: Promise<{ localidad: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
};

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { localidad } = await params;
  try {
    const d = await traerDestino(localidad);
    return {
      title: `Alojamientos en ${d.localidad}, ${d.provincia}`,
      description: `${d.total} alojamientos publicados en ${d.localidad}, ${d.provincia}. Reservá con precio total a la vista.`,
      alternates: { canonical: `/alojamientos-en/${d.localidad_slug}` },
    };
  } catch {
    return { title: "Destino" };
  }
}

export default async function Destino({ params, searchParams }: Params) {
  const { localidad } = await params;
  const sp = await searchParams;
  const pagina = sp.pagina ?? "1";

  let d;
  try {
    d = await traerDestino(localidad, new URLSearchParams({ pagina }));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const otros = (await destinos().catch(() => [])).filter((x) => x.slug !== d.localidad_slug);
  const desde = hoyISO(21);
  const hasta = hoyISO(24);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <nav className={estilos.migas} aria-label="Ubicación en el sitio">
          <Link href="/">Inicio</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">
            {d.localidad}, {d.provincia}
          </span>
        </nav>

        <div className={estilos.encabezado}>
          <h1>
            Alojamientos en {d.localidad}, {d.provincia}
          </h1>
          <p className={estilos.bajada}>
            {plural(d.total, "alojamiento publicado", "alojamientos publicados")} en el
            departamento {d.localidad}. Elegí las fechas para ver cuáles están libres y cuánto
            salen en total.
          </p>
          {d.zonas.length > 0 && (
            <p className={estilos.zonas}>
              Distritos: <span>{d.zonas.join(" · ")}</span>
            </p>
          )}
        </div>

        <BarraBusqueda
          valores={{
            localidad: d.localidad_slug,
            localidadNombre: d.localidad,
            desde,
            hasta,
            personas: 2,
          }}
        />

        <AvisoDemo />

        {d.publicaciones.length === 0 ? (
          <p className={estilos.vacio}>Todavía no hay alojamientos publicados en este destino.</p>
        ) : (
          <ul className={estilos.grilla}>
            {d.publicaciones.map((p) => (
              <li key={p.publicacion_id}>
                <article className={estilos.tarjeta}>
                  <Link href={`/alojamiento/${p.slug}`} className={estilos.foto}>
                    {p.fotos[0] ? (
                      <img src={p.fotos[0].url} alt={`${p.titulo}, foto principal`} loading="lazy" />
                    ) : (
                      <span className={estilos.sinFoto}>Sin fotos</span>
                    )}
                  </Link>
                  <div className={estilos.cuerpo}>
                    <h2>
                      <Link href={`/alojamiento/${p.slug}`}>{p.titulo}</Link>
                    </h2>
                    <p className={estilos.detalle}>
                      {[p.subtipo, p.zona].filter(Boolean).join(" · ")}
                    </p>
                    <p className={estilos.detalle}>
                      Hasta {plural(p.capacidad_maxima, "persona", "personas")}
                    </p>
                    {p.confirmacion_inmediata && (
                      <p className={estilos.inmediata}>
                        <Rayo />
                        Confirmación inmediata
                      </p>
                    )}
                    {p.comodidades.length > 0 && (
                      <ul className={estilos.comodidades}>
                        {p.comodidades.slice(0, 5).map((codigo) => {
                          const Icono = ICONOS_COMODIDAD[codigo];
                          return Icono ? (
                            <li key={codigo}>
                              <Icono className={estilos.iconoChico} />
                            </li>
                          ) : null;
                        })}
                      </ul>
                    )}
                    {p.tarifa_desde && (
                      <p className={estilos.tarifa}>
                        <span className="cifra">{pesos(p.tarifa_desde)}</span> tarifa base por
                        noche
                      </p>
                    )}
                  </div>
                </article>
              </li>
            ))}
          </ul>
        )}

        <Paginado pagina={d.pagina} paginas={d.paginas} />

        {otros.length > 0 && (
          <section className={estilos.otros}>
            <h2>Otros destinos de {d.provincia}</h2>
            <ul>
              {otros.slice(0, 12).map((x) => (
                <li key={x.slug}>
                  <Link href={`/alojamientos-en/${x.slug}`}>
                    {x.nombre}
                    <span className="cifra">{x.publicaciones}</span>
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
