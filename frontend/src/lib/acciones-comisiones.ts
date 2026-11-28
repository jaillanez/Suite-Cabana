"use server";

/* Reglas de comisión del operador (docs/00 §7.4). La validación y el cálculo son
   del backend: acá solo se pasa el token y se devuelve el resultado o el error. */

import { revalidatePath } from "next/cache";

import {
  ApiError,
  cambiarEstadoRegla,
  crearReglaComision,
  editarReglaComision,
  historialReglaComision,
  simularComision,
  type HistorialRegla,
  type ReglaComisionIn,
  type ReglaComisionOp,
  type SimulacionComision,
} from "./api";
import { tokenActual } from "./sesion";

type Error_ = { error: string };

function problema(e: unknown, porDefecto: string): Error_ {
  if (e instanceof ApiError) {
    const d = e.detalle;
    if (Array.isArray(d)) {
      const primero = d[0] as { msg?: string } | undefined;
      return { error: primero?.msg?.replace(/^Value error, /, "") ?? porDefecto };
    }
    return { error: e.message || porDefecto };
  }
  return { error: porDefecto };
}

async function conToken<T>(
  llamada: (token: string) => Promise<T>,
  porDefecto: string,
): Promise<{ ok: T } | Error_> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { ok: await llamada(token) };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

export async function accionGuardarRegla(
  id: string | null,
  datos: ReglaComisionIn,
): Promise<{ ok: ReglaComisionOp } | Error_> {
  const r = await conToken(
    (t) => (id ? editarReglaComision(t, id, datos) : crearReglaComision(t, datos)),
    "No pudimos guardar la regla.",
  );
  revalidatePath("/admin/comisiones");
  return r;
}

export async function accionEstadoRegla(id: string, activar: boolean) {
  const r = await conToken((t) => cambiarEstadoRegla(t, id, activar), "No pudimos cambiarla.");
  revalidatePath("/admin/comisiones");
  return r;
}

export async function accionHistorialRegla(
  id: string,
): Promise<{ ok: HistorialRegla[] } | Error_> {
  return conToken((t) => historialReglaComision(t, id), "No pudimos traer el historial.");
}

export async function accionSimular(
  caso: Record<string, unknown>,
): Promise<{ ok: SimulacionComision } | Error_> {
  return conToken((t) => simularComision(t, caso), "No pudimos simular ese caso.");
}
