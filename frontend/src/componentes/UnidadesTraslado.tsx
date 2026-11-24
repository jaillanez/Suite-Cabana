"use client";

import { useState } from "react";

/* Traslados del prestador (docs/06, etapa 3): los lugares con nombre, cada
   vehículo con sus recorridos fijos, su tarifa por kilómetro y sus reglas, y su
   agenda. Acá solo se cargan datos: rangos, choques y duplicados los valida el
   backend, y el precio de un viaje lo calcula él. */

import {
  accionBorrarUnidad,
  accionCrearLugar,
  accionCrearTramo,
  accionCrearUnidad,
  accionEditarLugar,
  accionGuardarTarifaTraslado,
  accionQuitarLugar,
  accionQuitarTramo,
  type Resultado,
} from "@/lib/acciones-publicaciones";
import type {
  LugarTrasladoEdicion,
  PublicacionEdicion,
  TarifaTrasladoEdicion,
  UnidadEdicion,
} from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import AgendaSalon from "./AgendaSalon";
import { Cruz } from "./Iconos";
import MapaSelector from "./MapaSelector";
import estilos from "./EditorPublicacion.module.css";
import propios from "./UnidadesSalon.module.css";
import tr from "./UnidadesTraslado.module.css";

type Correr = (accion: () => Promise<Resultado>) => void;

const hora = (h: string | null) => (h ? h.slice(0, 5) : "");

function duracion(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h && m ? `${h} h ${m} min` : h ? `${h} h` : `${m} min`;
}

/* Lo que rige si el prestador todavía no guardó nada: lo mismo que el backend. */
const REGLAS_POR_DEFECTO: TarifaTrasladoEdicion = {
  precio_km: null,
  bajada: "0",
  minimo: "0",
  radio_km: null,
  factor_ruta: "1.3",
  velocidad_kmh: 60,
  recargo_nocturno_desde: null,
  recargo_nocturno_hasta: null,
  recargo_nocturno_porcentaje: "0",
  vuelve_a_base: true,
  anticipacion_minima_horas: 12,
};

/* --- Lugares --- */

function Lugar({
  p,
  lugar,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  lugar: LugarTrasladoEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  const [moviendo, setMoviendo] = useState(false);
  return (
    <li>
      <span>
        <strong>{lugar.nombre}</strong>
        {lugar.es_base && <span className={estilos.periodo}>base de los vehículos</span>}
      </span>
      <span className={tr.acciones}>
        {!lugar.es_base && (
          <button
            type="button"
            className={estilos.borrar}
            disabled={pendiente}
            onClick={() => correr(() => accionEditarLugar(p.id, lugar.id, { es_base: true }))}
          >
            Hacer base
          </button>
        )}
        <button
          type="button"
          className={estilos.borrar}
          disabled={pendiente}
          aria-expanded={moviendo}
          onClick={() => setMoviendo(!moviendo)}
        >
          {moviendo ? "Listo" : "Mover"}
        </button>
        <button
          type="button"
          className={estilos.borrar}
          disabled={pendiente}
          onClick={() => correr(() => accionQuitarLugar(p.id, lugar.id))}
          aria-label={`Quitar ${lugar.nombre}`}
        >
          <Cruz />
        </button>
      </span>
      {moviendo && (
        <div className={tr.mapaLugar}>
          <MapaSelector
            lat={lugar.lat}
            lon={lugar.lon}
            ayuda={`Tocá el mapa o arrastrá el pin hasta ${lugar.nombre}.`}
            onMover={(lat, lon) =>
              correr(() => accionEditarLugar(p.id, lugar.id, { lat, lon }))
            }
          />
        </div>
      )}
    </li>
  );
}

function Lugares({
  p,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  const lugares = p.lugares_traslado ?? [];
  const [punto, setPunto] = useState<{ lat: number; lon: number } | null>(null);
  return (
    <>
      <h2>Lugares</h2>
      <p className={estilos.ayuda}>
        Los puntos de donde salen y adonde llegan tus viajes: el aeropuerto, la
        terminal, el centro. Con ellos armás los recorridos de precio fijo. Si
        marcás uno como base, el radio por kilómetro se mide desde ahí; si no,
        desde la ubicación de la publicación.
      </p>
      {lugares.length === 0 ? (
        <p className={estilos.sinTarifa}>
          Sin lugares todavía. Hacen falta para los recorridos de precio fijo; para
          cobrar solo por kilómetro no.
        </p>
      ) : (
        <ul className={estilos.tarifas}>
          {lugares.map((l) => (
            <Lugar key={l.id} p={p} lugar={l} correr={correr} pendiente={pendiente} />
          ))}
        </ul>
      )}
      <form
        className={tr.formLugar}
        action={(datos) => {
          if (!punto) return;
          const nombre = String(datos.get("nombre") ?? "").trim();
          correr(() =>
            accionCrearLugar(p.id, {
              nombre,
              ...punto,
              es_base: datos.get("es_base") === "on",
            }),
          );
        }}
      >
        <MapaSelector
          lat={p.lat}
          lon={p.lon}
          ayuda="Tocá el mapa donde queda el lugar nuevo."
          onMover={(lat, lon) => setPunto({ lat, lon })}
        />
        <div className={estilos.filaForm}>
          <label className={propios.campo}>
            <span>Nombre del lugar</span>
            <input name="nombre" placeholder="Aeropuerto" required minLength={2} maxLength={120} />
          </label>
          <label className={propios.casillaChica}>
            <input type="checkbox" name="es_base" />
            Es la base
          </label>
          <button type="submit" disabled={pendiente || !punto}>
            {punto ? "Agregar lugar" : "Marcá el punto en el mapa"}
          </button>
        </div>
      </form>
    </>
  );
}

/* --- Vehículos --- */

function Recorridos({
  p,
  u,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  u: UnidadEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  const tramos = u.tramos_traslado ?? [];
  const lugares = p.lugares_traslado ?? [];
  return (
    <section className={propios.parte}>
      <h3>Recorridos de precio fijo</h3>
      {tramos.length > 0 && (
        <ul className={estilos.tarifas}>
          {tramos.map((t) => (
            <li key={t.id}>
              <span>
                <strong>
                  {t.origen} {t.ambos_sentidos ? "↔" : "→"} {t.destino}
                </strong>
                <span className={estilos.periodo}>
                  {duracion(t.duracion_minutos)}
                  {t.ambos_sentidos ? " · ida o vuelta" : " · solo en este sentido"}
                </span>
              </span>
              <span className={`${estilos.precio} cifra`}>
                {pesos(t.precio)}
                {t.por_persona ? " por persona" : ""}
              </span>
              <button
                type="button"
                className={estilos.borrar}
                disabled={pendiente}
                onClick={() => correr(() => accionQuitarTramo(p.id, u.id, t.id))}
                aria-label={`Quitar recorrido ${t.origen} a ${t.destino}`}
              >
                <Cruz />
              </button>
            </li>
          ))}
        </ul>
      )}
      {lugares.length < 2 ? (
        <p className={estilos.ayuda}>
          Cargá al menos dos lugares para armar un recorrido de precio fijo.
        </p>
      ) : (
        <form
          className={estilos.filaForm}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            correr(() =>
              accionCrearTramo(p.id, u.id, {
                origen_id: v("origen_id"),
                destino_id: v("destino_id"),
                precio: v("precio"),
                por_persona: v("cobro") === "persona",
                duracion_minutos: Number(v("duracion") || 0),
                ambos_sentidos: datos.get("ambos_sentidos") === "on",
              }),
            );
          }}
        >
          <label className={propios.campo}>
            <span>Desde</span>
            <select name="origen_id" required defaultValue="">
              <option value="" disabled>
                Elegí…
              </option>
              {lugares.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className={propios.campo}>
            <span>Hasta</span>
            <select name="destino_id" required defaultValue="">
              <option value="" disabled>
                Elegí…
              </option>
              {lugares.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className={propios.campo}>
            <span>Precio</span>
            {/* step="any": ver el comentario del precio por noche en el editor. */}
            <input name="precio" type="number" min={1} step="any" required />
          </label>
          <label className={propios.campo}>
            <span>Se cobra</span>
            <select name="cobro" defaultValue="vehiculo">
              <option value="vehiculo">por el vehículo</option>
              <option value="persona">por persona</option>
            </select>
          </label>
          <label className={propios.campo}>
            <span>Dura (min)</span>
            <input name="duracion" type="number" min={5} max={2880} required placeholder="40" />
          </label>
          <label className={propios.casillaChica}>
            <input type="checkbox" name="ambos_sentidos" defaultChecked />
            Vale también a la vuelta
          </label>
          <button type="submit" disabled={pendiente}>
            Agregar recorrido
          </button>
        </form>
      )}
    </section>
  );
}

function Reglas({
  p,
  u,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  u: UnidadEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  const r = u.tarifa_traslado ?? REGLAS_POR_DEFECTO;
  const conKm = r.precio_km != null;
  const conRecargo = Number(r.recargo_nocturno_porcentaje) > 0;
  return (
    <section className={propios.parte}>
      <h3>Por kilómetro y reglas del vehículo</h3>
      <p className={estilos.ayuda}>
        {conKm
          ? `Cobra ${pesos(r.precio_km!)} por km${Number(r.bajada) ? ` más ${pesos(r.bajada)} de bajada` : ""}${Number(r.minimo) ? `, mínimo ${pesos(r.minimo)}` : ""}${r.radio_km ? `, hasta ${r.radio_km} km de la base` : ""}.`
          : "Sin precio por km: este vehículo hace solo los recorridos fijos."}{" "}
        {conRecargo &&
          `Recargo nocturno del ${Number(r.recargo_nocturno_porcentaje)} % de ${hora(r.recargo_nocturno_desde)} a ${hora(r.recargo_nocturno_hasta)}. `}
        Se reserva con {plural(r.anticipacion_minima_horas, "hora", "horas")} de
        anticipación{r.vuelve_a_base ? " y cada viaje cuenta la vuelta a la base" : ""}.
      </p>
      <form
        // Al guardar cambian los valores: el form se vuelve a armar con los nuevos.
        key={JSON.stringify(r)}
        className={estilos.filaForm}
        action={(datos) => {
          const v = (k: string) => String(datos.get(k) ?? "").trim();
          const recargo = v("recargo") || "0";
          correr(() =>
            accionGuardarTarifaTraslado(p.id, u.id, {
              precio_km: v("precio_km") || null,
              bajada: v("bajada") || "0",
              minimo: v("minimo") || "0",
              radio_km: v("radio_km") ? Number(v("radio_km")) : null,
              factor_ruta: v("factor_ruta") || "1.3",
              velocidad_kmh: Number(v("velocidad") || 60),
              recargo_nocturno_porcentaje: recargo,
              recargo_nocturno_desde: Number(recargo) > 0 ? v("desde") || null : null,
              recargo_nocturno_hasta: Number(recargo) > 0 ? v("hasta") || null : null,
              vuelve_a_base: datos.get("vuelve_a_base") === "on",
              anticipacion_minima_horas: Number(v("anticipacion") || 0),
            }),
          );
        }}
      >
        <label className={propios.campo}>
          <span>Precio por km</span>
          <input
            name="precio_km"
            type="number"
            min={1}
            step="any"
            defaultValue={r.precio_km != null ? Number(r.precio_km) : ""}
            placeholder="Vacío: no cobra por km"
          />
        </label>
        <label className={propios.campo}>
          <span>Bajada</span>
          <input name="bajada" type="number" min={0} step="any" defaultValue={Number(r.bajada) || ""} />
        </label>
        <label className={propios.campo}>
          <span>Mínimo por viaje</span>
          <input name="minimo" type="number" min={0} step="any" defaultValue={Number(r.minimo) || ""} />
        </label>
        <label className={propios.campo}>
          <span>Hasta (km de la base)</span>
          <input
            name="radio_km"
            type="number"
            min={1}
            max={2000}
            defaultValue={r.radio_km ?? ""}
            placeholder="Sin límite"
          />
        </label>
        <label className={propios.campo}>
          <span>Factor de ruta</span>
          <input
            name="factor_ruta"
            type="number"
            min={1}
            max={3}
            step={0.05}
            defaultValue={Number(r.factor_ruta)}
            aria-describedby={`factor-${u.id}`}
          />
        </label>
        <label className={propios.campo}>
          <span>Velocidad media (km/h)</span>
          <input name="velocidad" type="number" min={10} max={150} defaultValue={r.velocidad_kmh} />
        </label>
        <label className={propios.campo}>
          <span>Recargo nocturno (%)</span>
          <input
            name="recargo"
            type="number"
            min={0}
            max={200}
            defaultValue={Number(r.recargo_nocturno_porcentaje) || ""}
            placeholder="Sin recargo"
          />
        </label>
        <label className={propios.campo}>
          <span>desde las</span>
          <input name="desde" type="time" defaultValue={hora(r.recargo_nocturno_desde)} />
        </label>
        <label className={propios.campo}>
          <span>hasta las</span>
          <input name="hasta" type="time" defaultValue={hora(r.recargo_nocturno_hasta)} />
        </label>
        <label className={propios.campo}>
          <span>Anticipación (horas)</span>
          <input
            name="anticipacion"
            type="number"
            min={0}
            max={720}
            defaultValue={r.anticipacion_minima_horas}
          />
        </label>
        <label className={propios.casillaChica}>
          <input type="checkbox" name="vuelve_a_base" defaultChecked={r.vuelve_a_base} />
          Vuelve a la base después de cada viaje
        </label>
        <button type="submit" disabled={pendiente}>
          Guardar reglas
        </button>
      </form>
      <p id={`factor-${u.id}`} className={estilos.ayuda}>
        Los km se miden en línea recta entre los dos puntos y se multiplican por
        el factor de ruta: 1,3 suma un 30 % por las curvas del camino. Subilo si
        en tu zona los caminos dan más vueltas.
      </p>
    </section>
  );
}

function Vehiculo({
  p,
  u,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  u: UnidadEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  const [agendaAbierta, setAgendaAbierta] = useState(false);
  return (
    <li className={estilos.unidad}>
      <div className={estilos.unidadCabecera}>
        <div>
          <strong>{u.nombre}</strong>
          <span className={estilos.unidadDetalle}>
            {plural(u.capacidad, "pasajero", "pasajeros")}
            {u.equipaje != null ? ` · ${plural(u.equipaje, "valija", "valijas")}` : ""}
            {u.preparacion_minutos ? ` · ${u.preparacion_minutos} min entre viajes` : ""}
          </span>
        </div>
        <button
          type="button"
          className={estilos.borrar}
          disabled={pendiente}
          onClick={() => correr(() => accionBorrarUnidad(p.id, u.id))}
        >
          Quitar
        </button>
      </div>

      <Recorridos p={p} u={u} correr={correr} pendiente={pendiente} />
      <Reglas p={p} u={u} correr={correr} pendiente={pendiente} />

      {/* Se pide recién al abrirla: cerrada no tiene por qué ir a la API. */}
      <details
        className={estilos.agenda}
        onToggle={(e) => setAgendaAbierta((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>Agenda del vehículo</summary>
        {agendaAbierta && <AgendaSalon publicacionId={p.id} unidadId={u.id} vehiculo />}
      </details>
    </li>
  );
}

export default function UnidadesTraslado({
  p,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  correr: Correr;
  pendiente: boolean;
}) {
  return (
    <>
      <Lugares p={p} correr={correr} pendiente={pendiente} />

      <h2 className={tr.segundoTitulo}>Vehículos</h2>
      <p className={estilos.ayuda}>
        Cada vehículo es lo que alguien reserva entero, con chofer: cuántos
        pasajeros y valijas entran, sus recorridos de precio fijo y, si querés, un
        precio por kilómetro para cualquier dirección.
      </p>
      <ul className={estilos.unidades}>
        {p.unidades.map((u) => (
          <Vehiculo key={u.id} p={p} u={u} correr={correr} pendiente={pendiente} />
        ))}
      </ul>
      <form
        className={estilos.filaForm}
        action={(datos) => {
          const v = (k: string) => String(datos.get(k) ?? "").trim();
          correr(() =>
            accionCrearUnidad(p.id, {
              nombre: v("nombre"),
              capacidad: Number(v("capacidad")),
              equipaje: v("equipaje") ? Number(v("equipaje")) : null,
              preparacion_minutos: Number(v("preparacion") || 0),
            }),
          );
        }}
      >
        <label className={propios.campo}>
          <span>Vehículo</span>
          <input name="nombre" placeholder="Auto, Combi 15…" required maxLength={120} />
        </label>
        <label className={propios.campo}>
          <span>Pasajeros</span>
          <input name="capacidad" type="number" min={1} max={80} required />
        </label>
        <label className={propios.campo}>
          <span>Valijas</span>
          <input name="equipaje" type="number" min={0} max={200} placeholder="Sin límite" />
        </label>
        <label className={propios.campo}>
          <span>Entre viajes (min)</span>
          <input name="preparacion" type="number" min={0} max={720} placeholder="0" />
        </label>
        <button type="submit" disabled={pendiente}>
          Agregar vehículo
        </button>
      </form>
    </>
  );
}
