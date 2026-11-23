import type { Metadata } from "next";
import Link from "next/link";

import { ApiError, buscarSalones, destinosSalones } from "@/lib/api";
import { diaMesAnio, hoyISO, pesos } from "@/lib/formato";
import Encabezado from "@/componentes/Encabezado";
import estilos from "./salones.module.css";

export const metadata: Metadata = {
  title: "Salones de eventos",
  description:
    "Salones, quinchos y espacios para eventos: por turno o por horas, con el precio a la vista y reserva con seña.",
  alternates: { canonical: "/salones" },
};

type Props = { searchParams: Promise<Record<string, string | undefined>> };

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

export default async function Salones({ searchParams }: Props) {
  const sp = await searchParams;
  const localidad = sp.localidad ?? "";
  const dia = FECHA.test(sp.dia ?? "") && sp.dia! >= hoyISO() ? sp.dia! : "";
  const invitados =
    Number(sp.invitados) > 0 ? Math.min(Number(sp.invitados), 5000) : 0;

  const params = new URLSearchParams();
  if (localidad) params.set("localidad", localidad);
  if (dia) params.set("dia", dia);
  if (invitados) params.set("invitados", String(invitados));
  if (sp.pagina) params.set("pagina", sp.pagina);

  const [destinos, resultado] = await Promise.all([
    destinosSalones().catch(() => []),
    buscarSalones(params).catch((e) => {
      if (e instanceof ApiError) return null;
      throw e;
    }),
  ]);

  // Lo que se pidió viaja a la ficha: el panel arranca con el día y los invitados.
  const aFicha = new URLSearchParams();
  if (dia) aFicha.set("dia", dia);
  if (invitados) aFicha.set("invitados", String(invitados));
  const sufijo = aFicha.size ? `?${aFicha}` : "";

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <header className={estilos.cabecera}>
          <h1>Salones de eventos</h1>
          <p>
            Salones, quinchos y espacios al aire libre. Por turno o por horas,
            con seña.
          </p>
        </header>

        <form className={estilos.buscador} method="get" action="/salones">
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
            <span>Día del evento</span>
            <input type="date" name="dia" defaultValue={dia} min={hoyISO()} max={hoyISO(730)} />
          </label>
          <label>
            <span>Invitados</span>
            <input
              type="number"
              name="invitados"
              min={1}
              max={5000}
              defaultValue={invitados || ""}
              placeholder="Cuántos"
            />
          </label>
          <button type="submit">Buscar</button>
        </form>

        {resultado === null ? (
          <p className={estilos.vacio}>
            No pudimos buscar con esos datos. Revisá el día.
          </p>
        ) : resultado.total === 0 ? (
          <div className={estilos.vacio}>
            <h2>
              No encontramos salones{" "}
              {dia ? `libres el ${diaMesAnio(dia)}` : "con eso"}
            </h2>
            <p>
              Probá con otro día, menos invitados u otro destino.{" "}
              {(dia || invitados || localidad) && (
                <Link href="/salones">Ver todos</Link>
              )}
            </p>
          </div>
        ) : (
          <>
            <p className={estilos.cuenta}>
              <span className="cifra">{resultado.total}</span>{" "}
              {resultado.total === 1 ? "salón" : "salones"}
              {dia ? ` con lugar el ${diaMesAnio(dia)}` : ""}
            </p>
            <ul className={estilos.grilla}>
              {resultado.resultados.map((s) => (
                <li key={s.slug}>
                  <Link
                    href={`/salon/${s.slug}${sufijo}`}
                    className={estilos.tarjeta}
                  >
                    <span className={estilos.foto}>
                      {s.fotos[0] ? (
                        <img src={s.fotos[0].url} alt="" loading="lazy" />
                      ) : (
                        <span className={estilos.sinFoto}>
                          Sin fotos todavía
                        </span>
                      )}
                      {s.es_demo && (
                        <span className={estilos.demo}>Ejemplo</span>
                      )}
                    </span>
                    <span className={estilos.datos}>
                      <strong>{s.titulo}</strong>
                      <span className={estilos.lugar}>
                        {[s.subtipo, s.localidad].filter(Boolean).join(" · ")}
                      </span>
                      <span className={estilos.capacidad}>
                        Hasta{" "}
                        <span className="cifra">{s.capacidad_maxima}</span>{" "}
                        personas
                        {s.sentados_maximo ? (
                          <>
                            {" "}
                            · <span className="cifra">
                              {s.sentados_maximo}
                            </span>{" "}
                            sentadas
                          </>
                        ) : null}
                      </span>
                      {s.precio_desde && (
                        <span className={estilos.precio}>
                          Desde{" "}
                          <strong className="cifra">
                            {pesos(s.precio_desde.monto)}
                          </strong>{" "}
                          {s.precio_desde.detalle}
                        </span>
                      )}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            {resultado.paginas > 1 && (
              <nav className={estilos.paginas} aria-label="Páginas">
                {Array.from({ length: resultado.paginas }, (_, i) => i + 1).map(
                  (n) => {
                    const p = new URLSearchParams(params);
                    p.set("pagina", String(n));
                    return (
                      <Link
                        key={n}
                        href={`/salones?${p}`}
                        aria-current={
                          n === resultado.pagina ? "page" : undefined
                        }
                      >
                        {n}
                      </Link>
                    );
                  },
                )}
              </nav>
            )}
          </>
        )}
      </main>
    </>
  );
}
