"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  ApiError,
  aprobarReserva,
  cancelarReserva,
  crearReserva,
  pedirPago,
  rechazarReserva,
  reservarEvento,
  reservarExcursion,
  simularPago,
  type PedidoEvento,
  type PedidoExcursion,
  type Reserva,
} from "./api";
import { tokenActual } from "./sesion";

export type ResultadoReserva = { reserva: Reserva } | { error: string };
export type ResultadoPago = { url: string; pasarela: string } | { error: string };

/** 428: falta el WhatsApp del viajero. El formulario muestra el campo y reenvía. */
type FaltaTelefono = { error: string; pedirTelefono?: boolean };

function problemaAlReservar(e: unknown, porDefecto: string): FaltaTelefono {
  if (e instanceof ApiError && e.status === 428) {
    return { error: e.message, pedirTelefono: true };
  }
  return problema(e, porDefecto);
}

function problema(e: unknown, porDefecto: string): { error: string } {
  if (e instanceof ApiError) {
    const d = e.detalle;
    if (Array.isArray(d)) {
      const primero = d[0] as { msg?: string } | undefined;
      return { error: primero?.msg ?? porDefecto };
    }
    return { error: e.message || porDefecto };
  }
  return { error: porDefecto };
}

async function conSesion(
  llamada: (token: string) => Promise<Reserva>,
  porDefecto: string,
): Promise<ResultadoReserva> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const reserva = await llamada(token);
    revalidatePath("/reservas");
    revalidatePath("/mis-reservas");
    return { reserva };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

/** Crea la reserva y manda al detalle, donde se paga. */
export async function accionReservar(_previo: unknown, datos: FormData) {
  const token = await tokenActual();
  if (!token) redirect("/ingresar?volver=/buscar");

  const v = (k: string) => String(datos.get(k) ?? "").trim();
  if (datos.get("acepta_terminos") !== "on") {
    return { error: "Hay que aceptar los términos y la política de cancelación" };
  }

  let reserva: Reserva;
  try {
    reserva = await crearReserva(token, {
      unidad_id: v("unidad_id"),
      desde: v("desde"),
      hasta: v("hasta"),
      adultos: Number(v("adultos") || 2),
      menores: Number(v("menores") || 0),
      mascotas: Number(v("mascotas") || 0),
      acepta_terminos: true,
      telefono: v("telefono") || undefined,
    });
  } catch (e) {
    return problemaAlReservar(e, "No pudimos crear la reserva.");
  }
  revalidatePath("/reservas");
  redirect(`/reservas/${reserva.codigo}`);
}

/** Reserva de un salón (docs/04). Sin sesión, avisa: el panel manda a ingresar y
    vuelve a la ficha, en vez de perder lo que el viajero ya eligió. */
export async function accionReservarEvento(
  pedido: PedidoEvento,
  acepta: boolean,
  telefono?: string,
): Promise<{ error: string; ingresar?: boolean; pedirTelefono?: boolean } | never> {
  // Lo que tildó el viajero, no un `true` fijo: la reserva guarda que aceptó.
  if (acepta !== true) {
    return { error: "Hay que aceptar los términos y la política de cancelación" };
  }
  const token = await tokenActual();
  if (!token) return { error: "Ingresá para reservar.", ingresar: true };

  let reserva: Reserva;
  try {
    reserva = await reservarEvento(token, {
      ...pedido,
      acepta_terminos: acepta,
      telefono: telefono || undefined,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      return { error: "Tu sesión venció. Ingresá de nuevo.", ingresar: true };
    }
    return problemaAlReservar(e, "No pudimos crear la reserva.");
  }
  revalidatePath("/reservas");
  redirect(`/reservas/${reserva.codigo}`);
}

/** Reserva de lugares en una salida de excursión (docs/05). Igual que un salón:
    sin sesión, el panel manda a ingresar y vuelve a la ficha. */
export async function accionReservarExcursion(
  pedido: PedidoExcursion,
  acepta: boolean,
  telefono?: string,
): Promise<{ error: string; ingresar?: boolean; pedirTelefono?: boolean } | never> {
  if (acepta !== true) {
    return { error: "Hay que aceptar los términos y la política de cancelación" };
  }
  const token = await tokenActual();
  if (!token) return { error: "Ingresá para reservar.", ingresar: true };

  let reserva: Reserva;
  try {
    reserva = await reservarExcursion(token, {
      ...pedido,
      acepta_terminos: acepta,
      telefono: telefono || undefined,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      return { error: "Tu sesión venció. Ingresá de nuevo.", ingresar: true };
    }
    return problemaAlReservar(e, "No pudimos crear la reserva.");
  }
  revalidatePath("/reservas");
  redirect(`/reservas/${reserva.codigo}`);
}

export async function accionPagar(
  codigo: string,
  pasarela?: string,
): Promise<ResultadoPago> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const preferencia = await pedirPago(token, codigo, pasarela);
    return { url: preferencia.url_pago, pasarela: preferencia.pasarela };
  } catch (e) {
    return problema(e, "No pudimos armar el pago.");
  }
}

export async function accionCancelar(codigo: string, motivo: string) {
  return conSesion((t) => cancelarReserva(t, codigo, motivo), "No pudimos cancelar la reserva.");
}

export async function accionAprobarReserva(codigo: string) {
  return conSesion((t) => aprobarReserva(t, codigo), "No pudimos aprobar la reserva.");
}

export async function accionRechazarReserva(codigo: string, motivo: string) {
  return conSesion((t) => rechazarReserva(t, codigo, motivo), "No pudimos rechazar la reserva.");
}

/** Solo desarrollo: aprueba o rechaza un pago simulado. */
export async function accionSimularPago(pago: string, reserva: string, estado: string) {
  try {
    const r = await simularPago({ pago, reserva, estado });
    revalidatePath(`/reservas/${reserva}`);
    return { resultado: r.resultado ?? r.estado };
  } catch (e) {
    return problema(e, "No pudimos simular el pago.");
  }
}
