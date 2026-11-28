"use server";

import { redirect } from "next/navigation";

import { revalidatePath } from "next/cache";

import {
  ApiError,
  altaPrestador,
  cambiarTelefono,
  conectarMercadoPago,
  desvincularMercadoPago,
  vincularMercadoPago,
  ingresar,
  ingresarConGoogle,
  pedirVerificacion,
  registrarse,
} from "./api";
import { borrarSesion, guardarSesion, tokenActual } from "./sesion";

export type Estado = { error?: string; aviso?: string; enlace?: string | null };

const texto = (f: FormData, clave: string) => String(f.get(clave) ?? "").trim();

function mensaje(e: unknown, porDefecto: string): string {
  if (e instanceof ApiError) {
    // Los 422 de Pydantic llegan como lista de problemas por campo.
    if (Array.isArray(e.detalle)) {
      const primero = e.detalle[0] as { msg?: string } | undefined;
      return primero?.msg ?? porDefecto;
    }
    return e.message || porDefecto;
  }
  return porDefecto;
}

export async function accionIngresar(_previo: Estado, datos: FormData): Promise<Estado> {
  const email = texto(datos, "email");
  const password = String(datos.get("password") ?? "");
  if (!email || !password) return { error: "Completá el correo y la contraseña" };

  try {
    const sesion = await ingresar({ email, password });
    await guardarSesion(sesion.token, sesion.expira_en_minutos);
  } catch (e) {
    return { error: mensaje(e, "No pudimos ingresar. Probá de nuevo.") };
  }
  redirect(texto(datos, "volver") || "/cuenta");
}

export async function accionRegistrarse(_previo: Estado, datos: FormData): Promise<Estado> {
  const email = texto(datos, "email");
  const password = String(datos.get("password") ?? "");
  const nombre = texto(datos, "nombre");
  const apellido = texto(datos, "apellido");

  if (!email || !nombre || !apellido) return { error: "Faltan datos" };
  if (password.length < 8) return { error: "La contraseña necesita al menos 8 caracteres" };
  if (datos.get("acepta_terminos") !== "on") {
    return { error: "Hay que aceptar los términos y la política de privacidad" };
  }

  try {
    const sesion = await registrarse({
      email,
      password,
      nombre,
      apellido,
      telefono: texto(datos, "telefono") || undefined,
      acepta_terminos: true,
    });
    await guardarSesion(sesion.token, sesion.expira_en_minutos);
  } catch (e) {
    return { error: mensaje(e, "No pudimos crear la cuenta. Probá de nuevo.") };
  }
  redirect("/cuenta");
}

export async function accionSalir() {
  await borrarSesion();
  redirect("/");
}

export async function accionAltaPrestador(_previo: Estado, datos: FormData): Promise<Estado> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };

  const razon_social = texto(datos, "razon_social");
  const cuit = texto(datos, "cuit");
  const condicion_iva = texto(datos, "condicion_iva");
  if (!razon_social || !cuit || !condicion_iva) return { error: "Faltan datos" };

  try {
    await altaPrestador(token, { razon_social, cuit, condicion_iva });
  } catch (e) {
    return { error: mensaje(e, "No pudimos guardar tus datos de prestador.") };
  }
  redirect("/cuenta");
}

export async function accionVincularMercadoPago(
  _previo: Estado,
  datos: FormData,
): Promise<Estado> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  const credencial = texto(datos, "access_token");
  if (!credencial) return { error: "Pegá tu Access Token de Mercado Pago." };
  try {
    await vincularMercadoPago(token, credencial);
  } catch (e) {
    return { error: mensaje(e, "No pudimos vincular tu cuenta de Mercado Pago.") };
  }
  redirect("/cuenta");
}

/** "Conectar con Mercado Pago": pide la dirección de autorización y manda ahí. */
export async function accionConectarMercadoPago(): Promise<void> {
  const token = await tokenActual();
  if (!token) redirect("/ingresar?volver=/cuenta");
  let url: string;
  try {
    url = (await conectarMercadoPago(token)).url;
  } catch {
    redirect("/cuenta/mercadopago?error=no_disponible");
  }
  redirect(url);
}

export async function accionDesvincularMercadoPago(): Promise<void> {
  const token = await tokenActual();
  if (!token) redirect("/ingresar?volver=/cuenta");
  await desvincularMercadoPago(token);
  redirect("/cuenta");
}

export async function accionPedirVerificacion(): Promise<Estado> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const r = await pedirVerificacion(token);
    return { aviso: r.detalle, enlace: r.enlace };
  } catch (e) {
    return { error: mensaje(e, "No pudimos generar el enlace.") };
  }
}

/** El WhatsApp de la cuenta: lo normaliza el backend y vuelve como quedó guardado. */
export async function accionCambiarTelefono(
  _previo: Estado & { telefono?: string | null },
  datos: FormData,
): Promise<Estado & { telefono?: string | null }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const cuenta = await cambiarTelefono(token, texto(datos, "telefono"));
    revalidatePath("/cuenta");
    return { aviso: "Guardado.", telefono: cuenta.telefono };
  } catch (e) {
    return { error: mensaje(e, "No pudimos guardar el número.") };
  }
}

/** Recibe el id_token que devuelve Google en el navegador y lo canjea por sesión.
    La verificación de la firma la hace el backend: acá no se confía en nada. */
export async function accionIngresarConGoogle(credencial: string): Promise<Estado> {
  try {
    const sesion = await ingresarConGoogle(credencial);
    await guardarSesion(sesion.token, sesion.expira_en_minutos);
  } catch (e) {
    return { error: mensaje(e, "No pudimos ingresar con Google.") };
  }
  redirect("/cuenta");
}
