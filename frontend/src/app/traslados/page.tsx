import type { Metadata } from "next";
import Link from "next/link";

import { ApiError, buscarTraslados, destinosTraslados } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../salones/salones.module.css";
import propios from "./traslados.module.css";

export const metadata: Metadata = {
  title: "Traslados",
  description:
    "Traslados al aeropuerto, a la terminal y entre localidades: elegí el vehículo, mirá el precio del viaje y reservá online.",
  alternates: { canonical: "/traslados" },
};

type Props = { searchParams: Promise<Record<string, string | undefined>> };

const entero = (v: string | undefined, maximo: number) =>
  Number(v) > 0 ? Math.min(Math.floor(Number(v)), maximo) : 0;

export default async function Traslados({ searchParams }: Props) {
  const sp = await searchParams;
  const localidad = sp.localidad ?? "";
  const lugar = (sp.lugar ?? "").trim().slice(0, 60);
  const pasajeros = entero(sp.pasajeros, 100);
  const valijas = entero(sp.valijas, 200);

  const params = new URLSearchParams();
  if (localidad) params.set("localidad", localidad);
  if (lugar) params.set("lugar", lugar);
  if (pasajeros) params.set("pasajeros", String(pasajeros));
  if (valijas) params.set("valijas", String(valijas));
  if (sp.pagina) params.set("pagina", sp.pagina);

  const [destinos, resultado] = await Promise.all([
    destinosTraslados().catch(() => []),
    buscarTraslados(params).catch((e) => {
      if (e instanceof ApiError) return null;
      throw e;
    }),
  ]);

  // Lo que se pidió viaja a la ficha: el panel arranca con los pasajeros y valijas.
  const aFicha = new URLSearchParams();
  if (pasajeros) aFicha.set("pasajeros", String(pasajeros));
  if (valijas) aFicha.set("valijas", String(valijas));
  const sufijo = aFicha.size ? `?${aFicha}` : "";

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <header className={estilos.cabecera}>
          <h1>Traslados</h1>
          <p>
            Al aeropuerto, a la terminal o entre localidades, con chofer. Armás el
            viaje, ves cuánto sale en cada vehículo y lo reservás.
          </p>
        </header>

        <form
          className={`${estilos.buscador} ${propios.buscador}`}
          method="get"
          action="/traslados"
        >
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
            <span>Desde o hasta</span>
            <input
              name="lugar"
              defaultValue={lugar}
              maxLength={60}
              placeholder="Aeropuerto, terminal…"
            />
          </label>
          <label>
            <span>Pasajeros</span>
            <input
              type="number"
              name="pasajeros"
              min={1}
              max={100}
              defaultValue={pasajeros || ""}
              placeholder="Cuántos"
            />
          </label>
          <label>
            <span>Valijas</span>
            <input
              type="number"
              name="valijas"
              min={0}
              max={200}
              defaultValue={valijas || ""}
              placeholder="Cuántas"
            />
          </label>
          <button type="submit">Buscar</button>
        </form>

        {resultado === null ? (
          <p className={estilos.vacio}>No pudimos buscar con esos datos.</p>
        ) : resultado.total === 0 ? (
          <div className={estilos.vacio}>
            <h2>No encontramos traslados con eso</h2>
            <p>
              Probá con menos pasajeros o valijas, otro lugar u otro destino.{" "}
              {(lugar || pasajeros || valijas || localidad) && (
                <Link href="/traslados">Ver todos</Link>
              )}
            </p>
          </div>
        ) : (
          <>
            <p className={estilos.cuenta}>
              <span className="cifra">{resultado.total}</span>{" "}
              {resultado.total === 1 ? "servicio de traslados" : "servicios de traslados"}
            </p>
            <ul className={estilos.grilla}>
              {resultado.resultados.map((x) => (
                <li key={x.slug}>
                  <Link href={`/traslado/${x.slug}${sufijo}`} className={estilos.tarjeta}>
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
                        {x.vehiculos > 1
                          ? `${x.vehiculos} vehículos, hasta ${x.pasajeros_maximo} pasajeros`
                          : `Hasta ${plural(x.pasajeros_maximo, "pasajero", "pasajeros")}`}
                        {x.valijas_maximo != null
                          ? ` · ${plural(x.valijas_maximo, "valija", "valijas")}`
                          : ""}
                      </span>
                      {x.recorridos.length > 0 && (
                        <span className={estilos.capacidad}>{x.recorridos.join(" · ")}</span>
                      )}
                      {x.por_km && (
                        <span className={estilos.capacidad}>
                          {x.recorridos.length > 0 ? "Y a cualquier dirección" : "A cualquier dirección"}
                          , por kilómetro
                        </span>
                      )}
                      {x.precio_desde && (
                        <span className={estilos.precio}>
                          Desde{" "}
                          <strong className="cifra">{pesos(x.precio_desde.monto)}</strong>{" "}
                          {x.precio_desde.detalle}
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
                      href={`/traslados?${p}`}
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
