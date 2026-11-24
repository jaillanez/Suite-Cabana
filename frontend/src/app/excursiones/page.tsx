import type { Metadata } from "next";
import Link from "next/link";

import { ApiError, buscarExcursiones, destinosExcursiones } from "@/lib/api";
import { diaAR, diaMesAnio, horaAR, hoyISO, pesos } from "@/lib/formato";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../salones/salones.module.css";

export const metadata: Metadata = {
  title: "Excursiones y actividades",
  description:
    "Cabalgatas, trekking, visitas a bodegas y paseos guiados: elegí la salida, mirá el precio por persona y reservá online.",
  alternates: { canonical: "/excursiones" },
};

type Props = { searchParams: Promise<Record<string, string | undefined>> };

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

export default async function Excursiones({ searchParams }: Props) {
  const sp = await searchParams;
  const localidad = sp.localidad ?? "";
  const fecha = FECHA.test(sp.fecha ?? "") && sp.fecha! >= hoyISO() ? sp.fecha! : "";
  const personas = Number(sp.personas) > 0 ? Math.min(Number(sp.personas), 500) : 0;

  const params = new URLSearchParams();
  if (localidad) params.set("localidad", localidad);
  if (fecha) params.set("fecha", fecha);
  if (personas) params.set("personas", String(personas));
  if (sp.pagina) params.set("pagina", sp.pagina);

  const [destinos, resultado] = await Promise.all([
    destinosExcursiones().catch(() => []),
    buscarExcursiones(params).catch((e) => {
      if (e instanceof ApiError) return null;
      throw e;
    }),
  ]);

  // Lo que se pidió viaja a la ficha: el panel arranca con el día y las personas.
  const aFicha = new URLSearchParams();
  if (fecha) aFicha.set("fecha", fecha);
  if (personas) aFicha.set("personas", String(personas));
  const sufijo = aFicha.size ? `?${aFicha}` : "";

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <header className={estilos.cabecera}>
          <h1>Excursiones y actividades</h1>
          <p>
            Cabalgatas, trekking, visitas a bodegas y paseos guiados. Elegí la
            salida y reservá tu lugar.
          </p>
        </header>

        <form className={estilos.buscador} method="get" action="/excursiones">
          <label>
            <span>Dónde</span>
            <select name="localidad" defaultValue={localidad}>
              <option value="">Todos los destinos</option>
              {destinos.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.nombre} · {d.provincia}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Día</span>
            <input type="date" name="fecha" defaultValue={fecha} min={hoyISO()} max={hoyISO(365)} />
          </label>
          <label>
            <span>Personas</span>
            <input
              type="number"
              name="personas"
              min={1}
              max={500}
              defaultValue={personas || ""}
              placeholder="Cuántas"
            />
          </label>
          <button type="submit">Buscar</button>
        </form>

        {resultado === null ? (
          <p className={estilos.vacio}>No pudimos buscar con esos datos. Revisá el día.</p>
        ) : resultado.total === 0 ? (
          <div className={estilos.vacio}>
            <h2>
              No encontramos excursiones{" "}
              {fecha ? `con lugar el ${diaMesAnio(fecha)}` : "con eso"}
            </h2>
            <p>
              Probá con otro día, menos personas u otro destino.{" "}
              {(fecha || personas || localidad) && <Link href="/excursiones">Ver todas</Link>}
            </p>
          </div>
        ) : (
          <>
            <p className={estilos.cuenta}>
              <span className="cifra">{resultado.total}</span>{" "}
              {resultado.total === 1 ? "excursión" : "excursiones"}
              {fecha ? ` con lugar el ${diaMesAnio(fecha)}` : ""}
            </p>
            <ul className={estilos.grilla}>
              {resultado.resultados.map((x) => (
                <li key={x.slug}>
                  <Link href={`/excursion/${x.slug}${sufijo}`} className={estilos.tarjeta}>
                    <span className={estilos.foto}>
                      {x.fotos[0] ? (
                        <img src={x.fotos[0].url} alt="" loading="lazy" />
                      ) : (
                        <span className={estilos.sinFoto}>Sin fotos todavía</span>
                      )}
                      {x.es_demo && <span className={estilos.demo}>Ejemplo</span>}
                    </span>
                    <span className={estilos.datos}>
                      <strong>{x.titulo}</strong>
                      <span className={estilos.lugar}>
                        {[x.subtipo, x.localidad].filter(Boolean).join(" · ")}
                      </span>
                      <span className={estilos.capacidad}>
                        {x.proxima_salida
                          ? fecha
                            ? `${x.salidas_del_dia === 1 ? "Sale" : `${x.salidas_del_dia} salidas,`} desde las ${horaAR(x.proxima_salida)} h`
                            : `Próxima salida: ${diaAR(x.proxima_salida)}, ${horaAR(x.proxima_salida)} h`
                          : "Sin salidas en los próximos dos meses"}
                      </span>
                      {x.precio_desde && (
                        <span className={estilos.precio}>
                          {Number(x.precio_desde.monto) === 0 ? (
                            <strong>Gratis</strong>
                          ) : (
                            <>
                              Desde{" "}
                              <strong className="cifra">{pesos(x.precio_desde.monto)}</strong>{" "}
                              {x.precio_desde.detalle}
                            </>
                          )}
                        </span>
                      )}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            {resultado.paginas > 1 && (
              <nav className={estilos.paginas} aria-label="Páginas">
                {Array.from({ length: resultado.paginas }, (_, i) => i + 1).map((n) => {
                  const p = new URLSearchParams(params);
                  p.set("pagina", String(n));
                  return (
                    <Link
                      key={n}
                      href={`/excursiones?${p}`}
                      aria-current={n === resultado.pagina ? "page" : undefined}
                    >
                      {n}
                    </Link>
                  );
                })}
              </nav>
            )}
          </>
        )}
      </main>
    </>
  );
}
