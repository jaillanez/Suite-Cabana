"use client";

import { useRef, useState, useTransition } from "react";

import {
  accionCargarVentaPropia,
  accionCompletarExterna,
  accionDescartarExterna,
  accionLeerCorreo,
} from "@/lib/acciones-publicaciones";
import type { Plataforma, ReservaExterna, UnidadAgenda } from "@/lib/api";
import { diaMes, hoyISO, pesos } from "@/lib/formato";
import { Alerta } from "./Iconos";
import estilos from "./VentasDeAfuera.module.css";

/* Despegar no publica iCal, y una venta cerrada por WhatsApp no tiene calendario
   ninguno. Las dos entran por acá, y al entrar tapan esa noche en Airbnb y en
   Booking: el bloqueo que crean sale por el iCal que exportamos. */
export default function VentasDeAfuera({
  unidades,
  plataformas,
  pendientes,
  direccionBuzon,
}: {
  unidades: UnidadAgenda[];
  plataformas: Plataforma[];
  pendientes: ReservaExterna[];
  direccionBuzon: string;
}) {
  const [modo, setModo] = useState<"correo" | "mano">("correo");
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();
  const formMail = useRef<HTMLFormElement>(null);
  const formMano = useRef<HTMLFormElement>(null);

  const limpiar = () => {
    setAviso(null);
    setError(null);
  };

  function leerMail(datos: FormData) {
    const v = (k: string) => String(datos.get(k) ?? "").trim();
    empezar(async () => {
      limpiar();
      const r = await accionLeerCorreo({
        cuerpo: v("cuerpo"),
        asunto: v("asunto") || undefined,
        remitente: v("remitente") || undefined,
        unidad_id: v("unidad_id") || undefined,
      });
      if ("error" in r) return setError(r.error);
      setAviso(
        r.nueva
          ? `${r.reserva.plataforma_nombre}: ${r.detalle}`
          : "Ese mensaje ya estaba cargado, no se duplicó nada.",
      );
      if (r.nueva && r.reserva.estado === "confirmada") formMail.current?.reset();
    });
  }

  function cargarAMano(datos: FormData) {
    const v = (k: string) => String(datos.get(k) ?? "").trim();
    empezar(async () => {
      limpiar();
      const r = await accionCargarVentaPropia({
        unidad_id: v("unidad_id"),
        fecha_inicio: v("fecha_inicio"),
        fecha_fin: v("fecha_fin"),
        huesped: v("huesped") || undefined,
        contacto: v("contacto") || undefined,
        personas: v("personas") ? Number(v("personas")) : undefined,
        monto: v("monto") || undefined,
        plataforma: v("plataforma") || "particular",
      });
      if ("error" in r) return setError(r.error);
      setAviso(
        `Cargada: ${r.reserva.huesped ?? "sin nombre"}, ` +
          `del ${diaMes(r.reserva.fecha_inicio!)} al ${diaMes(r.reserva.fecha_fin!)}. ` +
          "Esas noches ya están tapadas en las otras plataformas.",
      );
      formMano.current?.reset();
    });
  }

  const opcionesUnidad = (
    <>
      <option value="">Elegí la unidad</option>
      {unidades.map((u) => (
        <option key={u.unidad_id} value={u.unidad_id}>
          {u.publicacion} · {u.unidad}
        </option>
      ))}
    </>
  );

  return (
    <section className={estilos.bloque}>
      <h2>Reservas que entraron por fuera</h2>
      <p className={estilos.ayuda}>
        Lo que vendiste en Despegar —que no publica calendario— o cerraste por WhatsApp.
        Apenas lo cargás, esas noches quedan tapadas en Airbnb, en Booking y acá.
      </p>

      {pendientes.length > 0 && (
        <PorRevisar unidades={unidades} pendientes={pendientes} alTerminar={setAviso} />
      )}

      <div className={estilos.solapas} role="tablist" aria-label="Cómo cargarla">
        {(
          [
            ["correo", "Pegar el mail"],
            ["mano", "Cargarla a mano"],
          ] as const
        ).map(([valor, texto]) => (
          <button
            key={valor}
            type="button"
            role="tab"
            aria-selected={modo === valor}
            className={modo === valor ? estilos.activa : undefined}
            onClick={() => {
              setModo(valor);
              limpiar();
            }}
          >
            {texto}
          </button>
        ))}
      </div>

      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}
      {aviso && (
        <p className={estilos.ok} aria-live="polite">
          {aviso}
        </p>
      )}

      {modo === "correo" ? (
        <form
          className={estilos.formulario}
          action={leerMail}
          ref={formMail}
        >
          <p className={estilos.ayuda}>
            Pegá el mail de confirmación tal cual te llegó. Sacamos fechas, huésped, código y
            monto. Si algo no se entiende, te lo pregunta en vez de adivinar.
          </p>
          <label className={estilos.ancho}>
            <span>El mail, completo</span>
            <textarea
              name="cuerpo"
              rows={7}
              required
              minLength={10}
              placeholder={
                "Localizador: DESP-8842\nHuésped: María Quiroga\nCheck-in: 11/11/2026\n" +
                "Check-out: 15/11/2026\nTotal: $ 248.500,00"
              }
            />
          </label>
          <label>
            <span>Remitente (opcional)</span>
            <input name="remitente" placeholder="reservas@despegar.com.ar" maxLength={300} />
          </label>
          <label>
            <span>Unidad (si ya sabés cuál)</span>
            <select name="unidad_id" defaultValue="">
              <option value="">Que la deduzca del mail</option>
              {unidades.map((u) => (
                <option key={u.unidad_id} value={u.unidad_id}>
                  {u.publicacion} · {u.unidad}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={pendiente}>
            {pendiente ? "Leyendo…" : "Leer el mail"}
          </button>
          <Buzon direccion={direccionBuzon} />
        </form>
      ) : (
        <form
          className={estilos.formulario}
          action={cargarAMano}
          ref={formMano}
        >
          <p className={estilos.ayuda}>
            Para la venta que cerraste vos. No lleva comisión: no la vendimos nosotros, solo
            ocupa la noche.
          </p>
          <label>
            <span>Unidad</span>
            <select name="unidad_id" required defaultValue="">
              {opcionesUnidad}
            </select>
          </label>
          <label>
            <span>Dónde se vendió</span>
            <select name="plataforma" defaultValue="particular">
              <option value="particular">La cerré yo (WhatsApp, teléfono)</option>
              {plataformas.map((p) => (
                <option key={p.codigo} value={p.codigo}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Entrada</span>
            <input type="date" name="fecha_inicio" required min={hoyISO(-365)} />
          </label>
          <label>
            <span>Salida</span>
            <input type="date" name="fecha_fin" required min={hoyISO(-364)} />
          </label>
          <label>
            <span>Huésped</span>
            <input name="huesped" maxLength={120} placeholder="Nombre y apellido" />
          </label>
          <label>
            <span>Contacto</span>
            <input name="contacto" maxLength={120} placeholder="Teléfono o correo" />
          </label>
          <label>
            <span>Personas</span>
            <input type="number" name="personas" min={1} max={99} />
          </label>
          <label>
            <span>Lo que cobraste</span>
            <input type="number" name="monto" min={0} step="any" placeholder="En pesos" />
          </label>
          <button type="submit" disabled={pendiente}>
            {pendiente ? "Cargando…" : "Cargar la reserva"}
          </button>
        </form>
      )}
    </section>
  );
}

/* Para no pegar los mails uno por uno: el anfitrión pone una regla de reenvío y
   entran solos. Es reenvío y no leerle la casilla a propósito —guardar su
   contraseña nos convertiría en un depósito de credenciales ajenas. */
function Buzon({ direccion }: { direccion: string }) {
  const [copiada, setCopiada] = useState(false);

  if (!direccion) {
    return (
      <p className={`${estilos.ayuda} ${estilos.ancho} ${estilos.buzon}`}>
        <strong>¿Cansado de pegarlos de a uno?</strong> Se puede automatizar: cada
        alojamiento tiene una dirección propia, ponés una regla de reenvío en tu correo y
        las reservas entran solas. Falta contratar el servicio de correo entrante y cargar{" "}
        <code>CORREO_ENTRANTE_DOMINIO</code> y <code>CORREO_ENTRANTE_SECRETO</code>.
      </p>
    );
  }

  return (
    <div className={`${estilos.ancho} ${estilos.buzon}`}>
      <p className={estilos.ayuda}>
        <strong>Para que entren solas:</strong> en tu correo, creá una regla que reenvíe los
        mails de las plataformas a esta dirección. Después no tocás nada más.
      </p>
      <p className={estilos.direccion}>
        <code>{direccion}</code>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(direccion);
              setCopiada(true);
              setTimeout(() => setCopiada(false), 2000);
            } catch {
              setCopiada(false);
            }
          }}
        >
          {copiada ? "Copiada" : "Copiar"}
        </button>
      </p>
    </div>
  );
}

/* Lo que llegó por mail y no se entendió del todo. Nada de esto bloquea fechas:
   una reserva a medias que igual ocupa noches es peor que ninguna. */
function PorRevisar({
  unidades,
  pendientes,
  alTerminar,
}: {
  unidades: UnidadAgenda[];
  pendientes: ReservaExterna[];
  alTerminar: (aviso: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  return (
    <div className={estilos.revisar}>
      <h3>
        <Alerta className={estilos.icono} />
        {pendientes.length === 1
          ? "Un mensaje quedó a medias"
          : `${pendientes.length} mensajes quedaron a medias`}
      </h3>
      <p className={estilos.ayuda}>
        No los entendimos del todo, así que <strong>no bloquearon ninguna fecha</strong>.
        Completá lo que falta y ahí sí ocupan la noche.
      </p>
      {error && (
        <p className={estilos.error} role="alert">
          {error}
        </p>
      )}
      <ul>
        {pendientes.map((r) => (
          <li key={r.id}>
            <div className={estilos.quien}>
              <strong>{r.huesped ?? r.plataforma_nombre}</strong>
              <span>
                {r.fecha_inicio && r.fecha_fin
                  ? `${diaMes(r.fecha_inicio)} → ${diaMes(r.fecha_fin)}`
                  : "sin fechas"}
                {r.monto ? ` · ${pesos(r.monto)}` : ""}
                {r.codigo_externo ? ` · ${r.codigo_externo}` : ""}
              </span>
              <span className={estilos.falta}>Falta: {r.faltantes.join(", ")}</span>
            </div>
            <form
              className={estilos.completar}
              action={(datos) => {
                const v = (k: string) => String(datos.get(k) ?? "").trim();
                empezar(async () => {
                  setError(null);
                  const salida = await accionCompletarExterna(r.id, {
                    unidad_id: v("unidad_id") || undefined,
                    fecha_inicio: v("fecha_inicio") || undefined,
                    fecha_fin: v("fecha_fin") || undefined,
                  });
                  if ("error" in salida) setError(salida.error);
                  else alTerminar("Listo, esas noches ya están tomadas.");
                });
              }}
            >
              {!r.unidad_id && (
                <select name="unidad_id" required defaultValue="" aria-label="Unidad">
                  <option value="">¿Qué unidad?</option>
                  {unidades.map((u) => (
                    <option key={u.unidad_id} value={u.unidad_id}>
                      {u.publicacion} · {u.unidad}
                    </option>
                  ))}
                </select>
              )}
              {!r.fecha_inicio && (
                <input type="date" name="fecha_inicio" required aria-label="Entrada" />
              )}
              {!r.fecha_fin && (
                <input type="date" name="fecha_fin" required aria-label="Salida" />
              )}
              <button type="submit" disabled={pendiente}>
                Confirmar
              </button>
              <button
                type="button"
                className={estilos.descartar}
                disabled={pendiente}
                onClick={() =>
                  empezar(async () => {
                    const salida = await accionDescartarExterna(r.id);
                    if (salida.error) setError(salida.error);
                    else alTerminar("Descartado.");
                  })
                }
              >
                No era una reserva
              </button>
            </form>
          </li>
        ))}
      </ul>
    </div>
  );
}
