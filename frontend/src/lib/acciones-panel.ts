"use server";

import { revalidatePath } from "next/cache";

import { ApiError, guardarFavorito, sacarFavorito } from "./api";
import { tokenActual } from "./sesion";

export type ResultadoFavorito = { guardado: boolean } | { error: string };

/** Guarda o saca un favorito. Sin sesión lo dice, en vez de fallar en silencio. */
export async function accionFavorito(
  publicacionId: string,
  guardar: boolean,
): Promise<ResultadoFavorito> {
  const token = await tokenActual();
  if (!token) return { error: "Ingresá para guardar alojamientos" };
  try {
    if (guardar) await guardarFavorito(token, publicacionId);
    else await sacarFavorito(token, publicacionId);
  } catch (e) {
    return {
      error: e instanceof ApiError ? e.message : "No pudimos guardar el alojamiento.",
    };
  }
  revalidatePath("/favoritos");
  return { guardado: guardar };
}
