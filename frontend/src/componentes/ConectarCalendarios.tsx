"use client";

/* Asistente para conectar los calendarios de Airbnb, Booking y otras con los de
   acá (mejora 2). Son dos sentidos y los dos se guían paso a paso:
   1. Traer el de ellos: se pega su enlace y el backend lo lee en el momento.
   2. Llevar el nuestro: se copia nuestra dirección y se pega allá; cuando esa
      plataforma la lee, aparece acá ("Airbnb lo leyó hace 20 min").
   Qué es un enlace válido, qué se encontró y qué falla lo decide el backend. */

import { useState, useTransition } from "react";

import {
  accionAgregarCalendario,
  accionQuitarCalendario,
  accionSincronizar,
} from "@/lib/acciones-publicaciones";
import type {
  CalendarioExterno,
  CalendariosPublicacion,
  CalendariosUnidad,
  Plataforma,
} from "@/lib/api";
import { Alerta, Rayo } from "./Iconos";
import estilos from "./ConectarCalendarios.module.css";

function hace(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const minutos = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutos < 2) return "recién";
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.round(horas / 24);
  return `hace ${dias} ${dias === 1 ? "día" : "días"}`;
}

type Estado = "al_dia" | "con_error" | "sin_conectar";

function estadoDe(u: CalendariosUnidad): Estado {
  if (u.calendarios.some((c) => c.ultimo_error)) return "con_error";
  if (u.calendarios.length === 0 && u.lecturas.length === 0) return "sin_conectar";
  return "al_dia";
}

const ETIQUETA_ESTADO: Record<Estado, string> = {
  al_dia: "Conectada",
  con_error: "Con un problema",
  sin_conectar: "Sin conectar",
};

/* --- Un calendario ya conectado --- */

function Conectado({
  publicacionId,
  unidadId,
  c,
  nombre,
  cambiar,
}: {
  publicacionId: string;
  unidadId: string;
  c: CalendarioExterno;
  nombre: string;
  cambiar: (lista: CalendarioExterno[] | null, aviso?: string) => void;
}) {
  const [pendiente, empezar] = useTransition();
  return (
    <li className={c.ultimo_error ? estilos.conError : estilos.conectado}>
      <div>
        <strong>{nombre}</strong>
        {c.ultimo_error ? (
          <p>
            <Alerta className={estilos.icono} />
            {c.ultimo_error}
          </p>
        ) : (
          <p>Al día · leído {hace(c.ultima_sincronizacion)}. Se vuelve a leer cada hora.</p>
        )}
      </div>
      <div className={estilos.acciones}>
        <button
          type="button"
          disabled={pendiente}
          onClick={() =>
            empezar(async () => {
              const r = await accionSincronizar(publicacionId, unidadId, c.id);
              if ("error" in r) cambiar(null, r.error);
              else cambiar(r.calendarios, `${nombre}: leído recién, ${r.detalle}.`);
            })
          }
        >
          {pendiente ? "Leyendo…" : "Leer ahora"}
        </button>
        <button
          type="button"
          disabled={pendiente}
          onClick={() =>
            empezar(async () => {
              const r = await accionQuitarCalendario(publicacionId, unidadId, c.id);
              if ("agenda" in r) cambiar(r.agenda.calendarios, `Quitamos el calendario de ${nombre}.`);
              else cambiar(null, r.error);
            })
          }
        >
          Quitar
        </button>
      </div>
    </li>
  );
}

/* --- El paso a paso para una plataforma --- */

function Asistente({
  publicacionId,
  unidad,
  plataforma,
  terminar,
  conectado,
}: {
  publicacionId: string;
  unidad: CalendariosUnidad;
  plataforma: Plataforma;
  terminar: () => void;
  conectado: (lista: CalendarioExterno[], aviso: string) => void;
}) {
  const [paso, setPaso] = useState<1 | 2>(1);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [pendiente, empezar] = useTransition();
  const lectura = unidad.lecturas.find((l) => l.plataforma === plataforma.codigo);

  function probar() {
    setError(null);
    empezar(async () => {
      const r = await accionAgregarCalendario(publicacionId, unidad.unidad_id, {
        nombre: plataforma.codigo === "otro" ? "Otra plataforma" : plataforma.nombre,
        url: url.trim(),
        plataforma: plataforma.codigo,
      });
      if ("error" in r) {
        setError(r.error);
        return;
      }
      setResultado(r.agenda.aviso ?? "Conectado.");
      conectado(r.agenda.calendarios, r.agenda.aviso ?? "");
      setPaso(2);
    });
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(unidad.url_exportacion);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch {
      setError("No pudimos copiarla: seleccionala y copiala a mano.");
    }
  }

  return (
    <section className={estilos.asistente} aria-label={`Conectar ${plataforma.nombre}`}>
      <ol className={estilos.migas}>
        <li aria-current={paso === 1 ? "step" : undefined}>1. Traer el de {plataforma.nombre}</li>
        <li aria-current={paso === 2 ? "step" : undefined}>2. Llevar el nuestro</li>
      </ol>

      {paso === 1 ? (
        <>
          <h3>Copiá el enlace del calendario en {plataforma.nombre}</h3>
          {plataforma.pasos.length > 0 ? (
            <ol className={estilos.pasos}>
              {plataforma.pasos.slice(0, -1).map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ol>
          ) : (
            <p className={estilos.ayuda}>Está en: {plataforma.donde_esta}.</p>
          )}
          {plataforma.nota && <p className={estilos.ayuda}>{plataforma.nota}</p>}
          <label className={estilos.campo}>
            <span>Pegá acá el enlace</span>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={plataforma.ejemplo_url}
              inputMode="url"
              autoComplete="off"
            />
          </label>
          {error && (
            <p className={estilos.error} role="alert">
              <Alerta className={estilos.icono} />
              {error}
            </p>
          )}
          <div className={estilos.botones}>
            <button
              type="button"
              className={estilos.principal}
              disabled={pendiente || url.trim().length < 10}
              onClick={probar}
            >
              {pendiente ? "Leyendo el calendario…" : "Probar y conectar"}
            </button>
            <button type="button" className={estilos.secundario} onClick={terminar}>
              Cancelar
            </button>
          </div>
        </>
      ) : (
        <>
          {resultado && (
            <p className={estilos.ok} role="status">
              <Rayo className={estilos.icono} />
              {resultado}
            </p>
          )}
          <h3>Ahora, que {plataforma.nombre} vea lo que se reserva acá</h3>
          <ol className={estilos.pasos}>
            <li>Copiá esta dirección:</li>
          </ol>
          <div className={estilos.copiar}>
            <code>{unidad.url_exportacion}</code>
            <button type="button" onClick={copiar}>
              {copiado ? "¡Copiada!" : "Copiar"}
            </button>
          </div>
          <ol className={estilos.pasos} start={2}>
            <li>
              {plataforma.pasos.length > 0
                ? plataforma.pasos[plataforma.pasos.length - 1]
                : `En ${plataforma.nombre}, buscá «importar calendario» y pegala.`}
            </li>
          </ol>
          <p className={estilos.ayuda}>
            {lectura
              ? `${plataforma.nombre} ya está leyendo tu calendario (${hace(lectura.leido_en)}). ¡Listo!`
              : `Cuando ${plataforma.nombre} lo lea por primera vez, lo vas a ver en esta pantalla. Puede tardar unas horas.`}
          </p>
          {error && (
            <p className={estilos.error} role="alert">
              {error}
            </p>
          )}
          <div className={estilos.botones}>
            <button type="button" className={estilos.principal} onClick={terminar}>
              Listo
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/* --- La pantalla --- */

export default function ConectarCalendarios({
  inicial,
  plataformas,
}: {
  inicial: CalendariosPublicacion;
  plataformas: Plataforma[];
}) {
  const [unidades, setUnidades] = useState(inicial.unidades);
  const [elegida, setElegida] = useState(inicial.unidades[0]?.unidad_id ?? "");
  const [conectando, setConectando] = useState<Plataforma | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const u = unidades.find((x) => x.unidad_id === elegida);
  const nombre = (c: CalendarioExterno) =>
    plataformas.find((p) => p.codigo === c.plataforma && p.codigo !== "otro")?.nombre ?? c.nombre;

  function cambiar(lista: CalendarioExterno[] | null, texto?: string) {
    if (lista) {
      setUnidades((todas) =>
        todas.map((x) => (x.unidad_id === elegida ? { ...x, calendarios: lista } : x)),
      );
    }
    if (texto !== undefined) setAviso(texto);
  }

  if (!u) {
    return <p className={estilos.ayuda}>Primero cargá al menos una unidad en tu publicación.</p>;
  }

  const conIcal = plataformas.filter((p) => p.tiene_ical);
  const sinIcal = plataformas.filter((p) => !p.tiene_ical);

  return (
    <div className={estilos.pantalla}>
      {unidades.length > 1 && (
        <div className={estilos.unidades} role="tablist" aria-label="Unidad">
          {unidades.map((x) => {
            const e = estadoDe(x);
            return (
              <button
                key={x.unidad_id}
                type="button"
                role="tab"
                aria-selected={x.unidad_id === elegida}
                className={estilos.unidad}
                onClick={() => {
                  setElegida(x.unidad_id);
                  setConectando(null);
                  setAviso(null);
                }}
              >
                <strong>{x.unidad}</strong>
                <span className={estilos[e]}>{ETIQUETA_ESTADO[e]}</span>
              </button>
            );
          })}
        </div>
      )}

      {aviso && (
        <p className={estilos.aviso} role="status">
          {aviso}
        </p>
      )}

      <section className={estilos.bloque}>
        <h2>Lo que traemos de otras plataformas</h2>
        {u.calendarios.length === 0 ? (
          <p className={estilos.ayuda}>
            Todavía no conectaste ninguna. Lo que se reserve allá no se bloquea acá.
          </p>
        ) : (
          <ul className={estilos.lista}>
            {u.calendarios.map((c) => (
              <Conectado
                key={c.id}
                publicacionId={inicial.publicacion_id}
                unidadId={u.unidad_id}
                c={c}
                nombre={nombre(c)}
                cambiar={cambiar}
              />
            ))}
          </ul>
        )}
      </section>

      <section className={estilos.bloque}>
        <h2>Quién lee tu calendario de acá</h2>
        {u.lecturas.length === 0 ? (
          <p className={estilos.ayuda}>
            Todavía ninguna plataforma lo leyó. Hasta que lo hagan, lo que se reserve acá no se
            bloquea allá.
          </p>
        ) : (
          <ul className={estilos.lista}>
            {u.lecturas.map((l) => (
              <li key={l.plataforma} className={estilos.conectado}>
                <div>
                  <strong>{l.nombre}</strong>
                  <p>Lo leyó {hace(l.leido_en)}.</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {conectando ? (
        <Asistente
          key={`${u.unidad_id}-${conectando.codigo}`}
          publicacionId={inicial.publicacion_id}
          unidad={u}
          plataforma={conectando}
          terminar={() => setConectando(null)}
          // El resultado lo muestra el asistente: arriba no se repite.
          conectado={(lista) => cambiar(lista)}
        />
      ) : (
        <section className={estilos.bloque}>
          <h2>Conectar una plataforma</h2>
          <div className={estilos.plataformas}>
            {conIcal.map((p) => (
              <button
                key={p.codigo}
                type="button"
                className={estilos.plataforma}
                onClick={() => {
                  setAviso(null);
                  setConectando(p);
                }}
              >
                {p.nombre}
              </button>
            ))}
          </div>
          {sinIcal.map((p) => (
            <p key={p.codigo} className={estilos.ayuda}>
              <strong>{p.nombre}:</strong> {p.nota}
            </p>
          ))}
        </section>
      )}

      <p className={estilos.nota}>
        Las plataformas se leen entre sí cada una a cuatro horas, así que si alguien reserva en
        dos lugares casi al mismo tiempo puede haber una doble reserva. Acá nunca se vende una
        noche tomada: el riesgo es solo en ese rato, y por eso conviene conectar los dos sentidos.
      </p>
    </div>
  );
}
