"use client";

import Link from "next/link";
import { useMemo, useRef, useState, useTransition } from "react";

import { accionSincronizarTodo } from "@/lib/acciones-publicaciones";
import type { AgendaGeneral, Plataforma, TramoAgenda, UnidadAgenda } from "@/lib/api";
import { plural } from "@/lib/formato";
import { Alerta } from "./Iconos";
import estilos from "./CalendarioGeneral.module.css";

const DIA = 86_400_000;
const SEMANA = ["D", "L", "M", "M", "J", "V", "S"];
const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** Toda la grilla se cuenta en UTC de punta a punta. Mezclar con la fecha local
    de `formato.fecha` corre las columnas un día entero al oeste de Greenwich, que
    es exactamente donde estamos. */
function aDia(iso: string): Date {
  const [anio, mes, dia] = iso.split("-").map(Number);
  return new Date(Date.UTC(anio, mes - 1, dia));
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

const hoyUTC = () => {
  const n = new Date();
  return iso(new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())));
};

function dias(desde: string, hasta: string): Date[] {
  const salida: Date[] = [];
  for (let t = aDia(desde).getTime(); t < aDia(hasta).getTime(); t += DIA) {
    salida.push(new Date(t));
  }
  return salida;
}

/** Por cada noche, qué la tiene tomada. Una sola pasada por unidad: la grilla
    consulta por día y no puede recorrer los tramos cada vez. */
function porNoche(u: UnidadAgenda): Map<string, TramoAgenda> {
  const mapa = new Map<string, TramoAgenda>();
  for (const t of u.tramos) {
    for (const d of dias(t.desde, t.hasta)) mapa.set(iso(d), t);
  }
  return mapa;
}

const CUANDO = (valor: string | null) =>
  valor ? new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : null;

export default function CalendarioGeneral({
  agenda,
  plataformas,
}: {
  agenda: AgendaGeneral;
  plataformas: Plataforma[];
}) {
  const [resultado, setResultado] = useState<string | null>(null);
  const [fallas, setFallas] = useState<string[]>([]);
  const [pendiente, empezar] = useTransition();
  const grilla = useRef<HTMLDivElement>(null);

  const fechas = useMemo(() => dias(agenda.desde, agenda.hasta), [agenda.desde, agenda.hasta]);
  const ocupacion = useMemo(
    () => agenda.unidades.map((u) => [u, porNoche(u)] as const),
    [agenda.unidades],
  );
  const hoy = hoyUTC();

  /* Los meses se dibujan una vez arriba, abarcando sus días. */
  const meses = useMemo(() => {
    const tramos: { nombre: string; largo: number }[] = [];
    for (const d of fechas) {
      const nombre = `${MES[d.getUTCMonth()]}${d.getUTCMonth() === 0 ? ` ${d.getUTCFullYear()}` : ""}`;
      const ultimo = tramos.at(-1);
      if (ultimo?.nombre === nombre) ultimo.largo += 1;
      else tramos.push({ nombre, largo: 1 });
    }
    return tramos;
  }, [fechas]);

  function sincronizar() {
    empezar(async () => {
      setResultado(null);
      setFallas([]);
      const r = await accionSincronizarTodo();
      if ("error" in r) {
        setFallas([r.error]);
        return;
      }
      setResultado(
        r.con_error === 0
          ? `Listo: ${plural(r.sincronizados, "calendario", "calendarios")} al día.`
          : `${plural(r.sincronizados, "actualizado", "actualizados")}, ` +
            `${r.con_error} sin responder.`,
      );
      setFallas(
        r.resultados.filter((x) => !x.ok).map((x) => `${x.nombre} (${x.unidad}): ${x.detalle}`),
      );
    });
  }

  const { resumen } = agenda;
  const conectables = plataformas.filter((p) => p.tiene_ical);
  const sinIcal = plataformas.filter((p) => !p.tiene_ical);

  return (
    <div className={estilos.pantalla}>
      <section className={estilos.cifras} aria-label="Resumen">
        {[
          [resumen.unidades, "unidades"],
          [resumen.noches_ocupadas, "noches tomadas"],
          [resumen.conexiones, "calendarios conectados"],
        ].map(([n, texto]) => (
          <div key={texto as string}>
            <strong className="cifra">{n}</strong>
            <span>{texto}</span>
          </div>
        ))}
        {resumen.con_error > 0 && (
          <div className={estilos.malo}>
            <strong className="cifra">{resumen.con_error}</strong>
            <span>sin responder</span>
          </div>
        )}
      </section>

      <div className={estilos.acciones}>
        <button
          type="button"
          className={estilos.sincronizar}
          onClick={sincronizar}
          disabled={pendiente || resumen.conexiones === 0}
        >
          {pendiente ? "Sincronizando…" : "Sincronizar todo"}
        </button>
        {resumen.conexiones === 0 ? (
          <p className={estilos.ayuda}>
            Todavía no conectaste ningún calendario. Abajo está cómo sacar la dirección en
            cada plataforma.
          </p>
        ) : (
          <p className={estilos.ayuda} aria-live="polite">
            {resultado ??
              "Cada plataforma relee los calendarios ajenos cada una a cuatro horas. Si acabás de vender afuera, traelo ahora."}
          </p>
        )}
      </div>

      {fallas.length > 0 && (
        <ul className={estilos.fallas} role="alert">
          {fallas.map((f) => (
            <li key={f}>
              <Alerta className={estilos.icono} />
              {f}
            </li>
          ))}
        </ul>
      )}

      {agenda.unidades.length === 0 ? (
        <p className={estilos.vacio}>
          Todavía no tenés unidades cargadas.{" "}
          <Link href="/mis-publicaciones/nueva">Creá tu primera publicación</Link>.
        </p>
      ) : (
        <>
          <div className={estilos.marco} ref={grilla}>
            <table className={estilos.grilla}>
              <caption className="oculto">
                Ocupación de tus unidades día por día, con el origen de cada bloqueo.
              </caption>
              <thead>
                <tr>
                  <th className={estilos.esquina} scope="col" rowSpan={2}>
                    Unidad
                  </th>
                  {meses.map((m) => (
                    <th key={m.nombre} colSpan={m.largo} scope="col" className={estilos.mes}>
                      <span>{m.nombre}</span>
                    </th>
                  ))}
                </tr>
                <tr>
                  {fechas.map((d) => {
                    const clave = iso(d);
                    const finde = d.getUTCDay() === 0 || d.getUTCDay() === 6;
                    return (
                      <th
                        key={clave}
                        scope="col"
                        className={`${estilos.dia} ${finde ? estilos.finde : ""} ${
                          clave === hoy ? estilos.hoy : ""
                        }`}
                      >
                        <span className={estilos.diaSemana}>{SEMANA[d.getUTCDay()]}</span>
                        <span className="cifra">{d.getUTCDate()}</span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {ocupacion.map(([u, noches]) => (
                  <tr key={u.unidad_id}>
                    <th scope="row" className={estilos.unidad}>
                      <Link href={`/mis-publicaciones/${u.publicacion_id}`}>
                        <strong>{u.unidad}</strong>
                        <span>{u.publicacion}</span>
                      </Link>
                    </th>
                    {fechas.map((d) => {
                      const clave = iso(d);
                      const t = noches.get(clave);
                      const finde = d.getUTCDay() === 0 || d.getUTCDay() === 6;
                      /* Los extremos redondeados salen de comparar con el vecino:
                         así dos tramos pegados se leen como dos, no como uno. */
                      const empieza = t && noches.get(iso(new Date(d.getTime() - DIA))) !== t;
                      const termina = t && noches.get(iso(new Date(d.getTime() + DIA))) !== t;
                      return (
                        <td
                          key={clave}
                          className={[
                            estilos.celda,
                            finde ? estilos.finde : "",
                            clave === hoy ? estilos.hoy : "",
                            t ? estilos[t.origen] : "",
                            t && empieza ? estilos.empieza : "",
                            t && termina ? estilos.termina : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          /* Quién viene es lo primero que se quiere saber al
                             pasar por encima; de dónde vino, después. */
                          title={
                            t
                              ? [u.unidad, t.nota, t.etiqueta, t.calendario]
                                  .filter(Boolean)
                                  .join(" · ")
                              : undefined
                          }
                        >
                          {t && t.desde === clave && (
                            <span className="oculto">
                              {u.unidad}: ocupado desde el {clave} hasta el {t.hasta}, {t.etiqueta}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className={estilos.referencias}>
            {[
              ["reserva", "Reserva en Suite Cabaña"],
              ["retencion", "Esperando el pago"],
              ["ical", "Vendido en otra plataforma"],
              ["manual", "Bloqueado por vos"],
            ].map(([clase, texto]) => (
              <li key={clase}>
                <span className={`${estilos.muestra} ${estilos[clase]}`} aria-hidden="true" />
                {texto}
              </li>
            ))}
          </ul>
        </>
      )}

      <section className={estilos.conexiones}>
        <h2>Calendarios conectados</h2>
        {agenda.conexiones.length === 0 ? (
          <p className={estilos.vacio}>
            Ninguno todavía. Se conectan desde cada unidad, en el editor de su publicación.
          </p>
        ) : (
          <ul>
            {agenda.conexiones.map((c) => (
              <li key={c.id} className={c.ultimo_error ? estilos.conError : undefined}>
                <div className={estilos.quien}>
                  <strong>{c.plataforma_nombre}</strong>
                  <span>
                    {c.unidad} · {c.publicacion}
                  </span>
                </div>
                <Link href={`/mis-publicaciones/${c.publicacion_id ?? ""}`}>Ver unidad</Link>
                <span className={estilos.cuando}>
                  {c.ultimo_error ? (
                    <>
                      <Alerta className={estilos.icono} />
                      {c.ultimo_error}
                    </>
                  ) : (
                    (CUANDO(c.ultima_sincronizacion) ?? "Todavía no se trajo nada")
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={estilos.guia}>
        <h2>Cómo conectar cada plataforma</h2>
        <p className={estilos.ayuda}>
          Son dos direcciones y van cruzadas: la de ellos se pega en el editor de tu unidad, y
          la nuestra —que está en esa misma pantalla— se pega allá. El calendario viaja solo
          con las fechas ocupadas: no lleva precios ni datos del huésped.
        </p>
        <div className={estilos.tarjetas}>
          {conectables.map((p) => (
            <details key={p.codigo}>
              <summary>
                <strong>{p.nombre}</strong>
                <span>{p.donde_esta}</span>
              </summary>
              {p.pasos.length > 0 && (
                <ol>
                  {p.pasos.map((paso) => (
                    <li key={paso}>
                      <span>{paso}</span>
                    </li>
                  ))}
                </ol>
              )}
              {p.ejemplo_url && (
                <p className={estilos.ejemplo}>
                  Se ve así: <code>{p.ejemplo_url}</code>
                </p>
              )}
              {p.nota && <p className={estilos.nota}>{p.nota}</p>}
            </details>
          ))}
        </div>
        {sinIcal.length > 0 && (
          <div className={estilos.pendientes}>
            <h3>Todavía no se pueden sincronizar solas</h3>
            <ul>
              {sinIcal.map((p) => (
                <li key={p.codigo}>
                  <strong>{p.nombre}</strong>
                  <span>{p.nota}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
