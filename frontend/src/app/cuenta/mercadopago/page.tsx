import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { accionConectarMercadoPago } from "@/lib/acciones";
import { ApiError, volverDeMercadoPago } from "@/lib/api";
import { tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../../no-encontrado.module.css";

export const metadata: Metadata = { title: "Mercado Pago", robots: { index: false } };

/* Adonde vuelve el anfitrión después de autorizar en Mercado Pago (OAuth). Con
   el `code` y el `state` se cierra la conexión en el backend, que valida que el
   pedido sea de esta misma cuenta. Si sale bien, vuelve a Mi cuenta. */

const ERRORES: Record<string, string> = {
  access_denied: "No autorizaste la conexión en Mercado Pago, así que no cambió nada.",
  no_disponible:
    "La conexión con Mercado Pago todavía no está habilitada. Avisanos y lo resolvemos.",
};

export default async function VueltaDeMercadoPago({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  let problema = sp.error ? (ERRORES[sp.error] ?? "Mercado Pago no completó la conexión.") : null;

  if (!problema && sp.code && sp.state) {
    const token = await tokenActual();
    if (!token) {
      const volver = `/cuenta/mercadopago?${new URLSearchParams({ code: sp.code, state: sp.state })}`;
      redirect(`/ingresar?volver=${encodeURIComponent(volver)}`);
    }
    try {
      await volverDeMercadoPago(token, sp.code, sp.state);
    } catch (e) {
      problema =
        e instanceof ApiError && e.message ? e.message : "No pudimos terminar la conexión.";
    }
    if (!problema) redirect("/cuenta?mp=conectado#cobros");
  } else if (!problema) {
    problema = "Esta página es la vuelta desde Mercado Pago. Empezá desde Mi cuenta.";
  }

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <p className={estilos.codigo}>Mercado Pago</p>
        <h1>No quedó conectada</h1>
        <p className={estilos.cuerpo}>{problema}</p>
        <form action={accionConectarMercadoPago}>
          <button type="submit" className={estilos.accion}>
            Probar de nuevo
          </button>
        </form>
        <Link href="/cuenta#cobros">Volver a mi cuenta</Link>
      </main>
    </>
  );
}
