import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, fichaSalon } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import Encabezado from "@/componentes/Encabezado";
import GaleriaFicha from "@/componentes/GaleriaFicha";
import { ICONOS_COMODIDAD, Ubicacion } from "@/componentes/Iconos";
import MapaPunto from "@/componentes/MapaPunto";
import ReservaSalon from "@/componentes/ReservaSalon";
import estilos from "@/app/alojamiento/[slug]/ficha.module.css";

type Params = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
};

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  try {
    const f = await fichaSalon(slug);
    return {
      title: `${f.titulo} · Salón en ${f.localidad}, ${f.provincia}`,
      description: f.descripcion.slice(0, 160),
      alternates: { canonical: `/salon/${f.slug}` },
    };
  } catch {
    return { title: "Salón de eventos" };
  }
}

export default async function FichaSalon({ params, searchParams }: Params) {
  const { slug } = await params;
  const sp = await searchParams;

  let f;
  try {
    f = await fichaSalon(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const ubicacion = [f.zona, f.localidad, f.provincia]
    .filter(Boolean)
    .join(" · ");
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(sp.dia ?? "") ? sp.dia! : "";
  const invitados = Number(sp.invitados) > 0 ? Number(sp.invitados) : 0;

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <nav className={estilos.migas} aria-label="Ubicación en el sitio">
          <Link href="/">Inicio</Link>
          <span aria-hidden="true">/</span>
          <Link href={`/salones?localidad=${f.localidad_slug}`}>
            Salones en {f.localidad}
          </Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{f.titulo}</span>
        </nav>

        <div className={estilos.titulos}>
          <h1>{f.titulo}</h1>
          <p className={estilos.ubicacion}>
            <Ubicacion className={estilos.iconoChico} />
            {[f.subtipo ?? "Salón de eventos", ubicacion]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>

        {f.es_demo && (
          <AvisoDemo
            variante={
              f.fotos.some((foto) => foto.url.startsWith("/media/"))
                ? "provisorio"
                : "ejemplo"
            }
          />
        )}

        <GaleriaFicha fotos={f.fotos} titulo={f.titulo} />

        <div className={estilos.columnas}>
          <div className={estilos.izquierda}>
            <section>
              <h2 className={estilos.subtitulo}>
                {f.subtipo ?? "Salón"} para eventos en {f.localidad}
              </h2>
              <p className={estilos.prestador}>
                Lo ofrece <strong>{f.prestador.razon_social}</strong>
                {f.prestador.verificado && (
                  <span className={estilos.verificado}>Verificado</span>
                )}
                <span className={estilos.desde}>
                  Publica desde {f.prestador.publica_desde}
                </span>
              </p>
              <p className={estilos.descripcion}>{f.descripcion}</p>
            </section>

            {f.comodidades.length > 0 && (
              <section>
                <h2 className={estilos.subtitulo}>Qué tiene</h2>
                <ul className={estilos.comodidades}>
                  {f.comodidades.map((c) => {
                    const Icono = ICONOS_COMODIDAD[c.codigo];
                    return (
                      <li key={c.codigo}>
                        {Icono ? (
                          <Icono className={estilos.iconoChico} />
                        ) : null}
                        {c.nombre}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            <section>
              <h2 className={estilos.subtitulo}>
                {f.espacios.length === 1 ? "El espacio" : "Los espacios"}
              </h2>
              <ul className={estilos.unidades}>
                {f.espacios.map((e) => (
                  <li key={e.id}>
                    <div>
                      <p className={estilos.unidadNombre}>{e.nombre}</p>
                      <p className={estilos.unidadDetalle}>
                        Hasta {plural(e.capacidad, "persona", "personas")} de
                        pie
                        {e.capacidad_sentados
                          ? ` · ${e.capacidad_sentados} sentadas`
                          : ""}
                        {e.capacidad_base && Number(e.cargo_persona_extra) > 0
                          ? ` · ${e.capacidad_base} incluidas, ${pesos(
                              e.cargo_persona_extra,
                            )} por invitado extra`
                          : ""}
                      </p>
                      {e.franjas.map((t) => (
                        <p key={t.id} className={estilos.unidadDetalle}>
                          {t.nombre}: {t.hora_inicio} a {t.hora_fin} h
                          {t.termina_al_dia_siguiente
                            ? " (del día siguiente)"
                            : ""}{" "}
                          · <span className="cifra">{pesos(t.precio)}</span>
                        </p>
                      ))}
                      {e.por_horas && (
                        <p className={estilos.unidadDetalle}>
                          Por horas, de {e.por_horas.hora_apertura} a{" "}
                          {e.por_horas.hora_cierre} h · mínimo{" "}
                          {e.por_horas.horas_minimas} h
                        </p>
                      )}
                    </div>
                    {e.por_horas && (
                      <p className={estilos.unidadPrecio}>
                        <span className="cifra">
                          {pesos(e.por_horas.precio_hora)}
                        </span>
                        <span>la hora</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            {f.reglas && (
              <section>
                <h2 className={estilos.subtitulo}>Reglas del lugar</h2>
                <p className={estilos.descripcion}>{f.reglas}</p>
              </section>
            )}

            {(f.porcentaje_sena || f.politica_cancelacion) && (
              <section>
                <h2 className={estilos.subtitulo}>Seña y cancelación</h2>
                {f.porcentaje_sena && (
                  <p className={estilos.descripcion}>
                    Para reservar se paga una seña del {f.porcentaje_sena}%
                    online; el resto se arregla con el anfitrión.
                  </p>
                )}
                {f.politica_cancelacion && (
                  <>
                    <ul className={estilos.tramos}>
                      {f.politica_cancelacion.tramos.map((t) => (
                        <li key={t.dias_antes}>
                          <span className="cifra">
                            {t.dias_antes === 0
                              ? "El mismo día"
                              : `Hasta ${plural(t.dias_antes, "día", "días")} antes`}
                          </span>
                          <span>
                            se devuelve el {t.porcentaje_reintegro}% de lo
                            pagado
                          </span>
                        </li>
                      ))}
                    </ul>
                    {f.politica_cancelacion.descripcion && (
                      <p className={estilos.nota}>
                        {f.politica_cancelacion.descripcion}
                      </p>
                    )}
                  </>
                )}
              </section>
            )}

            {f.alojamientos_del_anfitrion.length > 0 && (
              <section>
                <h2 className={estilos.subtitulo}>Para quedarse a dormir</h2>
                <p className={estilos.descripcion}>
                  El mismo anfitrión tiene alojamiento:{" "}
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
                <h2 className={estilos.subtitulo}>Dónde queda</h2>
                <p className={estilos.descripcion}>{ubicacion}</p>
                <div className={estilos.mapa}>
                  <MapaPunto lat={f.lat} lon={f.lon} etiqueta={f.titulo} />
                </div>
                <p className={estilos.nota}>
                  La dirección exacta se comparte al confirmar la reserva.
                </p>
              </section>
            )}
          </div>

          <ReservaSalon
            ficha={f}
            diaInicial={dia}
            invitadosInicial={invitados}
          />
        </div>
      </main>
    </>
  );
}
