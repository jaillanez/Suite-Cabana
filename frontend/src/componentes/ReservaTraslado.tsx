"use client";

/* El panel de reserva de un traslado (docs/06, etapa 4). El viajero arma el viaje
   y el backend responde, vehículo por vehículo, cuánto sale y si está libre
   (`opciones`). Acá no se calcula ningún precio ni se decide disponibilidad. */

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { accionReservarTraslado } from "@/lib/acciones-reservas";
import {
  ApiError,
  opcionesTraslado,
  type ExtremoViaje,
  type FichaTraslado,
  type OpcionTraslado,
  type ViajePedido,
} from "@/lib/api";
import { diaAR, horaAR, hoyISO, pesos, pesosExactos, plural } from "@/lib/formato";
import { CampoWhatsApp } from "./BotonReservar";
import { Alerta } from "./Iconos";
import MapaSelector from "./MapaSelector";
import panel from "./PanelReserva.module.css";
import salon from "./ReservaSalon.module.css";
import estilos from "./ReservaTraslado.module.css";

const OTRA = "otra";

type Punta = {
  lugar: string; // id del lugar, OTRA o "" (sin elegir)
  direccion: string;
  punto: { lat: number; lon: number } | null;
};

const vacia = (lugar = ""): Punta => ({ lugar, direccion: "", punto: null });

/* Argentina no tiene horario de verano: la hora de reloj es siempre -03:00. */
const enHora = (dia: string, hora: string) => `${dia}T${hora}:00-03:00`;

function extremo(p: Punta): ExtremoViaje | null {
  if (p.lugar === OTRA) {
    if (!p.punto || !p.direccion.trim()) return null;
    return { ...p.punto, direccion: p.direccion.trim() };
  }
  if (!p.lugar) return null;
  return { lugar_id: p.lugar, direccion: p.direccion.trim() || null };
}

function mensaje(e: unknown, porDefecto: string) {
  return e instanceof ApiError && e.message ? e.message : porDefecto;
}

function EleccionPunta({
  titulo,
  punta,
  cambiar,
  ficha,
  ayudaDireccion,
}: {
  titulo: string;
  punta: Punta;
  cambiar: (p: Punta) => void;
  ficha: FichaTraslado;
  ayudaDireccion: string;
}) {
  const conKm = ficha.vehiculos.some((v) => v.por_km);
  return (
    <fieldset className={estilos.punta}>
      <legend>{titulo}</legend>
      <select
        value={punta.lugar}
        onChange={(e) => cambiar({ ...vacia(e.target.value) })}
        aria-label={titulo}
      >
        <option value="" disabled>
          Elegí…
        </option>
        {ficha.lugares.map((l) => (
          <option key={l.id} value={l.id}>
            {l.nombre}
          </option>
        ))}
        {conKm && <option value={OTRA}>Otra dirección…</option>}
      </select>
      {punta.lugar === OTRA && (
        <div className={estilos.mapa}>
          <MapaSelector
            lat={punta.punto?.lat ?? ficha.lat}
            lon={punta.punto?.lon ?? ficha.lon}
            ayuda="Tocá el mapa o arrastrá el pin hasta la puerta."
            onMover={(lat, lon) => cambiar({ ...punta, punto: { lat, lon } })}
          />
        </div>
      )}
      {punta.lugar && (
        <input
          value={punta.direccion}
          onChange={(e) => cambiar({ ...punta, direccion: e.target.value })}
          maxLength={200}
          required={punta.lugar === OTRA}
          placeholder={punta.lugar === OTRA ? "Calle y número (obligatorio)" : ayudaDireccion}
          aria-label={`Dirección: ${titulo.toLowerCase()}`}
        />
      )}
    </fieldset>
  );
}

export default function ReservaTraslado({
  ficha,
  pasajerosInicial = 0,
  valijasInicial = 0,
  diaInicial = "",
}: {
  ficha: FichaTraslado;
  pasajerosInicial?: number;
  valijasInicial?: number;
  diaInicial?: string;
}) {
  const router = useRouter();
  const [origen, setOrigen] = useState<Punta>(vacia());
  const [destino, setDestino] = useState<Punta>(vacia());
  const [dia, setDia] = useState(diaInicial >= hoyISO() ? diaInicial : "");
  const [hora, setHora] = useState("");
  const [pasajeros, setPasajeros] = useState(pasajerosInicial || 1);
  const [valijas, setValijas] = useState(valijasInicial);
  const [conVuelta, setConVuelta] = useState(false);
  const [diaVuelta, setDiaVuelta] = useState("");
  const [horaVuelta, setHoraVuelta] = useState("");
  const [vueloIda, setVueloIda] = useState("");
  const [vueloVuelta, setVueloVuelta] = useState("");
  const [notas, setNotas] = useState("");
  const [lista, setLista] = useState<OpcionTraslado[] | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [errorLista, setErrorLista] = useState<string | null>(null);
  const [elegido, setElegido] = useState<string | null>(null);
  const [errorReserva, setErrorReserva] = useState<string | null>(null);
  const [acepta, setAcepta] = useState(false);
  const [pedirTelefono, setPedirTelefono] = useState(false);
  const [telefono, setTelefono] = useState("");
  const [reservando, empezar] = useTransition();

  /* El viaje, recién cuando está completo. Lo que no cambia el precio (vuelos,
     notas) no vuelve a pedir opciones: va aparte, al reservar. */
  const viaje: ViajePedido | null = useMemo(() => {
    const o = extremo(origen);
    const d = extremo(destino);
    if (!o || !d || !dia || !hora || pasajeros < 1) return null;
    if (conVuelta && (!diaVuelta || !horaVuelta)) return null;
    return {
      origen: o,
      destino: d,
      inicio: enHora(dia, hora),
      pasajeros,
      valijas,
      vuelta_inicio: conVuelta ? enHora(diaVuelta, horaVuelta) : null,
    };
  }, [origen, destino, dia, hora, pasajeros, valijas, conVuelta, diaVuelta, horaVuelta]);

  useEffect(() => {
    if (!viaje) {
      setLista(null);
      setErrorLista(null);
      return;
    }
    let vigente = true;
    setBuscando(true);
    const espera = setTimeout(() => {
      opcionesTraslado(ficha.publicacion_id, viaje)
        .then((r) => {
          if (!vigente) return;
          setLista(r);
          setErrorLista(null);
          // Se mantiene el elegido si sigue disponible; si no, el primero libre.
          setElegido((e) =>
            e && r.some((x) => x.unidad_id === e && x.disponible)
              ? e
              : (r.find((x) => x.disponible)?.unidad_id ?? null),
          );
        })
        .catch((e) => {
          if (!vigente) return;
          setLista(null);
          setErrorLista(mensaje(e, "No pudimos calcular el viaje."));
        })
        .finally(() => vigente && setBuscando(false));
    }, 350);
    return () => {
      vigente = false;
      clearTimeout(espera);
    };
  }, [viaje, ficha.publicacion_id]);

  if (ficha.vehiculos.length === 0) {
    return (
      <aside className={panel.panel}>
        <p className={panel.aviso}>Este servicio todavía no tiene vehículos para reservar.</p>
      </aside>
    );
  }

  const opcion = lista?.find((x) => x.unidad_id === elegido && x.disponible) ?? null;
  const cot = opcion?.cotizacion ?? null;
  /* Qué falta, dicho puntual: "elegí desde dónde" no ayuda a quien ya eligió
     "otra dirección" y solo le falta tocar el mapa. */
  const falta = (p: Punta, cual: string) =>
    !p.lugar
      ? `Elegí ${cual}.`
      : p.lugar === OTRA && !p.punto
        ? `Marcá en el mapa ${cual === "desde dónde" ? "dónde te buscamos" : "adónde vas"}.`
        : p.lugar === OTRA && !p.direccion.trim()
          ? `Escribí la dirección ${cual === "desde dónde" ? "donde te buscamos" : "adonde vas"}.`
          : null;
  const pendientePunta = falta(origen, "desde dónde") ?? falta(destino, "hasta dónde");

  function reservar() {
    if (!viaje || !opcion) return;
    setErrorReserva(null);
    empezar(async () => {
      const r = await accionReservarTraslado(
        {
          ...viaje,
          unidad_id: opcion.unidad_id,
          vuelo_ida: vueloIda.trim() || null,
          vuelo_vuelta: conVuelta ? vueloVuelta.trim() || null : null,
          notas: notas.trim() || null,
        },
        acepta,
        pedirTelefono ? telefono : undefined,
      );
      if (r?.ingresar) {
        const volver = `/traslado/${ficha.slug}?pasajeros=${pasajeros}&valijas=${valijas}&dia=${dia}`;
        router.push(`/ingresar?volver=${encodeURIComponent(volver)}`);
        return;
      }
      if (r?.pedirTelefono) setPedirTelefono(true);
      if (r?.error) setErrorReserva(r.error);
    });
  }

  return (
    <aside className={`${panel.panel} ${estilos.suelto}`} aria-label="Reservar">
      <EleccionPunta
        titulo="Desde"
        punta={origen}
        cambiar={setOrigen}
        ficha={ficha}
        ayudaDireccion="Precisión, si hace falta (opcional)"
      />
      <EleccionPunta
        titulo="Hasta"
        punta={destino}
        cambiar={setDestino}
        ficha={ficha}
        ayudaDireccion="Hotel o dirección exacta (opcional)"
      />

      <div className={estilos.fila}>
        <label className={estilos.campo}>
          <span>Día</span>
          <input
            type="date"
            value={dia}
            min={hoyISO()}
            max={hoyISO(365)}
            onChange={(e) => setDia(e.target.value)}
          />
        </label>
        <label className={estilos.campo}>
          <span>Hora</span>
          <input type="time" value={hora} onChange={(e) => setHora(e.target.value)} />
        </label>
      </div>
      <div className={estilos.fila}>
        <label className={estilos.campo}>
          <span>Pasajeros</span>
          <input
            type="number"
            min={1}
            max={100}
            value={pasajeros}
            onChange={(e) => setPasajeros(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <label className={estilos.campo}>
          <span>Valijas</span>
          <input
            type="number"
            min={0}
            max={200}
            value={valijas}
            onChange={(e) => setValijas(Math.max(0, Number(e.target.value) || 0))}
          />
        </label>
      </div>
      <label className={estilos.campo}>
        <span>Vuelo o micro (opcional)</span>
        <input
          value={vueloIda}
          onChange={(e) => setVueloIda(e.target.value)}
          maxLength={20}
          placeholder="Ej.: AR1672"
        />
      </label>

      <label className={salon.terminos}>
        <input type="checkbox" checked={conVuelta} onChange={(e) => setConVuelta(e.target.checked)} />
        <span>También la vuelta, en el mismo vehículo</span>
      </label>
      {conVuelta && (
        <>
          <div className={estilos.fila}>
            <label className={estilos.campo}>
              <span>Día de la vuelta</span>
              <input
                type="date"
                value={diaVuelta}
                min={dia || hoyISO()}
                max={hoyISO(365)}
                onChange={(e) => setDiaVuelta(e.target.value)}
              />
            </label>
            <label className={estilos.campo}>
              <span>Hora</span>
              <input type="time" value={horaVuelta} onChange={(e) => setHoraVuelta(e.target.value)} />
            </label>
          </div>
          <label className={estilos.campo}>
            <span>Vuelo o micro de la vuelta (opcional)</span>
            <input
              value={vueloVuelta}
              onChange={(e) => setVueloVuelta(e.target.value)}
              maxLength={20}
            />
          </label>
        </>
      )}

      {/* --- Vehículos para ese viaje --- */}
      {!viaje ? (
        <p className={salon.nota}>
          {pendientePunta ??
            (conVuelta && dia && hora
              ? "Completá el día y la hora de la vuelta para ver cuánto sale."
              : "Completá el día y la hora para ver cuánto sale en cada vehículo.")}
        </p>
      ) : errorLista ? (
        <p className={salon.error} role="alert">
          <Alerta className={salon.iconoError} />
          {errorLista}
        </p>
      ) : !lista ? (
        <p className={salon.nota}>Calculando…</p>
      ) : (
        <div
          className={estilos.opciones}
          role="radiogroup"
          aria-label="Vehículo"
          aria-busy={buscando}
        >
          {lista.map((o) => {
            const total = o.cotizacion?.total;
            return (
              <button
                key={o.unidad_id}
                type="button"
                role="radio"
                aria-checked={o.unidad_id === elegido}
                disabled={!o.disponible}
                className={`${panel.unidad} ${o.unidad_id === elegido ? panel.seleccionada : ""}`}
                onClick={() => setElegido(o.unidad_id)}
              >
                <span className={estilos.vehiculo}>
                  <strong>{o.nombre}</strong>
                  <small>
                    {plural(o.pasajeros, "pasajero", "pasajeros")}
                    {o.valijas != null ? ` · ${plural(o.valijas, "valija", "valijas")}` : ""}
                  </small>
                  {!o.disponible && o.motivo && <small className={estilos.motivo}>{o.motivo}</small>}
                </span>
                {total && (
                  <strong className={`cifra ${!o.disponible ? estilos.tachado : ""}`}>
                    {pesos(total)}
                  </strong>
                )}
              </button>
            );
          })}
          {!lista.some((o) => o.disponible) && (
            <p className={salon.nota}>
              Ningún vehículo puede hacer ese viaje así. Probá otra hora, otro día o menos
              valijas.
            </p>
          )}
        </div>
      )}

      {cot && (
        <div className={salon.cotizacion}>
          {cot.viajes.map((v) => (
            <div key={v.sentido} className={estilos.viaje}>
              <p className={salon.cuando}>
                {v.sentido === "vuelta" ? "Vuelta · " : ""}
                {diaAR(v.inicio)}, {horaAR(v.inicio)} h
              </p>
              <p className={estilos.recorrido}>
                {v.origen} → {v.destino}
                {v.km != null ? ` · ${String(v.km).replace(".", ",")} km` : ""} · llega{" "}
                {horaAR(v.llegada)} h aprox.
              </p>
              <dl>
                {v.lineas.map((l) => (
                  <div key={l.concepto}>
                    <dt>{l.concepto}</dt>
                    <dd className="cifra">{pesosExactos(l.monto)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          <dl>
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
              se lo pagás al chofer.
            </p>
          ) : (
            <p className={salon.sena}>Se paga el total al reservar.</p>
          )}
        </div>
      )}

      {cot && (
        <label className={estilos.campo}>
          <span>Para el chofer (opcional)</span>
          <textarea
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder="Viajamos con un cochecito, una mascota…"
          />
        </label>
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
          este traslado.
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
          Quien hace el traslado confirma cada pedido. Si no lo acepta, se te devuelve lo
          pagado.
        </p>
      )}
    </aside>
  );
}
