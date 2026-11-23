"use client";

/* El panel de reserva de un salón (docs/04 §5 S10). Pide la disponibilidad del día
   y la cotización al backend: acá no se calcula ningún precio ni se decide si un
   horario está libre, solo se muestra lo que la API responde. */

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { accionReservarEvento } from "@/lib/acciones-reservas";
import {
  ApiError,
  alojamientosSumables,
  cotizarEvento,
  type AlojamientoSumable,
  disponibilidadSalon,
  type CotizacionEvento,
  type DisponibilidadSalon,
  type FichaSalon,
  type PedidoEvento,
} from "@/lib/api";
import {
  horaAR,
  horarioEvento,
  hoyISO,
  pesos,
  pesosExactos,
  plural,
  rangoFechas,
} from "@/lib/formato";
import { CampoWhatsApp } from "./BotonReservar";
import { Alerta, Personas } from "./Iconos";
import panel from "./PanelReserva.module.css";
import estilos from "./ReservaSalon.module.css";

type Modo = "turno" | "horas";
const MEDIA_HORA = 30 * 60 * 1000;

/** El día ISO siguiente (o n días después), sin pasar por UTC. */
function masDias(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const f = new Date(Date.UTC(a, m - 1, d + n));
  return f.toISOString().slice(0, 10);
}

function mensaje(e: unknown, porDefecto: string) {
  return e instanceof ApiError && e.message ? e.message : porDefecto;
}

/* Inicios posibles cada media hora dentro del horario de atención, marcando los
   que chocan con algo ocupado. Es solo para guiar: la palabra final la tiene la
   cotización, que incluye la preparación y el mínimo de horas. */
function inicios(d: DisponibilidadSalon, horas: number) {
  if (!d.por_horas) return [];
  const apertura = new Date(d.por_horas.apertura).getTime();
  const cierre = new Date(d.por_horas.cierre).getTime();
  const dur = horas * 2 * MEDIA_HORA;
  const ahora = Date.now();
  const ocupado = d.ocupado.map((o) => [
    new Date(o.inicio).getTime(),
    new Date(o.fin).getTime(),
  ]);
  const lista: { iso: string; libre: boolean }[] = [];
  for (let t = apertura; t + dur <= cierre; t += MEDIA_HORA) {
    const choca = ocupado.some(([a, b]) => t < b && t + dur > a);
    lista.push({ iso: new Date(t).toISOString(), libre: t > ahora && !choca });
  }
  return lista;
}

export default function ReservaSalon({
  ficha,
  diaInicial = "",
  invitadosInicial = 0,
}: {
  ficha: FichaSalon;
  diaInicial?: string;
  invitadosInicial?: number;
}) {
  const router = useRouter();
  const [espacioId, setEspacioId] = useState(ficha.espacios[0]?.id ?? "");
  const espacio =
    ficha.espacios.find((e) => e.id === espacioId) ?? ficha.espacios[0];
  const [dia, setDia] = useState(diaInicial);
  const [invitados, setInvitados] = useState(invitadosInicial || 0);
  const [modo, setModo] = useState<Modo>(
    espacio?.franjas.length ? "turno" : "horas",
  );
  const [franjaId, setFranjaId] = useState<string | null>(null);
  const [horaInicio, setHoraInicio] = useState<string | null>(null);
  const [horas, setHoras] = useState(espacio?.por_horas?.horas_minimas ?? 3);
  const [adicionales, setAdicionales] = useState<string[]>([]);
  const [acepta, setAcepta] = useState(false);
  // Paquete (docs/04 S11): cabañas del mismo anfitrión desde la noche del evento.
  const [noches, setNoches] = useState(1);
  const [estadias, setEstadias] = useState<Record<string, number>>({});
  const [sumables, setSumables] = useState<AlojamientoSumable[] | null>(null);
  const hayAlojamiento = ficha.alojamientos_del_anfitrion.length > 0;
  const salida = dia ? masDias(dia, noches) : "";

  const [disp, setDisp] = useState<DisponibilidadSalon | null>(null);
  const [errorDisp, setErrorDisp] = useState<string | null>(null);
  const [cot, setCot] = useState<CotizacionEvento | null>(null);
  const [errorCot, setErrorCot] = useState<string | null>(null);
  const [errorReserva, setErrorReserva] = useState<string | null>(null);
  // Solo aparece si la cuenta no tiene WhatsApp (el backend responde 428).
  const [pedirTelefono, setPedirTelefono] = useState(false);
  const [telefono, setTelefono] = useState("");
  const [reservando, empezar] = useTransition();

  // Cambiar de espacio o de día invalida lo elegido: los turnos y horas son otros.
  useEffect(() => {
    setFranjaId(null);
    setHoraInicio(null);
    setCot(null);
    if (!espacio || !dia) {
      setDisp(null);
      return;
    }
    let vigente = true;
    setErrorDisp(null);
    disponibilidadSalon(espacio.id, dia)
      .then((d) => vigente && setDisp(d))
      .catch(
        (e) =>
          vigente &&
          setErrorDisp(mensaje(e, "No pudimos ver la disponibilidad.")),
      );
    return () => {
      vigente = false;
    };
  }, [espacio, dia]);

  // Qué cabañas se pueden sumar esas noches, con su precio. Lo que dejó de
  // estar libre se saca de lo elegido.
  useEffect(() => {
    if (!hayAlojamiento || !espacio || !dia) {
      setSumables(null);
      return;
    }
    let vigente = true;
    alojamientosSumables(espacio.id, dia, salida, 2)
      .then((lista) => {
        if (!vigente) return;
        setSumables(lista);
        const libres = new Set(lista.filter((x) => x.libre).map((x) => x.unidad_id));
        setEstadias((actual) =>
          Object.fromEntries(
            Object.entries(actual).filter(([id]) => libres.has(id)),
          ),
        );
      })
      .catch(() => vigente && setSumables([]));
    return () => {
      vigente = false;
    };
  }, [hayAlojamiento, espacio, dia, salida]);

  const pedido: PedidoEvento | null = useMemo(() => {
    if (!espacio || !dia || invitados < 1) return null;
    const alojamientos = Object.entries(estadias).map(([unidad_id, adultos]) => ({
      unidad_id,
      desde: dia,
      hasta: salida,
      adultos,
    }));
    const base = { unidad_id: espacio.id, dia, invitados, adicionales, alojamientos };
    if (modo === "turno" && franjaId) return { ...base, franja_id: franjaId };
    if (modo === "horas" && horaInicio)
      return { ...base, hora_inicio: horaInicio, horas };
    return null;
  }, [
    espacio,
    dia,
    invitados,
    adicionales,
    estadias,
    salida,
    modo,
    franjaId,
    horaInicio,
    horas,
  ]);

  useEffect(() => {
    if (!pedido) {
      setCot(null);
      setErrorCot(null);
      return;
    }
    let vigente = true;
    const espera = setTimeout(() => {
      cotizarEvento(pedido)
        .then((c) => {
          if (!vigente) return;
          setCot(c);
          setErrorCot(null);
        })
        .catch((e) => {
          if (!vigente) return;
          setCot(null);
          setErrorCot(mensaje(e, "No pudimos calcular el precio."));
        });
    }, 250);
    return () => {
      vigente = false;
      clearTimeout(espera);
    };
  }, [pedido]);

  if (!espacio) {
    return (
      <aside className={panel.panel}>
        <p className={panel.aviso}>
          Este salón todavía no tiene precios cargados.
        </p>
      </aside>
    );
  }

  const opcionesHora = disp ? inicios(disp, horas) : [];
  const minimoHoras = espacio.por_horas?.horas_minimas ?? 1;

  function reservar() {
    if (!pedido) return;
    setErrorReserva(null);
    empezar(async () => {
      const r = await accionReservarEvento(
        pedido,
        pedirTelefono ? telefono : undefined,
      );
      if (r?.ingresar) {
        const volver = `/salon/${ficha.slug}?dia=${dia}&invitados=${invitados}`;
        router.push(`/ingresar?volver=${encodeURIComponent(volver)}`);
        return;
      }
      if (r?.pedirTelefono) setPedirTelefono(true);
      if (r?.error) setErrorReserva(r.error);
    });
  }

  return (
    <aside className={panel.panel} aria-label="Reservar">
      {ficha.espacios.length > 1 && (
        <div
          className={estilos.espacios}
          role="radiogroup"
          aria-label="Espacio"
        >
          {ficha.espacios.map((e) => (
            <button
              key={e.id}
              type="button"
              role="radio"
              aria-checked={e.id === espacio.id}
              className={`${panel.unidad} ${e.id === espacio.id ? panel.seleccionada : ""}`}
              onClick={() => {
                setEspacioId(e.id);
                setModo(e.franjas.length ? "turno" : "horas");
                setHoras(e.por_horas?.horas_minimas ?? 3);
                setAdicionales([]);
              }}
            >
              <strong>{e.nombre}</strong>
              <span>hasta {e.capacidad}</span>
            </button>
          ))}
        </div>
      )}

      <div className={panel.fechas}>
        <label>
          <span>Día del evento</span>
          <input
            type="date"
            value={dia}
            min={hoyISO()}
            max={hoyISO(730)}
            onChange={(e) => setDia(e.target.value)}
          />
        </label>
        <label>
          <span>Invitados</span>
          <span className={panel.conIcono}>
            <Personas className={panel.icono} />
            <input
              type="number"
              min={1}
              max={espacio.capacidad}
              value={invitados || ""}
              placeholder={`hasta ${espacio.capacidad}`}
              onChange={(e) => setInvitados(Number(e.target.value))}
            />
          </span>
        </label>
      </div>

      {espacio.franjas.length > 0 && espacio.por_horas && (
        <div
          className={estilos.modos}
          role="tablist"
          aria-label="Cómo alquilar"
        >
          {(["turno", "horas"] as Modo[]).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={modo === m}
              className={modo === m ? estilos.modoActivo : ""}
              onClick={() => setModo(m)}
            >
              {m === "turno" ? "Por turno" : "Por horas"}
            </button>
          ))}
        </div>
      )}

      {!dia ? (
        <p className={panel.aviso}>Elegí el día para ver qué está libre.</p>
      ) : errorDisp ? (
        <p className={estilos.error}>
          <Alerta className={estilos.iconoError} />
          {errorDisp}
        </p>
      ) : !disp ? (
        <p className={panel.aviso}>Buscando qué está libre…</p>
      ) : modo === "turno" ? (
        <ul className={estilos.turnos}>
          {disp.franjas.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                disabled={!f.libre}
                aria-pressed={franjaId === f.id}
                className={`${panel.unidad} ${franjaId === f.id ? panel.seleccionada : ""} ${
                  f.libre ? "" : panel.ocupada
                }`}
                onClick={() => setFranjaId(f.id)}
              >
                <strong>{f.nombre}</strong>
                <span className="cifra">{pesos(f.precio)}</span>
                <small>
                  {horaAR(f.inicio)} a {horaAR(f.fin)} h
                  {f.libre ? "" : " · ocupado"}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className={estilos.horas}>
          <label>
            <span>Horas</span>
            <select
              value={horas}
              onChange={(e) => {
                setHoras(Number(e.target.value));
                setHoraInicio(null);
              }}
            >
              {Array.from({ length: 13 }, (_, i) => minimoHoras + i).map(
                (h) => (
                  <option key={h} value={h}>
                    {h} h
                  </option>
                ),
              )}
            </select>
          </label>
          <label>
            <span>Desde</span>
            <select
              value={horaInicio ?? ""}
              onChange={(e) => setHoraInicio(e.target.value || null)}
            >
              <option value="">Elegí</option>
              {opcionesHora.map((o) => (
                <option key={o.iso} value={horaAR(o.iso)} disabled={!o.libre}>
                  {horaAR(o.iso)}
                  {o.libre ? "" : " (ocupado)"}
                </option>
              ))}
            </select>
          </label>
          {disp.por_horas && (
            <p className={estilos.nota}>
              <span className="cifra">{pesos(disp.por_horas.precio_hora)}</span>{" "}
              la hora · abre {horaAR(disp.por_horas.apertura)}, cierra{" "}
              {horaAR(disp.por_horas.cierre)} h
            </p>
          )}
        </div>
      )}

      {espacio.adicionales.length > 0 && (
        <fieldset className={estilos.adicionales}>
          <legend>Sumar al alquiler</legend>
          {espacio.adicionales.map((a) => (
            <label key={a.id}>
              <input
                type="checkbox"
                checked={adicionales.includes(a.id)}
                onChange={(e) =>
                  setAdicionales((actual) =>
                    e.target.checked
                      ? [...actual, a.id]
                      : actual.filter((x) => x !== a.id),
                  )
                }
              />
              <span>{a.nombre}</span>
              <span className="cifra">
                {pesos(a.precio)}
                {a.por_persona ? " c/u" : ""}
              </span>
            </label>
          ))}
        </fieldset>
      )}

      {hayAlojamiento && dia && (
        <fieldset className={estilos.dormir}>
          <legend>¿Se quedan a dormir?</legend>
          <p className={estilos.nota}>
            Sumá cabañas del mismo anfitrión a esta reserva: un solo pago y una
            sola seña.
          </p>
          <label className={estilos.noches}>
            <span>Noches, desde el día del evento</span>
            <select
              value={noches}
              onChange={(e) => setNoches(Number(e.target.value))}
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {plural(n, "noche", "noches")}
                </option>
              ))}
            </select>
          </label>
          {!sumables ? (
            <p className={estilos.nota}>Buscando cabañas libres…</p>
          ) : sumables.length === 0 ? (
            <p className={estilos.nota}>No hay cabañas para sumar.</p>
          ) : (
            <ul className={estilos.cabanas}>
              {sumables.map((a) => {
                const elegida = a.unidad_id in estadias;
                return (
                  <li key={a.unidad_id} data-libre={a.libre}>
                    <label>
                      <input
                        type="checkbox"
                        disabled={!a.libre}
                        checked={elegida}
                        onChange={(e) =>
                          setEstadias((actual) => {
                            const nuevo = { ...actual };
                            if (e.target.checked)
                              nuevo[a.unidad_id] = Math.min(2, a.capacidad);
                            else delete nuevo[a.unidad_id];
                            return nuevo;
                          })
                        }
                      />
                      <span>
                        <strong>{a.unidad}</strong> · {a.publicacion}
                        <small>
                          {a.libre
                            ? `hasta ${a.capacidad} personas`
                            : a.motivo}
                        </small>
                      </span>
                      {a.total && (
                        <span className="cifra">{pesos(a.total)}</span>
                      )}
                    </label>
                    {elegida && (
                      <label className={estilos.personas}>
                        <span>Personas</span>
                        <select
                          value={estadias[a.unidad_id]}
                          onChange={(e) =>
                            setEstadias((actual) => ({
                              ...actual,
                              [a.unidad_id]: Number(e.target.value),
                            }))
                          }
                        >
                          {Array.from({ length: a.capacidad }, (_, i) => i + 1).map(
                            (n) => (
                              <option key={n} value={n}>
                                {n}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </fieldset>
      )}

      {errorCot && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.iconoError} />
          {errorCot}
        </p>
      )}

      {cot && (
        <div className={estilos.cotizacion}>
          <p className={estilos.cuando}>{horarioEvento(cot.inicio, cot.fin)}</p>
          <dl>
            <div>
              <dt>Alquiler</dt>
              <dd className="cifra">{pesosExactos(cot.alquiler)}</dd>
            </div>
            {cot.lineas.map((l) => (
              <div key={l.concepto}>
                <dt>{l.concepto}</dt>
                <dd className="cifra">{pesosExactos(l.monto)}</dd>
              </div>
            ))}
            {Number(cot.cargo_servicio) > 0 && (
              <div>
                <dt>Cargo de servicio</dt>
                <dd className="cifra">{pesosExactos(cot.cargo_servicio)}</dd>
              </div>
            )}
            {cot.alojamientos.length > 0 && (
              <>
                <div className={estilos.parcial}>
                  <dt>Evento</dt>
                  <dd className="cifra">{pesosExactos(cot.total_evento)}</dd>
                </div>
                {cot.alojamientos.map((a) => (
                  <div key={a.unidad_id}>
                    <dt>
                      {a.unidad} · {a.publicacion}
                      <small>
                        {rangoFechas(a.desde, a.hasta)},{" "}
                        {plural(a.noches, "noche", "noches")},{" "}
                        {plural(a.personas, "persona", "personas")}
                      </small>
                    </dt>
                    <dd className="cifra">{pesosExactos(a.total)}</dd>
                  </div>
                ))}
              </>
            )}
            <div className={estilos.total}>
              <dt>
                {cot.alojamientos.length > 0 ? "Total" : "Total del evento"}
              </dt>
              <dd className="cifra">{pesosExactos(cot.total)}</dd>
            </div>
          </dl>
          {cot.sena ? (
            <p className={estilos.sena}>
              Para reservar pagás la seña:{" "}
              <strong className="cifra">
                {pesosExactos(cot.a_pagar_ahora)}
              </strong>
              . El resto,{" "}
              <span className="cifra">
                {pesos(cot.saldo_con_anfitrion ?? "0")}
              </span>
              , lo arreglás con el anfitrión.
            </p>
          ) : (
            <p className={estilos.sena}>Se paga el total al reservar.</p>
          )}
        </div>
      )}

      {errorReserva && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.iconoError} />
          {errorReserva}
        </p>
      )}

      {pedirTelefono && (
        <CampoWhatsApp valor={telefono} cambiar={setTelefono} />
      )}

      <label className={estilos.terminos}>
        <input
          type="checkbox"
          checked={acepta}
          onChange={(e) => setAcepta(e.target.checked)}
        />
        <span>
          Acepto los <Link href="/terminos">términos</Link> y la política de
          cancelación de este salón.
        </span>
      </label>

      <button
        type="button"
        className={estilos.reservar}
        disabled={
          !cot || !acepta || reservando || (pedirTelefono && !telefono.trim())
        }
        onClick={reservar}
      >
        {reservando
          ? "Reservando…"
          : cot?.sena
            ? `Reservar con seña de ${pesos(cot.a_pagar_ahora)}`
            : "Reservar"}
      </button>

      {!ficha.confirmacion_inmediata && (
        <p className={estilos.nota}>
          El anfitrión confirma cada pedido. Si no lo acepta, se te devuelve lo
          pagado.
        </p>
      )}
    </aside>
  );
}
