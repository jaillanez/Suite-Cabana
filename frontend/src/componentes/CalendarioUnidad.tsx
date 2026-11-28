"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import {
  accionAgregarCalendario,
  accionBloquear,
  accionQuitarCalendario,
  accionSincronizar,
  accionSoltar,
  accionVerAgenda,
  type ResultadoAgenda,
} from "@/lib/acciones-publicaciones";
import type { Agenda } from "@/lib/api";
import { diaMes, hoyISO } from "@/lib/formato";
import { Alerta, Cruz } from "./Iconos";
import estilos from "./CalendarioUnidad.module.css";

/* El prestador ya publica en Booking y Airbnb. Si los calendarios no se hablan,
   la misma noche se vende dos veces. Acá se ve todo lo que tiene tomada la unidad,
   venga de donde venga, y se conectan los calendarios de las otras plataformas. */
export default function CalendarioUnidad({
  publicacionId,
  unidadId,
  bloqueado,
}: {
  publicacionId: string;
  unidadId: string;
  bloqueado: boolean;
}) {
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [copiada, setCopiada] = useState(false);
  const [pendiente, empezar] = useTransition();

  useEffect(() => {
    empezar(async () => aplicar(await accionVerAgenda(publicacionId, unidadId)));
  }, [publicacionId, unidadId]);

  function aplicar(r: ResultadoAgenda) {
    if ("agenda" in r) {
      setAgenda(r.agenda);
      setError(null);
      // Al conectar uno, el backend dice qué leyó ("¡Conectado! Leímos…").
      if (r.agenda.aviso) setAviso(r.agenda.aviso);
    } else {
      setError(r.error);
    }
  }

  const correr = (accion: () => Promise<ResultadoAgenda>) =>
    empezar(async () => {
      setAviso(null);
      aplicar(await accion());
    });

  async function copiar(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiada(true);
      setTimeout(() => setCopiada(false), 2000);
    } catch {
      setError("No pudimos copiarla. Seleccionala y copiala a mano.");
    }
  }

  if (!agenda) {
    return <p className={estilos.cargando}>{error ?? "Cargando el calendario…"}</p>;
  }

  const propios = agenda.tramos.filter((t) => t.editable);
  const ajenos = agenda.tramos.filter((t) => !t.editable);

  return (
    <div className={estilos.calendario}>
      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}
      {aviso && <p className={estilos.aviso}>{aviso}</p>}

      <section>
        <h4>Fechas tomadas</h4>
        {agenda.tramos.length === 0 ? (
          <p className={estilos.vacio}>Todo libre por ahora.</p>
        ) : (
          <ul className={estilos.tramos}>
            {[...propios, ...ajenos].map((t) => (
              <li key={t.id} className={estilos[t.origen]}>
                <span className={`${estilos.fechas} cifra`}>
                  {diaMes(t.desde)} → {diaMes(t.hasta)}
                </span>
                <span className={estilos.etiqueta}>
                  {t.etiqueta}
                  {t.calendario && <span className={estilos.fuente}> · {t.calendario}</span>}
                  {t.nota && t.origen === "manual" && (
                    <span className={estilos.fuente}> · {t.nota}</span>
                  )}
                </span>
                {t.editable ? (
                  <button
                    type="button"
                    disabled={pendiente || bloqueado}
                    onClick={() => correr(() => accionSoltar(publicacionId, unidadId, t.id))}
                    aria-label="Liberar estas fechas"
                  >
                    <Cruz />
                  </button>
                ) : (
                  <span aria-hidden="true" />
                )}
              </li>
            ))}
          </ul>
        )}

        <form
          className={estilos.fila}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            correr(() =>
              accionBloquear(publicacionId, unidadId, {
                desde: v("desde"),
                hasta: v("hasta"),
                nota: v("nota") || undefined,
              }),
            );
          }}
        >
          <input type="date" name="desde" min={hoyISO()} required aria-label="Desde" />
          <input type="date" name="hasta" min={hoyISO(1)} required aria-label="Hasta (salida)" />
          <input name="nota" placeholder="Motivo (opcional)" maxLength={200} />
          <button type="submit" disabled={pendiente || bloqueado}>
            Bloquear fechas
          </button>
        </form>
        <p className={estilos.ayuda}>
          La segunda fecha es el día de salida: esa noche queda libre para el próximo huésped.
        </p>
      </section>

      <section>
        <h4>Sincronizar con otras plataformas</h4>
        <p className={estilos.ayuda}>
          Lo más fácil es el{" "}
          <Link href={`/mis-publicaciones/${publicacionId}/calendarios`}>
            asistente paso a paso para Airbnb y Booking
          </Link>
          . Si ya tenés la dirección a mano, también la podés pegar acá: una fecha vendida en
          cualquiera de los dos lados queda tomada en el otro. Se actualiza sola cada una hora.
        </p>

        {agenda.calendarios.length > 0 && (
          <ul className={estilos.externos}>
            {agenda.calendarios.map((c) => (
              <li key={c.id}>
                <div>
                  <strong>{c.nombre}</strong>
                  <span className={estilos.estadoSync}>
                    {c.ultimo_error
                      ? c.ultimo_error
                      : c.ultima_sincronizacion
                        ? `Última vez: ${new Date(c.ultima_sincronizacion).toLocaleString("es-AR")}`
                        : "Todavía no se sincronizó"}
                  </span>
                </div>
                <button
                  type="button"
                  disabled={pendiente || bloqueado}
                  onClick={() =>
                    empezar(async () => {
                      const r = await accionSincronizar(publicacionId, unidadId, c.id);
                      if ("error" in r) setError(r.error);
                      else {
                        setAviso(r.detalle);
                        aplicar(await accionVerAgenda(publicacionId, unidadId));
                      }
                    })
                  }
                >
                  Sincronizar ahora
                </button>
                <button
                  type="button"
                  className={estilos.quitar}
                  disabled={pendiente || bloqueado}
                  onClick={() =>
                    correr(() => accionQuitarCalendario(publicacionId, unidadId, c.id))
                  }
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
        )}

        <form
          className={estilos.fila}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            correr(() =>
              accionAgregarCalendario(publicacionId, unidadId, {
                nombre: v("nombre"),
                url: v("url"),
              }),
            );
          }}
        >
          <input name="nombre" placeholder="Booking, Airbnb…" required maxLength={60} />
          <input
            name="url"
            type="url"
            placeholder="https://…/calendar.ics"
            required
            className={estilos.ancho}
          />
          <button type="submit" disabled={pendiente || bloqueado}>
            Conectar
          </button>
        </form>
      </section>

      <section>
        <h4>Tu calendario, para pegar allá</h4>
        <div className={estilos.exportar}>
          <code>{agenda.url_exportacion}</code>
          <button type="button" onClick={() => copiar(agenda.url_exportacion)}>
            {copiada ? "Copiada" : "Copiar"}
          </button>
        </div>
        <p className={estilos.ayuda}>
          Publica solo qué noches están tomadas: ni quién reservó ni cuánto pagó. Lo que traés
          de otra plataforma no se reenvía.
        </p>
      </section>
    </div>
  );
}
