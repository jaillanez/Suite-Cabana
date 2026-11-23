"use client";

/* Los espacios de un salón y cómo se cobran (docs/04 §4): turnos fijos, precio
   por hora y adicionales. Acá solo se cargan datos: los precios, mínimos y
   choques los calcula y valida el backend. */

import {
  accionBorrarAdicional,
  accionBorrarFranja,
  accionBorrarUnidad,
  accionCrearAdicional,
  accionCrearFranja,
  accionCrearUnidad,
  accionGuardarTarifaHoraria,
  accionQuitarTarifaHoraria,
  type Resultado,
} from "@/lib/acciones-publicaciones";
import type {
  PreciosPorDia,
  PublicacionEdicion,
  UnidadEdicion,
} from "@/lib/api";
import { pesos } from "@/lib/formato";
import { Cruz } from "./Iconos";
import estilos from "./EditorPublicacion.module.css";
import propios from "./UnidadesSalon.module.css";

type Correr = (accion: () => Promise<Resultado>) => void;

/* El fin de semana es lo que cambia de precio en un salón: se ofrece cargarlo
   aparte. "4" es viernes (lunes = 0, como en el backend). */
const DIAS_ESPECIALES = [
  { clave: "4", nombre: "Viernes" },
  { clave: "5", nombre: "Sábado" },
  { clave: "6", nombre: "Domingo" },
];

const hora = (h: string) => h.slice(0, 5);
const cruzaMedianoche = (desde: string, hasta: string) => hasta <= desde;

function preciosDelFinde(datos: FormData): PreciosPorDia {
  const precios: Record<string, string> = {};
  for (const d of DIAS_ESPECIALES) {
    const v = String(datos.get(`dia_${d.clave}`) ?? "").trim();
    if (v) precios[d.clave] = v;
  }
  return Object.keys(precios).length ? precios : null;
}

function DistintoElFinde({ precios }: { precios: PreciosPorDia }) {
  if (!precios) return null;
  return (
    <span className={estilos.periodo}>
      {DIAS_ESPECIALES.filter((d) => precios[d.clave])
        .map((d) => `${d.nombre} ${pesos(precios[d.clave])}`)
        .join(" · ")}
    </span>
  );
}

/* `actuales`: al editar, lo ya guardado. Sin esto, "Guardar cambios" mandaría
   los días vacíos y borraría los precios del fin de semana sin aviso. */
function CamposFinde({ actuales = null }: { actuales?: PreciosPorDia }) {
  return (
    <>
      {DIAS_ESPECIALES.map((d) => (
        <label key={d.clave} className={propios.campo}>
          <span>{d.nombre}</span>
          <input
            name={`dia_${d.clave}`}
            type="number"
            min={1}
            step="any"
            placeholder="Mismo precio"
            defaultValue={
              actuales?.[d.clave] ? Number(actuales[d.clave]) : undefined
            }
            aria-label={`Precio del ${d.nombre.toLowerCase()}, si es distinto`}
          />
        </label>
      ))}
    </>
  );
}

function Espacio({
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
  const th = u.tarifa_horaria;
  const sinPrecio = u.franjas.length === 0 && !th;

  return (
    <li className={estilos.unidad}>
      <div className={estilos.unidadCabecera}>
        <div>
          <strong>{u.nombre}</strong>
          <span className={estilos.unidadDetalle}>
            hasta {u.capacidad} de pie
            {u.capacidad_sentados ? ` · ${u.capacidad_sentados} sentados` : ""}
            {u.capacidad_base ? ` · ${u.capacidad_base} sin cargo extra` : ""}
            {u.preparacion_minutos
              ? ` · ${u.preparacion_minutos} min de preparación`
              : ""}
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

      {sinPrecio && (
        <p className={estilos.sinTarifa}>
          Sin turnos ni precio por hora: así no se puede reservar. Cargá al
          menos uno de los dos.
        </p>
      )}

      {/* --- Turnos --- */}
      <section className={propios.parte}>
        <h3>Turnos</h3>
        <p className={estilos.ayuda}>
          Horarios fijos con su precio, por ejemplo &quot;Noche, de 21 a 5
          h&quot;. Si termina antes de empezar, es al día siguiente.
        </p>
        {u.franjas.length > 0 && (
          <ul className={estilos.tarifas}>
            {u.franjas.map((f) => (
              <li key={f.id}>
                <span>
                  <strong>{f.nombre}</strong>
                  <span className={estilos.periodo}>
                    {hora(f.hora_inicio)} a {hora(f.hora_fin)} h
                    {cruzaMedianoche(f.hora_inicio, f.hora_fin)
                      ? " (al día siguiente)"
                      : ""}
                  </span>
                  <DistintoElFinde precios={f.precios_dia_semana} />
                </span>
                <span className={`${estilos.precio} cifra`}>
                  {pesos(f.precio)}
                </span>
                <button
                  type="button"
                  className={estilos.borrar}
                  disabled={pendiente}
                  onClick={() =>
                    correr(() => accionBorrarFranja(p.id, u.id, f.id))
                  }
                  aria-label={`Quitar turno ${f.nombre}`}
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
              accionCrearFranja(p.id, u.id, {
                nombre: v("nombre"),
                hora_inicio: v("hora_inicio"),
                hora_fin: v("hora_fin"),
                precio: v("precio"),
                precios_dia_semana: preciosDelFinde(datos),
              }),
            );
          }}
        >
          <label className={propios.campo}>
            <span>Turno</span>
            <input
              name="nombre"
              placeholder="Mañana, Noche…"
              required
              maxLength={80}
            />
          </label>
          <label className={propios.campo}>
            <span>Desde</span>
            <input name="hora_inicio" type="time" required />
          </label>
          <label className={propios.campo}>
            <span>Hasta</span>
            <input name="hora_fin" type="time" required />
          </label>
          {/* step="any": ver el comentario del precio por noche en el editor. */}
          <label className={propios.campo}>
            <span>Precio</span>
            <input name="precio" type="number" min={1} step="any" required />
          </label>
          <CamposFinde />
          <button type="submit" disabled={pendiente}>
            Agregar turno
          </button>
        </form>
      </section>

      {/* --- Por horas --- */}
      <section className={propios.parte}>
        <h3>Alquiler por horas</h3>
        <p className={estilos.ayuda}>
          Para que reserven de, por ejemplo, 15 a 18 h. Opcional: si solo
          alquilás por turnos, dejalo vacío. Turnos y horas comparten la agenda:
          no se pisan.
        </p>
        {th && (
          <ul className={estilos.tarifas}>
            <li>
              <span>
                <strong>Por hora</strong>
                <span className={estilos.periodo}>
                  de {hora(th.hora_apertura)} a {hora(th.hora_cierre)} h ·
                  mínimo {th.horas_minimas} h
                  {th.recargo_nocturno_desde &&
                  Number(th.recargo_nocturno_porcentaje) > 0
                    ? ` · +${Number(th.recargo_nocturno_porcentaje)} % desde las ${hora(
                        th.recargo_nocturno_desde,
                      )}`
                    : ""}
                </span>
                <DistintoElFinde precios={th.precios_dia_semana} />
              </span>
              <span className={`${estilos.precio} cifra`}>
                {pesos(th.precio_hora)}
              </span>
              <button
                type="button"
                className={estilos.borrar}
                disabled={pendiente}
                onClick={() =>
                  correr(() => accionQuitarTarifaHoraria(p.id, u.id))
                }
                aria-label="Quitar el alquiler por horas"
              >
                <Cruz />
              </button>
            </li>
          </ul>
        )}
        <form
          className={estilos.filaForm}
          // key: al guardar, el formulario se vuelve a armar con lo guardado.
          key={th ? JSON.stringify(th) : "nueva"}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            correr(() =>
              accionGuardarTarifaHoraria(p.id, u.id, {
                precio_hora: v("precio_hora"),
                horas_minimas: Number(v("horas_minimas") || 1),
                hora_apertura: v("hora_apertura"),
                hora_cierre: v("hora_cierre"),
                recargo_nocturno_desde: v("recargo_desde") || null,
                recargo_nocturno_porcentaje: v("recargo_porcentaje") || "0",
                precios_dia_semana: preciosDelFinde(datos),
              }),
            );
          }}
        >
          <label className={propios.campo}>
            <span>Precio por hora</span>
            <input
              name="precio_hora"
              type="number"
              min={1}
              step="any"
              defaultValue={th ? Number(th.precio_hora) : undefined}
              required
            />
          </label>
          <label className={propios.campo}>
            <span>Mínimo de horas</span>
            <input
              name="horas_minimas"
              type="number"
              min={1}
              max={24}
              defaultValue={th?.horas_minimas ?? 1}
            />
          </label>
          <label className={propios.campo}>
            <span>Abre</span>
            <input
              name="hora_apertura"
              type="time"
              required
              defaultValue={th ? hora(th.hora_apertura) : undefined}
            />
          </label>
          <label className={propios.campo}>
            <span>Cierra</span>
            <input
              name="hora_cierre"
              type="time"
              required
              defaultValue={th ? hora(th.hora_cierre) : undefined}
            />
          </label>
          <label className={propios.campo}>
            <span>Recargo desde</span>
            <input
              name="recargo_desde"
              type="time"
              defaultValue={
                th?.recargo_nocturno_desde
                  ? hora(th.recargo_nocturno_desde)
                  : undefined
              }
            />
          </label>
          <label className={propios.campo}>
            <span>Recargo %</span>
            <input
              name="recargo_porcentaje"
              type="number"
              min={0}
              max={100}
              step="any"
              placeholder="Sin recargo"
              defaultValue={
                th && Number(th.recargo_nocturno_porcentaje) > 0
                  ? Number(th.recargo_nocturno_porcentaje)
                  : undefined
              }
            />
          </label>
          <CamposFinde actuales={th?.precios_dia_semana ?? null} />
          <button type="submit" disabled={pendiente}>
            {th ? "Guardar cambios" : "Activar por horas"}
          </button>
        </form>
      </section>

      {/* --- Adicionales --- */}
      <section className={propios.parte}>
        <h3>Adicionales</h3>
        <p className={estilos.ayuda}>
          Lo que se puede sumar con su precio: vajilla, sonido, limpieza, mozos.
          Por evento o por invitado.
        </p>
        {u.adicionales.length > 0 && (
          <ul className={estilos.tarifas}>
            {u.adicionales.map((a) => (
              <li key={a.id}>
                <span>
                  <strong>{a.nombre}</strong>
                  <span className={estilos.periodo}>
                    {a.por_persona ? "por invitado" : "por evento"}
                  </span>
                </span>
                <span className={`${estilos.precio} cifra`}>
                  {pesos(a.precio)}
                </span>
                <button
                  type="button"
                  className={estilos.borrar}
                  disabled={pendiente}
                  onClick={() =>
                    correr(() => accionBorrarAdicional(p.id, u.id, a.id))
                  }
                  aria-label={`Quitar ${a.nombre}`}
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
              accionCrearAdicional(p.id, u.id, {
                nombre: v("nombre"),
                precio: v("precio"),
                por_persona: datos.get("por_persona") === "on",
              }),
            );
          }}
        >
          <input
            name="nombre"
            placeholder="Nombre (Vajilla, Sonido…)"
            required
            maxLength={80}
          />
          <input
            name="precio"
            type="number"
            min={1}
            step="any"
            placeholder="Precio"
            required
          />
          <label className={propios.casillaChica}>
            <input type="checkbox" name="por_persona" />
            Por invitado
          </label>
          <button type="submit" disabled={pendiente}>
            Agregar
          </button>
        </form>
      </section>
    </li>
  );
}

export default function UnidadesSalon({
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
      <h2>Espacios</h2>
      <p className={estilos.ayuda}>
        Cada espacio es lo que alguien reserva: el salón, el quincho, el jardín.
        Si se alquilan por separado, cargalos por separado.
      </p>

      <ul className={estilos.unidades}>
        {p.unidades.map((u) => (
          <Espacio
            key={u.id}
            p={p}
            u={u}
            correr={correr}
            pendiente={pendiente}
          />
        ))}
      </ul>

      <form
        className={estilos.filaForm}
        action={(datos) => {
          const v = (k: string) => String(datos.get(k) ?? "").trim();
          const n = (k: string) => (v(k) ? Number(v(k)) : null);
          correr(() =>
            accionCrearUnidad(p.id, {
              nombre: v("nombre"),
              capacidad: Number(v("capacidad")),
              capacidad_sentados: n("capacidad_sentados"),
              capacidad_base: n("capacidad_base"),
              cargo_persona_extra: v("cargo_persona_extra") || "0",
              preparacion_minutos: n("preparacion_minutos") ?? 0,
            }),
          );
        }}
      >
        <input
          name="nombre"
          placeholder="Nombre del espacio"
          required
          maxLength={120}
        />
        <input
          name="capacidad"
          type="number"
          min={1}
          max={5000}
          placeholder="Capacidad de pie"
          required
        />
        <input
          name="capacidad_sentados"
          type="number"
          min={1}
          max={5000}
          placeholder="Sentados (opcional)"
        />
        <input
          name="capacidad_base"
          type="number"
          min={1}
          max={5000}
          placeholder="Incluidos en el precio"
          aria-label="Invitados incluidos en el precio; desde ahí se cobra extra"
        />
        <input
          name="cargo_persona_extra"
          type="number"
          min={0}
          step="any"
          placeholder="Por invitado extra"
        />
        <input
          name="preparacion_minutos"
          type="number"
          min={0}
          max={720}
          step={15}
          placeholder="Preparación (min)"
          aria-label="Minutos libres entre un evento y el siguiente"
        />
        <button type="submit" disabled={pendiente}>
          Agregar espacio
        </button>
      </form>
    </>
  );
}
