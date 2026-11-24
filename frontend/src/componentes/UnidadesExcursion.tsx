"use client";

import { useState } from "react";

/* Las actividades de una excursión (docs/05, etapa 3): precios por tipo de
   pasajero, turnos que se repiten y el panel de salidas. Acá solo se cargan
   datos: mínimos, cupos y choques los valida el backend. */

import {
  accionBorrarUnidad,
  accionCrearPrecioPasajero,
  accionCrearTurno,
  accionCrearUnidad,
  accionQuitarPrecioPasajero,
  accionQuitarTurno,
  type Resultado,
} from "@/lib/acciones-publicaciones";
import type { PublicacionEdicion, TurnoEdicion, UnidadEdicion } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import { Cruz } from "./Iconos";
import PanelSalidas from "./PanelSalidas";
import estilos from "./EditorPublicacion.module.css";
import propios from "./UnidadesSalon.module.css";

type Correr = (accion: () => Promise<Resultado>) => void;

/* Lunes = 0, como en el backend. */
const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const hora = (h: string) => h.slice(0, 5);

function duracion(minutos: number): string {
  if (minutos % (24 * 60) === 0) return plural(minutos / (24 * 60), "día", "días");
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h && m ? `${h} h ${m} min` : h ? `${h} h` : `${m} min`;
}

function diasDelTurno(t: TurnoEdicion): string {
  if (t.dias_semana.length === 7) return "Todos los días";
  return t.dias_semana.map((d) => DIAS[d]).join(", ");
}

function edades(desde: number | null, hasta: number | null): string | null {
  if (desde != null && hasta != null) return `de ${desde} a ${hasta} años`;
  if (desde != null) return `desde ${desde} años`;
  if (hasta != null) return `hasta ${hasta} años`;
  return null;
}

const numero = (v: string) => (v === "" ? null : Number(v));

function Actividad({
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
  const turnos = u.turnos ?? [];
  const precios = u.precios_pasajero ?? [];
  const [salidasAbiertas, setSalidasAbiertas] = useState(false);

  return (
    <li className={estilos.unidad}>
      <div className={estilos.unidadCabecera}>
        <div>
          <strong>{u.nombre}</strong>
          <span className={estilos.unidadDetalle}>
            hasta {plural(u.capacidad, "persona", "personas")} por reserva
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

      {/* --- Precios --- */}
      <section className={propios.parte}>
        <h3>Precios por pasajero</h3>
        <p className={estilos.ayuda}>
          Vos definís los tipos y sus edades: Adulto, Menor de 3 a 12, Jubilado…
          Un precio en 0 es gratis. Sacá la marca de &quot;ocupa lugar&quot; para
          quien no usa cupo, como un bebé en brazos.
        </p>
        {precios.length === 0 ? (
          <p className={estilos.sinTarifa}>
            Sin precios: así no se puede reservar.
          </p>
        ) : (
          <ul className={estilos.tarifas}>
            {precios.map((x) => (
              <li key={x.id}>
                <span>
                  <strong>{x.nombre}</strong>
                  {edades(x.edad_desde, x.edad_hasta) && (
                    <span className={estilos.periodo}>
                      {edades(x.edad_desde, x.edad_hasta)}
                    </span>
                  )}
                  {x.descripcion && (
                    <span className={estilos.periodo}>{x.descripcion}</span>
                  )}
                  {!x.ocupa_lugar && (
                    <span className={estilos.periodo}>no ocupa lugar</span>
                  )}
                </span>
                <span className={`${estilos.precio} cifra`}>
                  {Number(x.precio) === 0 ? "Gratis" : pesos(x.precio)}
                </span>
                <button
                  type="button"
                  className={estilos.borrar}
                  disabled={pendiente}
                  onClick={() =>
                    correr(() => accionQuitarPrecioPasajero(p.id, u.id, x.id))
                  }
                  aria-label={`Quitar precio ${x.nombre}`}
                >
                  <Cruz />
                </button>
              </li>
            ))}
          </ul>
        )}
        <form
          className={estilos.filaForm}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            correr(() =>
              accionCrearPrecioPasajero(p.id, u.id, {
                nombre: v("nombre"),
                precio: v("precio") || "0",
                edad_desde: numero(v("edad_desde")),
                edad_hasta: numero(v("edad_hasta")),
                descripcion: v("descripcion") || null,
                ocupa_lugar: datos.get("ocupa_lugar") === "on",
              }),
            );
          }}
        >
          <label className={propios.campo}>
            <span>Tipo de pasajero</span>
            <input
              name="nombre"
              placeholder="Adulto, Menor…"
              required
              maxLength={60}
            />
          </label>
          <label className={propios.campo}>
            <span>Precio</span>
            {/* step="any": ver el comentario del precio por noche en el editor. */}
            <input name="precio" type="number" min={0} step="any" required />
          </label>
          <label className={propios.campo}>
            <span>Edad desde</span>
            <input name="edad_desde" type="number" min={0} max={120} />
          </label>
          <label className={propios.campo}>
            <span>Edad hasta</span>
            <input name="edad_hasta" type="number" min={0} max={120} />
          </label>
          <label className={propios.campo}>
            <span>Aclaración</span>
            <input
              name="descripcion"
              placeholder="Con carnet, residentes…"
              maxLength={200}
            />
          </label>
          <label className={propios.casillaChica}>
            <input type="checkbox" name="ocupa_lugar" defaultChecked />
            Ocupa lugar
          </label>
          <button type="submit" disabled={pendiente}>
            Agregar precio
          </button>
        </form>
      </section>

      {/* --- Turnos --- */}
      <section className={propios.parte}>
        <h3>Turnos</h3>
        <p className={estilos.ayuda}>
          Los días y la hora en que sale, con su cupo. Si ponés un mínimo de
          personas y no se llega, la salida se cancela sola tantas horas antes
          como elijas, y se devuelve lo que definiste en la política.
        </p>
        {turnos.length === 0 ? (
          <p className={estilos.sinTarifa}>
            Sin turnos: cargá al menos uno, o una salida especial en el panel de
            salidas.
          </p>
        ) : (
          <ul className={estilos.tarifas}>
            {turnos.map((t) => (
              <li key={t.id}>
                <span>
                  <strong>{t.nombre}</strong>
                  <span className={estilos.periodo}>
                    {diasDelTurno(t)} · {hora(t.hora_inicio)} h ·{" "}
                    {duracion(t.duracion_minutos)}
                  </span>
                  <span className={estilos.periodo}>
                    {plural(t.cupo, "lugar", "lugares")}
                    {t.minimo_personas > 1
                      ? ` · mínimo ${t.minimo_personas}, se decide ${t.aviso_minimo_horas} h antes`
                      : " · sin mínimo"}
                  </span>
                  {(t.desde || t.hasta) && (
                    <span className={estilos.periodo}>
                      temporada {t.desde ?? "…"} al {t.hasta ?? "…"}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  className={estilos.borrar}
                  disabled={pendiente}
                  onClick={() => correr(() => accionQuitarTurno(p.id, u.id, t.id))}
                  aria-label={`Quitar turno ${t.nombre}`}
                >
                  <Cruz />
                </button>
              </li>
            ))}
          </ul>
        )}
        <form
          className={estilos.filaForm}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            const dias = DIAS.map((_, i) => i).filter(
              (i) => datos.get(`dia_${i}`) === "on",
            );
            const horas = Number(v("horas") || 0);
            const minutos = Number(v("minutos") || 0);
            correr(() =>
              accionCrearTurno(p.id, u.id, {
                nombre: v("nombre"),
                dias_semana: dias,
                hora_inicio: v("hora_inicio"),
                duracion_minutos: horas * 60 + minutos,
                cupo: Number(v("cupo")),
                minimo_personas: Number(v("minimo") || 1),
                aviso_minimo_horas: Number(v("aviso") || 24),
                desde: v("desde") || null,
                hasta: v("hasta") || null,
              }),
            );
          }}
        >
          <label className={propios.campo}>
            <span>Turno</span>
            <input name="nombre" placeholder="Mañana" required maxLength={80} />
          </label>
          <fieldset className={propios.dias}>
            <legend>Días</legend>
            {DIAS.map((d, i) => (
              <label key={d} className={propios.casillaChica}>
                <input type="checkbox" name={`dia_${i}`} />
                {d}
              </label>
            ))}
          </fieldset>
          <label className={propios.campo}>
            <span>Sale a las</span>
            <input name="hora_inicio" type="time" required />
          </label>
          <label className={propios.campo}>
            <span>Dura (horas)</span>
            <input name="horas" type="number" min={0} max={336} defaultValue={2} />
          </label>
          <label className={propios.campo}>
            <span>y minutos</span>
            <input name="minutos" type="number" min={0} max={59} step={5} defaultValue={0} />
          </label>
          <label className={propios.campo}>
            <span>Cupo</span>
            <input name="cupo" type="number" min={1} max={500} required />
          </label>
          <label className={propios.campo}>
            <span>Mínimo de personas</span>
            <input name="minimo" type="number" min={1} max={500} defaultValue={1} />
          </label>
          <label className={propios.campo}>
            <span>Se decide (h antes)</span>
            <input name="aviso" type="number" min={0} max={720} defaultValue={24} />
          </label>
          <label className={propios.campo}>
            <span>Temporada desde</span>
            <input name="desde" type="date" />
          </label>
          <label className={propios.campo}>
            <span>hasta</span>
            <input name="hasta" type="date" />
          </label>
          <button type="submit" disabled={pendiente}>
            Agregar turno
          </button>
        </form>
      </section>

      {/* --- Salidas --- */}
      {/* Se pide recién al abrirlo: cerrado no tiene por qué ir a la API. */}
      <details
        className={estilos.agenda}
        onToggle={(e) =>
          setSalidasAbiertas((e.currentTarget as HTMLDetailsElement).open)
        }
      >
        <summary>Salidas, anotados y suspensiones</summary>
        {salidasAbiertas && (
          <PanelSalidas
            publicacionId={p.id}
            unidadId={u.id}
            reintegroSiNoSale={p.reintegro_si_no_sale ?? 100}
            // Al cambiar los turnos, el panel se vuelve a pedir.
            key={turnos.map((t) => t.id).join()}
          />
        )}
      </details>
    </li>
  );
}

export default function UnidadesExcursion({
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
      <h2>Actividades</h2>
      <p className={estilos.ayuda}>
        Cada actividad es lo que alguien reserva: la cabalgata, la visita, el
        trekking. Lleva sus precios, sus turnos y cuántas personas entran en una
        misma reserva.
      </p>
      <ul className={estilos.unidades}>
        {p.unidades.map((u) => (
          <Actividad key={u.id} p={p} u={u} correr={correr} pendiente={pendiente} />
        ))}
      </ul>
      <form
        className={estilos.filaForm}
        action={(datos) => {
          const v = (k: string) => String(datos.get(k) ?? "").trim();
          correr(() =>
            accionCrearUnidad(p.id, { nombre: v("nombre"), capacidad: Number(v("capacidad")) }),
          );
        }}
      >
        <input
          name="nombre"
          placeholder="Nombre de la actividad"
          required
          maxLength={120}
        />
        <input
          name="capacidad"
          type="number"
          min={1}
          max={500}
          placeholder="Máximo por reserva"
          aria-label="Cuántas personas como máximo en una misma reserva"
          required
        />
        <button type="submit" disabled={pendiente}>
          Agregar actividad
        </button>
      </form>
    </>
  );
}
