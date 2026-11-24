"use client";

/* El panel de reserva de una excursión (docs/05, etapa 4). Las salidas con lugar
   y la cotización las da el backend: acá no se calcula ningún precio ni se decide
   si hay lugar, solo se muestra lo que la API responde. */

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { accionReservarExcursion } from "@/lib/acciones-reservas";
import {
  ApiError,
  cotizarExcursion,
  salidasExcursion,
  type CotizacionExcursion,
  type FichaExcursion,
  type PedidoExcursion,
  type SalidaPublica,
} from "@/lib/api";
import { diaAR, horaAR, hoyISO, pesos, pesosExactos, plural } from "@/lib/formato";
import { CampoWhatsApp } from "./BotonReservar";
import { Alerta, ChevronDer, ChevronIzq } from "./Iconos";
import panel from "./PanelReserva.module.css";
import salon from "./ReservaSalon.module.css";
import estilos from "./ReservaExcursion.module.css";

const DIAS = 14;

function masDias(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d + n)).toISOString().slice(0, 10);
}

function mensaje(e: unknown, porDefecto: string) {
  return e instanceof ApiError && e.message ? e.message : porDefecto;
}

/* Turno + fecha: no cambia cuando la salida se guarda porque otro reservó. */
const clave = (s: SalidaPublica) => (s.turno_id ? `${s.turno_id}-${s.fecha}` : s.salida_id!);

function edades(desde: number | null, hasta: number | null): string | null {
  if (desde != null && hasta != null) return `${desde} a ${hasta} años`;
  if (desde != null) return `desde ${desde} años`;
  if (hasta != null) return `hasta ${hasta} años`;
  return null;
}

export default function ReservaExcursion({
  ficha,
  fechaInicial = "",
  personasInicial = 0,
}: {
  ficha: FichaExcursion;
  fechaInicial?: string;
  personasInicial?: number;
}) {
  const router = useRouter();
  const [actividadId, setActividadId] = useState(ficha.actividades[0]?.id ?? "");
  const actividad =
    ficha.actividades.find((a) => a.id === actividadId) ?? ficha.actividades[0];
  const [desde, setDesde] = useState(fechaInicial && fechaInicial >= hoyISO() ? fechaInicial : hoyISO());
  const [lista, setLista] = useState<SalidaPublica[] | null>(null);
  const [errorLista, setErrorLista] = useState<string | null>(null);
  const [elegida, setElegida] = useState<SalidaPublica | null>(null);
  // Arranca con las personas de la búsqueda en el primer tipo (el que el
  // prestador cargó primero, suele ser el adulto).
  const [cantidades, setCantidades] = useState<Record<string, number>>(() =>
    personasInicial && ficha.actividades[0]?.precios[0]
      ? { [ficha.actividades[0].precios[0].id]: personasInicial }
      : {},
  );
  const [cot, setCot] = useState<CotizacionExcursion | null>(null);
  const [errorCot, setErrorCot] = useState<string | null>(null);
  const [errorReserva, setErrorReserva] = useState<string | null>(null);
  const [acepta, setAcepta] = useState(false);
  const [pedirTelefono, setPedirTelefono] = useState(false);
  const [telefono, setTelefono] = useState("");
  const [reservando, empezar] = useTransition();
  const hasta = masDias(desde, DIAS - 1);

  useEffect(() => {
    if (!actividad) return;
    let vigente = true;
    setErrorLista(null);
    salidasExcursion(actividad.id, desde, hasta)
      .then((r) => {
        if (!vigente) return;
        setLista(r.salidas);
        // Si la elegida ya no está (se llenó, cambió la quincena), se suelta.
        setElegida((e) => (e && r.salidas.some((s) => clave(s) === clave(e)) ? e : null));
      })
      .catch((e) => vigente && setErrorLista(mensaje(e, "No pudimos ver las salidas.")));
    return () => {
      vigente = false;
    };
  }, [actividad, desde, hasta]);

  const pedido: PedidoExcursion | null = useMemo(() => {
    if (!actividad || !elegida) return null;
    const pasajeros = Object.entries(cantidades)
      .filter(([, n]) => n > 0)
      .map(([categoria_id, cantidad]) => ({ categoria_id, cantidad }));
    if (!pasajeros.length) return null;
    return {
      unidad_id: actividad.id,
      fecha: elegida.fecha,
      ...(elegida.salida_id ? { salida_id: elegida.salida_id } : { turno_id: elegida.turno_id }),
      pasajeros,
    };
  }, [actividad, elegida, cantidades]);

  useEffect(() => {
    if (!pedido) {
      setCot(null);
      setErrorCot(null);
      return;
    }
    let vigente = true;
    const espera = setTimeout(() => {
      cotizarExcursion(pedido)
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

  if (!actividad) {
    return (
      <aside className={panel.panel}>
        <p className={panel.aviso}>Esta excursión todavía no tiene precios cargados.</p>
      </aside>
    );
  }

  const total = Object.values(cantidades).reduce((a, b) => a + b, 0);
  const porDia = (lista ?? []).reduce<Record<string, SalidaPublica[]>>((acc, s) => {
    (acc[s.fecha] ??= []).push(s);
    return acc;
  }, {});

  function sumar(id: string, paso: number) {
    setCantidades((c) => ({ ...c, [id]: Math.max(0, (c[id] ?? 0) + paso) }));
  }

  function reservar() {
    if (!pedido) return;
    setErrorReserva(null);
    empezar(async () => {
      const r = await accionReservarExcursion(
        pedido,
        acepta,
        pedirTelefono ? telefono : undefined,
      );
      if (r?.ingresar) {
        const volver = `/excursion/${ficha.slug}?fecha=${elegida?.fecha ?? ""}&personas=${total}`;
        router.push(`/ingresar?volver=${encodeURIComponent(volver)}`);
        return;
      }
      if (r?.pedirTelefono) setPedirTelefono(true);
      if (r?.error) setErrorReserva(r.error);
    });
  }

  return (
    <aside className={panel.panel} aria-label="Reservar">
      {ficha.actividades.length > 1 && (
        <div className={salon.espacios} role="radiogroup" aria-label="Actividad">
          {ficha.actividades.map((a) => (
            <button
              key={a.id}
              type="button"
              role="radio"
              aria-checked={a.id === actividad.id}
              className={`${panel.unidad} ${a.id === actividad.id ? panel.seleccionada : ""}`}
              onClick={() => {
                setActividadId(a.id);
                setElegida(null);
                setCantidades({});
                setLista(null);
              }}
            >
              <strong>{a.nombre}</strong>
            </button>
          ))}
        </div>
      )}

      <div className={estilos.navegacion}>
        <button
          type="button"
          onClick={() => setDesde(masDias(desde, -DIAS) < hoyISO() ? hoyISO() : masDias(desde, -DIAS))}
          disabled={desde <= hoyISO()}
          aria-label="Dos semanas antes"
        >
          <ChevronIzq />
        </button>
        <span>Elegí la salida</span>
        <button
          type="button"
          onClick={() => setDesde(masDias(desde, DIAS))}
          disabled={masDias(desde, DIAS) > hoyISO(365)}
          aria-label="Dos semanas después"
        >
          <ChevronDer />
        </button>
      </div>

      {errorLista && (
        <p className={salon.error} role="alert">
          <Alerta className={salon.iconoError} />
          {errorLista}
        </p>
      )}

      {!lista ? (
        <p className={salon.nota}>Buscando salidas…</p>
      ) : lista.length === 0 ? (
        <p className={salon.nota}>No hay salidas con lugar en estas dos semanas.</p>
      ) : (
        <ol className={estilos.dias}>
          {Object.entries(porDia).map(([dia, delDia]) => (
            <li key={dia}>
              <span className={estilos.dia}>{diaAR(delDia[0].inicio)}</span>
              <span className={estilos.salidas} role="radiogroup" aria-label={diaAR(delDia[0].inicio)}>
                {delDia.map((s) => (
                  <button
                    key={clave(s)}
                    type="button"
                    role="radio"
                    aria-checked={elegida ? clave(elegida) === clave(s) : false}
                    className={estilos.salida}
                    onClick={() => setElegida(s)}
                  >
                    <strong className="cifra">{horaAR(s.inicio)}</strong>
                    <small>
                      {s.libres <= 5 ? plural(s.libres, "lugar", "lugares") : s.nombre}
                    </small>
                  </button>
                ))}
              </span>
            </li>
          ))}
        </ol>
      )}

      <fieldset className={estilos.pasajeros}>
        <legend>
          Quiénes van <small>hasta {actividad.maximo_por_reserva} por reserva</small>
        </legend>
        {actividad.precios.map((c) => {
          const n = cantidades[c.id] ?? 0;
          const detalle = [edades(c.edad_desde, c.edad_hasta), c.descripcion]
            .filter(Boolean)
            .join(" · ");
          return (
            <div key={c.id} className={estilos.pasajero}>
              <span>
                <strong>{c.nombre}</strong>
                <small>
                  {Number(c.precio) === 0 ? "Gratis" : pesos(c.precio)}
                  {detalle ? ` · ${detalle}` : ""}
                  {!c.ocupa_lugar ? " · no ocupa lugar" : ""}
                </small>
              </span>
              <span className={estilos.contador}>
                <button
                  type="button"
                  onClick={() => sumar(c.id, -1)}
                  disabled={n === 0}
                  aria-label={`Uno menos: ${c.nombre}`}
                >
                  −
                </button>
                <output className="cifra" aria-live="polite">
                  {n}
                </output>
                <button
                  type="button"
                  onClick={() => sumar(c.id, 1)}
                  disabled={total >= actividad.maximo_por_reserva}
                  aria-label={`Uno más: ${c.nombre}`}
                >
                  +
                </button>
              </span>
            </div>
          );
        })}
      </fieldset>

      {elegida && elegida.minimo_personas > 1 && (
        <p className={salon.nota}>
          Esta salida va con al menos {elegida.minimo_personas} personas. Si no se
          llega, se cancela y se te devuelve el {ficha.reintegro_si_no_sale}% de lo
          pagado.
        </p>
      )}

      {errorCot && (
        <p className={salon.error} role="alert">
          <Alerta className={salon.iconoError} />
          {errorCot}
        </p>
      )}

      {cot && (
        <div className={salon.cotizacion}>
          <p className={salon.cuando}>
            {diaAR(cot.salida.inicio)}, {horaAR(cot.salida.inicio)} h
          </p>
          <dl>
            {cot.lineas.map((l) => (
              <div key={l.concepto}>
                <dt>
                  {l.cantidad} × {l.concepto}
                </dt>
                <dd className="cifra">{pesosExactos(l.monto)}</dd>
              </div>
            ))}
            {Number(cot.cargo_servicio) > 0 && (
              <div>
                <dt>Cargo de servicio</dt>
                <dd className="cifra">{pesosExactos(cot.cargo_servicio)}</dd>
              </div>
            )}
            <div className={salon.total}>
              <dt>Total</dt>
              <dd className="cifra">{pesosExactos(cot.total)}</dd>
            </div>
          </dl>
          {cot.sena ? (
            <p className={salon.sena}>
              Para reservar pagás la seña:{" "}
              <strong className="cifra">{pesosExactos(cot.a_pagar_ahora)}</strong>. El
              resto, <span className="cifra">{pesos(cot.saldo_con_prestador ?? "0")}</span>,
              lo arreglás con quien organiza.
            </p>
          ) : (
            <p className={salon.sena}>Se paga el total al reservar.</p>
          )}
        </div>
      )}

      {errorReserva && (
        <p className={salon.error} role="alert">
          <Alerta className={salon.iconoError} />
          {errorReserva}
        </p>
      )}

      {pedirTelefono && <CampoWhatsApp valor={telefono} cambiar={setTelefono} />}

      <label className={salon.terminos}>
        <input type="checkbox" checked={acepta} onChange={(e) => setAcepta(e.target.checked)} />
        <span>
          Acepto los <Link href="/terminos">términos</Link> y la política de cancelación de
          esta excursión.
        </span>
      </label>

      <button
        type="button"
        className={salon.reservar}
        disabled={!cot || !acepta || reservando || (pedirTelefono && !telefono.trim())}
        onClick={reservar}
      >
        {reservando
          ? "Reservando…"
          : cot?.sena
            ? `Reservar con seña de ${pesos(cot.a_pagar_ahora)}`
            : "Reservar"}
      </button>

      {!ficha.confirmacion_inmediata && (
        <p className={salon.nota}>
          Quien organiza confirma cada pedido. Si no lo acepta, se te devuelve lo pagado.
        </p>
      )}
    </aside>
  );
}
