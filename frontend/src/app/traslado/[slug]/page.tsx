import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, fichaTraslado, type VehiculoFicha } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import Encabezado from "@/componentes/Encabezado";
import GaleriaFicha from "@/componentes/GaleriaFicha";
import { ICONOS_COMODIDAD, Ubicacion } from "@/componentes/Iconos";
import MapaPunto from "@/componentes/MapaPunto";
import ReservaTraslado from "@/componentes/ReservaTraslado";
import estilos from "@/app/alojamiento/[slug]/ficha.module.css";

type Params = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
};

function duracion(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h && m ? `${h} h ${m} min` : h ? `${h} h` : `${m} min`;
}

const entero = (v: string | undefined, maximo: number) =>
  Number(v) > 0 ? Math.min(Math.floor(Number(v)), maximo) : 0;

function porKm(v: VehiculoFicha): string | null {
  if (!v.por_km) return null;
  const partes = [`${pesos(v.por_km.precio_km)} por km`];
  if (Number(v.por_km.bajada) > 0) partes.push(`más ${pesos(v.por_km.bajada)} de bajada`);
  if (Number(v.por_km.minimo) > 0) partes.push(`mínimo ${pesos(v.por_km.minimo)}`);
  if (v.por_km.radio_km) partes.push(`hasta ${v.por_km.radio_km} km`);
  return `A cualquier dirección: ${partes.join(", ")}`;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  try {
    const f = await fichaTraslado(slug);
    return {
      title: `${f.titulo} · Traslados en ${f.localidad}, ${f.provincia}`,
      description: f.descripcion.slice(0, 160),
      alternates: { canonical: `/traslado/${f.slug}` },
    };
  } catch {
    return { title: "Traslado" };
  }
}

export default async function FichaTraslado({ params, searchParams }: Params) {
  const { slug } = await params;
  const sp = await searchParams;

  let f;
  try {
    f = await fichaTraslado(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const ubicacion = [f.localidad, f.provincia].filter(Boolean).join(" · ");
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(sp.dia ?? "") ? sp.dia! : "";

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <nav className={estilos.migas} aria-label="Ubicación en el sitio">
          <Link href="/">Inicio</Link>
          <span aria-hidden="true">/</span>
          <Link href={`/traslados?localidad=${f.localidad_slug}`}>
            Traslados en {f.localidad}
          </Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{f.titulo}</span>
        </nav>

        <div className={estilos.titulos}>
          <h1>{f.titulo}</h1>
          <p className={estilos.ubicacion}>
            <Ubicacion className={estilos.iconoChico} />
            {[f.subtipo ?? "Traslados", ubicacion].filter(Boolean).join(" · ")}
          </p>
        </div>

        {f.es_demo && (
          <AvisoDemo
            variante={f.fotos.some((foto) => foto.url.startsWith("/media/")) ? "provisorio" : "ejemplo"}
          />
        )}

        <GaleriaFicha fotos={f.fotos} titulo={f.titulo} />

        <div className={estilos.columnas}>
          <div className={estilos.izquierda}>
            <section>
              <h2 className={estilos.subtitulo}>Traslados en {f.localidad}</h2>
              <p className={estilos.prestador}>
                Los hace <strong>{f.prestador.razon_social}</strong>
                {f.prestador.verificado && <span className={estilos.verificado}>Verificado</span>}
                <span className={estilos.desde}>Publica desde {f.prestador.publica_desde}</span>
              </p>
              <p className={estilos.descripcion}>{f.descripcion}</p>
            </section>

            {f.comodidades.length > 0 && (
              <section>
                <h2 className={estilos.subtitulo}>Qué incluye</h2>
                <ul className={estilos.comodidades}>
                  {f.comodidades.map((c) => {
                    const Icono = ICONOS_COMODIDAD[c.codigo];
                    return (
                      <li key={c.codigo}>
                        {Icono ? <Icono className={estilos.iconoChico} /> : null}
                        {c.nombre}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            <section>
              <h2 className={estilos.subtitulo}>Vehículos y precios</h2>
              <ul className={estilos.unidades}>
                {f.vehiculos.map((v) => (
                  <li key={v.id}>
                    <div>
                      <p className={estilos.unidadNombre}>{v.nombre}</p>
                      <p className={estilos.unidadDetalle}>
                        {plural(v.pasajeros, "pasajero", "pasajeros")}
                        {v.valijas != null ? ` · ${plural(v.valijas, "valija", "valijas")}` : ""}
                      </p>
                      {v.recorridos.map((r) => (
                        <p key={`${r.origen}-${r.destino}`} className={estilos.unidadDetalle}>
                          {r.origen} {r.ambos_sentidos ? "↔" : "→"} {r.destino}:{" "}
                          <span className="cifra">{pesos(r.precio)}</span>
                          {r.por_persona ? " por persona" : " el viaje"} · {duracion(r.duracion_minutos)}
                        </p>
                      ))}
                      {porKm(v) && <p className={estilos.unidadDetalle}>{porKm(v)}</p>}
                      {v.recargo_nocturno && (
                        <p className={estilos.unidadDetalle}>
                          De {v.recargo_nocturno.desde} a {v.recargo_nocturno.hasta} h, recargo del{" "}
                          {Number(v.recargo_nocturno.porcentaje)}%
                        </p>
                      )}
                      <p className={estilos.unidadDetalle}>
                        Se reserva con {plural(v.anticipacion_minima_horas, "hora", "horas")} de
                        anticipación
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {f.para_tener_en_cuenta && (
              <section>
                <h2 className={estilos.subtitulo}>Para tener en cuenta</h2>
                <p className={estilos.descripcion}>{f.para_tener_en_cuenta}</p>
              </section>
            )}

            <section>
              <h2 className={estilos.subtitulo}>Cancelación</h2>
              {f.porcentaje_sena && (
                <p className={estilos.descripcion}>
                  Para reservar se paga una seña del {f.porcentaje_sena}% online; el resto se le
                  paga al chofer.
                </p>
              )}
              {f.politica_cancelacion && f.politica_cancelacion.tramos.length > 0 ? (
                <ul className={estilos.tramos}>
                  {f.politica_cancelacion.tramos.map((t) => (
                    <li key={t.dias_antes}>
                      <span className="cifra">
                        {t.dias_antes === 0
                          ? "El mismo día"
                          : `Hasta ${plural(t.dias_antes, "día", "días")} antes`}
                      </span>
                      <span>se devuelve el {t.porcentaje_reintegro}% de lo pagado</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={estilos.descripcion}>Si cancelás, no hay reintegro.</p>
              )}
            </section>

            {f.alojamientos_del_anfitrion.length > 0 && (
              <section>
                <h2 className={estilos.subtitulo}>Dónde quedarse</h2>
                <p className={estilos.descripcion}>
                  Quien hace los traslados también tiene alojamiento:{" "}
                  {f.alojamientos_del_anfitrion.map((a, i) => (
                    <span key={a.slug}>
                      {i > 0 && ", "}
                      <Link href={`/alojamiento/${a.slug}`}>{a.titulo}</Link>
                    </span>
                  ))}
                  .
                </p>
              </section>
            )}

            {f.lat !== null && f.lon !== null && (
              <section>
                <h2 className={estilos.subtitulo}>Dónde trabaja</h2>
                <p className={estilos.descripcion}>{ubicacion}</p>
                <div className={estilos.mapa}>
                  <MapaPunto lat={f.lat} lon={f.lon} etiqueta={f.titulo} />
                </div>
              </section>
            )}
          </div>

          <ReservaTraslado
            ficha={f}
            pasajerosInicial={entero(sp.pasajeros, 100)}
            valijasInicial={entero(sp.valijas, 200)}
            diaInicial={dia}
          />
        </div>
      </main>
    </>
  );
}
