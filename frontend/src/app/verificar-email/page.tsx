import type { Metadata } from "next";
import Link from "next/link";

import { confirmarEmail } from "@/lib/api";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../cuenta/cuenta.module.css";

export const metadata: Metadata = { title: "Verificar correo", robots: { index: false } };

export default async function VerificarEmail({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  let resultado: "ok" | "error" | "sin-token" = "sin-token";
  let correo: string | null = null;

  if (token) {
    try {
      const cuenta = await confirmarEmail(token);
      resultado = "ok";
      correo = cuenta.email;
    } catch {
      resultado = "error";
    }
  }

  return (
    <>
      <Encabezado />
      <main className={estilos.angosta}>
        {resultado === "ok" && (
          <>
            <h1>Listo, tu correo quedó verificado</h1>
            <p className={estilos.bajada}>
              Confirmamos <strong>{correo}</strong>. Ya podés reservar.
            </p>
            <Link href="/buscar" className={estilos.accion}>
              Buscar alojamiento
            </Link>
          </>
        )}
        {resultado === "error" && (
          <>
            <h1>Ese enlace no sirve</h1>
            <p className={estilos.bajada}>
              Puede haber vencido o estar incompleto. Entrá a tu cuenta y pedí uno nuevo.
            </p>
            <Link href="/cuenta" className={estilos.accion}>
              Ir a mi cuenta
            </Link>
          </>
        )}
        {resultado === "sin-token" && (
          <>
            <h1>Falta el enlace de verificación</h1>
            <p className={estilos.bajada}>
              Entrá desde el enlace que te mandamos, o pedí uno nuevo desde tu cuenta.
            </p>
            <Link href="/cuenta" className={estilos.accion}>
              Ir a mi cuenta
            </Link>
          </>
        )}
      </main>
    </>
  );
}
