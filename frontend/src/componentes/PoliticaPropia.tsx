"use client";

import { useState } from "react";

/* Las reglas de cancelación que decide cada prestador (docs/05 §3): tramos
   propios —mandan sobre la plantilla— y cuánto se devuelve si la salida no va.
   El backend valida rangos y días repetidos; acá solo se arman las filas. */

import { accionGuardarDatos, type Resultado } from "@/lib/acciones-publicaciones";
import type { PublicacionEdicion, TramoCancelacion } from "@/lib/api";
import { Cruz } from "./Iconos";
import estilos from "./EditorPublicacion.module.css";
import propios from "./UnidadesSalon.module.css";

const MAX_TRAMOS = 5;

type Fila = { dias: string; porcentaje: string };

const filas = (tramos: TramoCancelacion[] | null | undefined): Fila[] =>
  (tramos ?? []).map((t) => ({
    dias: String(t.dias_antes),
    porcentaje: String(t.porcentaje_reintegro),
  }));

export default function PoliticaPropia({
  p,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  correr: (accion: () => Promise<Resultado>) => void;
  pendiente: boolean;
}) {
  const [tramos, setTramos] = useState<Fila[]>(() =>
    p.tramos_cancelacion?.length ? filas(p.tramos_cancelacion) : [{ dias: "", porcentaje: "" }],
  );
  const propia = Boolean(p.tramos_cancelacion?.length);

  const cambiar = (i: number, campo: keyof Fila, valor: string) =>
    setTramos((t) => t.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)));

  return (
    <>
      <h2>Cancelación y reintegros</h2>
      <p className={estilos.ayuda}>
        Lo decidís vos. Podés usar la política elegida arriba o armar la tuya:
        cuánto se devuelve según con cuántos días de anticipación se cancela. Lo
        que ya se reservó sigue con las reglas que tenía.
      </p>

      <section className={propios.parte}>
        <h3>{propia ? "Tus tramos (mandan sobre la política de arriba)" : "Tus tramos"}</h3>
        <form
          className={estilos.filaForm}
          action={() =>
            correr(() =>
              accionGuardarDatos(p.id, {
                tramos_cancelacion: tramos
                  .filter((f) => f.dias !== "" && f.porcentaje !== "")
                  .map((f) => ({
                    dias_antes: Number(f.dias),
                    porcentaje_reintegro: Number(f.porcentaje),
                  })),
              }),
            )
          }
        >
          {tramos.map((f, i) => (
            <div key={i} className={propios.tramo}>
              <label className={propios.campo}>
                <span>Cancelando hasta (días antes)</span>
                <input
                  type="number"
                  min={0}
                  max={365}
                  value={f.dias}
                  onChange={(e) => cambiar(i, "dias", e.target.value)}
                />
              </label>
              <label className={propios.campo}>
                <span>Se devuelve (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={f.porcentaje}
                  onChange={(e) => cambiar(i, "porcentaje", e.target.value)}
                />
              </label>
              {tramos.length > 1 && (
                <button
                  type="button"
                  className={estilos.borrar}
                  onClick={() => setTramos((t) => t.filter((_, j) => j !== i))}
                  aria-label="Quitar este tramo"
                >
                  <Cruz />
                </button>
              )}
            </div>
          ))}
          {tramos.length < MAX_TRAMOS && (
            <button
              type="button"
              onClick={() => setTramos((t) => [...t, { dias: "", porcentaje: "" }])}
            >
              Otro tramo
            </button>
          )}
          <button type="submit" disabled={pendiente}>
            Guardar tramos
          </button>
          {propia && (
            <button
              type="button"
              disabled={pendiente}
              onClick={() => {
                setTramos([{ dias: "", porcentaje: "" }]);
                correr(() => accionGuardarDatos(p.id, { tramos_cancelacion: [] }));
              }}
            >
              Usar la política de arriba
            </button>
          )}
        </form>
      </section>

      {/* Solo las excursiones tienen salidas que se suspenden por falta de gente. */}
      {p.tipo === "excursion" && (
      <section className={propios.parte}>
        <h3>Si la salida no va</h3>
        <p className={estilos.ayuda}>
          Cuando suspendés una salida o no se llega al mínimo de personas, se
          cancelan las reservas y se devuelve este porcentaje de lo pagado.
        </p>
        <form
          className={estilos.filaForm}
          key={p.reintegro_si_no_sale}
          action={(datos) =>
            correr(() =>
              accionGuardarDatos(p.id, {
                reintegro_si_no_sale: Number(datos.get("reintegro") ?? 100),
              }),
            )
          }
        >
          <label className={propios.campo}>
            <span>Se devuelve (%)</span>
            <input
              name="reintegro"
              type="number"
              min={0}
              max={100}
              defaultValue={p.reintegro_si_no_sale ?? 100}
              required
            />
          </label>
          <button type="submit" disabled={pendiente}>
            Guardar
          </button>
        </form>
      </section>
      )}
    </>
  );
}
