import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, fichaExcursion } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import Encabezado from "@/componentes/Encabezado";
import GaleriaFicha from "@/componentes/GaleriaFicha";
import { ICONOS_COMODIDAD, Ubicacion } from "@/componentes/Iconos";
import MapaPunto from "@/componentes/MapaPunto";
import ReservaExcursion from "@/componentes/ReservaExcursion";
import estilos from "@/app/alojamiento/[slug]/ficha.module.css";

type Params = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
};

const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"];

function cuando(dias: number[]): string {
  if (dias.length === 7) return "Todos los días";
  const nombres = dias.map((d) => DIAS[d]);
  const texto =
    nombres.length === 1
      ? nombres[0]
      : `${nombres.slice(0, -1).join(", ")} y ${nombres[nombres.length - 1]}`;
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function duracion(minutos: number): string {
  if (minutos % (24 * 60) === 0) return plural(minutos / (24 * 60), "día", "días");
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h && m ? `${h} h ${m} min` : h ? `${h} h` : `${m} min`;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  try {
    const f = await fichaExcursion(slug);
    return {
      title: `${f.titulo} · Excursión en ${f.localidad}, ${f.provincia}`,
      description: f.descripcion.slice(0, 160),
      alternates: { canonical: `/excursion/${f.slug}` },
    };
  } catch {
    return { title: "Excursión" };
  }
}

export default async function FichaExcursion({ params, searchParams }: Params) {
  const { slug } = await params;
  const sp = await searchParams;

  let f;
  try {
    f = await fichaExcursion(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const ubicacion = [f.zona, f.localidad, f.provincia].filter(Boolean).join(" · ");
  const fecha = /^\d{4}-\d{2}-\d{2}$/.test(sp.fecha ?? "") ? sp.fecha! : "";
  const personas = Number(sp.personas) > 0 ? Math.min(Number(sp.personas), 500) : 0;

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <nav className={estilos.migas} aria-label="Ubicación en el sitio">
          <Link href="/">Inicio</Link>
          <span aria-hidden="true">/</span>
          <Link href={`/excursiones?localidad=${f.localidad_slug}`}>
            Excursiones en {f.localidad}
          </Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{f.titulo}</span>
        </nav>

        <div className={estilos.titulos}>
          <h1>{f.titulo}</h1>
          <p className={estilos.ubicacion}>
            <Ubicacion className={estilos.iconoChico} />
            {[f.subtipo ?? "Excursión", ubicacion].filter(Boolean).join(" · ")}
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
              <h2 className={estilos.subtitulo}>
                {f.subtipo ?? "Excursión"} en {f.localidad}
              </h2>
              <p className={estilos.prestador}>
                La organiza <strong>{f.prestador.razon_social}</strong>
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
              <h2 className={estilos.subtitulo}>Horarios y precios</h2>
              <ul className={estilos.unidades}>
                {f.actividades.map((a) => (
                  <li key={a.id}>
                    <div>
                      {f.actividades.length > 1 && <p className={estilos.unidadNombre}>{a.nombre}</p>}
                      {a.turnos.map((t) => (
                        <p key={`${t.nombre}-${t.hora_inicio}`} className={estilos.unidadDetalle}>
                          {cuando(t.dias_semana)}, a las {t.hora_inicio} h ·{" "}
                          {duracion(t.duracion_minutos)}
                          {t.minimo_personas > 1 ? ` · sale con al menos ${t.minimo_personas}` : ""}
                        </p>
                      ))}
                      {a.turnos.length === 0 && (
                        <p className={estilos.unidadDetalle}>Salidas especiales: mirá las fechas al reservar.</p>
                      )}
                      {a.precios.map((c) => (
                        <p key={c.id} className={estilos.unidadDetalle}>
                          {c.nombre}
                          {c.descripcion ? ` (${c.descripcion})` : ""}:{" "}
                          <span className="cifra">
                            {Number(c.precio) === 0 ? "gratis" : pesos(c.precio)}
                          </span>
                        </p>
                      ))}
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
                  Para reservar se paga una seña del {f.porcentaje_sena}% online; el resto se
                  arregla con quien organiza.
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
              <p className={estilos.nota}>
                Si la salida no va —se suspende o no se llega al mínimo de personas— se
                cancela tu reserva y se te devuelve el {f.reintegro_si_no_sale}% de lo pagado.
              </p>
            </section>

            {f.alojamientos_del_anfitrion.length > 0 && (
              <section>
                <h2 className={estilos.subtitulo}>Dónde quedarse</h2>
                <p className={estilos.descripcion}>
                  Quien organiza también tiene alojamiento:{" "}
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
                <h2 className={estilos.subtitulo}>Dónde es</h2>
                <p className={estilos.descripcion}>{ubicacion}</p>
                <div className={estilos.mapa}>
                  <MapaPunto lat={f.lat} lon={f.lon} etiqueta={f.titulo} />
                </div>
                <p className={estilos.nota}>
                  El punto de encuentro exacto se comparte al confirmar la reserva.
                </p>
              </section>
            )}
          </div>

          <ReservaExcursion ficha={f} fechaInicial={fecha} personasInicial={personas} />
        </div>
      </main>
    </>
  );
}
