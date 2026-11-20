import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, ficha as traerFicha } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import Encabezado from "@/componentes/Encabezado";
import GaleriaFicha from "@/componentes/GaleriaFicha";
import { ICONOS_COMODIDAD, Rayo, Ubicacion } from "@/componentes/Iconos";
import MapaPunto from "@/componentes/MapaPunto";
import PanelReserva from "@/componentes/PanelReserva";
import estilos from "./ficha.module.css";

type Params = { params: Promise<{ slug: string }>; searchParams: Promise<Record<string, string | undefined>> };

function consulta(sp: Record<string, string | undefined>): URLSearchParams {
  const p = new URLSearchParams();
  for (const clave of ["desde", "hasta", "personas", "mascotas"]) {
    const v = sp[clave];
    if (v) p.set(clave, v);
  }
  // Sin las dos fechas el backend no calcula precio: mejor no mandar una sola.
  if (!(p.get("desde") && p.get("hasta"))) {
    p.delete("desde");
    p.delete("hasta");
  }
  return p;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  try {
    const f = await traerFicha(slug);
    return {
      title: `${f.titulo} · ${f.localidad}, ${f.provincia}`,
      description: f.descripcion.slice(0, 160),
      alternates: { canonical: `/alojamiento/${f.slug}` },
    };
  } catch {
    return { title: "Alojamiento" };
  }
}

export default async function Ficha({ params, searchParams }: Params) {
  const { slug } = await params;
  const sp = await searchParams;

  let f;
  try {
    f = await traerFicha(slug, consulta(sp));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const ubicacion = [f.zona, f.localidad, f.provincia].filter(Boolean).join(" · ");

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <nav className={estilos.migas} aria-label="Ubicación en el sitio">
          <Link href="/">Inicio</Link>
          <span aria-hidden="true">/</span>
          <Link href={`/alojamientos-en/${f.localidad_slug}`}>
            Alojamientos en {f.localidad}
          </Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{f.titulo}</span>
        </nav>

        <div className={estilos.titulos}>
          <h1>{f.titulo}</h1>
          <p className={estilos.ubicacion}>
            <Ubicacion className={estilos.iconoChico} />
            {[f.subtipo, ubicacion].filter(Boolean).join(" · ")}
          </p>
          {f.confirmacion_inmediata && (
            <span className={estilos.inmediata}>
              <Rayo />
              Confirmación inmediata
            </span>
          )}
        </div>

        {/* Las fotos subidas por el prestador viven en /media; las de banco, en
            /fotos/demo. Que la ficha tenga las suyas es la señal de que el lugar
            es real y lo provisorio son los números. */}
        {f.es_demo && (
          <AvisoDemo
            variante={
              f.fotos.some((foto) => foto.url.startsWith("/media/")) ? "provisorio" : "ejemplo"
            }
          />
        )}

        <GaleriaFicha fotos={f.fotos} titulo={f.titulo} />

        <div className={estilos.columnas}>
          <div className={estilos.izquierda}>
            <section>
              <h2 className={estilos.subtitulo}>
                {f.subtipo ?? "Alojamiento"} en {f.localidad}
              </h2>
              <p className={estilos.prestador}>
                Lo recibe <strong>{f.prestador.razon_social}</strong>
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
              <h2 className={estilos.subtitulo}>Las unidades</h2>
              <ul className={estilos.unidades}>
                {f.unidades.map((u) => (
                  <li key={u.id}>
                    <div>
                      <p className={estilos.unidadNombre}>{u.nombre}</p>
                      <p className={estilos.unidadDetalle}>
                        Hasta {plural(u.capacidad, "persona", "personas")}
                        {u.capacidad_base && u.capacidad_base < u.capacidad
                          ? ` · ${u.capacidad_base} sin cargo extra`
                          : ""}
                        {u.estadia_minima > 1 && ` · mínimo ${u.estadia_minima} noches`}
                      </p>
                      {(Number(u.cargo_limpieza) > 0 || Number(u.descuento_semanal) > 0) && (
                        <p className={estilos.unidadDetalle}>
                          {Number(u.cargo_limpieza) > 0 &&
                            `Limpieza ${pesos(u.cargo_limpieza)}`}
                          {Number(u.cargo_limpieza) > 0 && Number(u.descuento_semanal) > 0 && " · "}
                          {Number(u.descuento_semanal) > 0 &&
                            `${Number(u.descuento_semanal)}% menos desde 7 noches`}
                        </p>
                      )}
                    </div>
                    {u.tarifa_base && (
                      <p className={estilos.unidadPrecio}>
                        <span className="cifra">{pesos(u.tarifa_base)}</span>
                        <span>tarifa base por noche</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            {(f.reglas_casa || f.hora_ingreso || f.hora_salida) && (
              <section>
                <h2 className={estilos.subtitulo}>Reglas de la casa</h2>
                {(f.hora_ingreso || f.hora_salida) && (
                  <p className={estilos.horarios}>
                    {f.hora_ingreso && `Ingreso desde las ${f.hora_ingreso}`}
                    {f.hora_ingreso && f.hora_salida && " · "}
                    {f.hora_salida && `Salida hasta las ${f.hora_salida}`}
                  </p>
                )}
                {f.reglas_casa && <p className={estilos.descripcion}>{f.reglas_casa}</p>}
              </section>
            )}

            {f.politica_cancelacion && (
              <section>
                <h2 className={estilos.subtitulo}>
                  Cancelación {f.politica_cancelacion.nombre.toLowerCase()}
                </h2>
                <ul className={estilos.tramos}>
                  {f.politica_cancelacion.tramos.map((t) => (
                    <li key={t.dias_antes}>
                      <span className="cifra">
                        {t.dias_antes === 0
                          ? "El mismo día"
                          : `Hasta ${plural(t.dias_antes, "día", "días")} antes`}
                      </span>
                      <span>se devuelve el {t.porcentaje_reintegro}%</span>
                    </li>
                  ))}
                </ul>
                {f.politica_cancelacion.descripcion && (
                  <p className={estilos.nota}>{f.politica_cancelacion.descripcion}</p>
                )}
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

          <PanelReserva ficha={f} />
        </div>
      </main>
    </>
  );
}
