import "server-only";

import { cookies } from "next/headers";

import { miCuenta, type Cuenta } from "./api";

const COOKIE = "sesion";

/* El token vive en una cookie httpOnly: no la puede leer el JavaScript de la
   página, así que un XSS no se lleva la sesión. */
export async function guardarSesion(token: string, minutos: number) {
  (await cookies()).set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: minutos * 60,
  });
}

export async function borrarSesion() {
  (await cookies()).delete(COOKIE);
}

export async function tokenActual(): Promise<string | null> {
  return (await cookies()).get(COOKIE)?.value ?? null;
}

/** La cuenta de quien está mirando, o null. Nunca lanza: la sesión puede haber vencido. */
export async function cuentaActual(): Promise<Cuenta | null> {
  const token = await tokenActual();
  if (!token) return null;
  try {
    return await miCuenta(token);
  } catch {
    return null;
  }
}
