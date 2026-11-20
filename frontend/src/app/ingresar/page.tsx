import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { accionIngresar } from "@/lib/acciones";
import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import BotonGoogle from "@/componentes/BotonGoogle";
import FormularioAuth from "@/componentes/FormularioAuth";
import estilos from "../cuenta/cuenta.module.css";

export const metadata: Metadata = { title: "Ingresar", robots: { index: false } };

export default async function Ingresar({
  searchParams,
}: {
  searchParams: Promise<{ volver?: string }>;
}) {
  if (await cuentaActual()) redirect("/cuenta");
  const { volver } = await searchParams;

  return (
    <>
      <Encabezado />
      <main className={estilos.angosta}>
        <h1>Ingresá a tu cuenta</h1>
        <p className={estilos.bajada}>
          Para reservar, guardar favoritos y ver tus reservas.
        </p>

        <FormularioAuth
          accion={accionIngresar}
          enviar="Ingresar"
          ocultos={volver ? { volver } : {}}
          campos={[
            {
              nombre: "email",
              etiqueta: "Correo",
              tipo: "email",
              autoComplete: "email",
              ancho: "completo",
            },
            {
              nombre: "password",
              etiqueta: "Contraseña",
              tipo: "password",
              autoComplete: "current-password",
              ancho: "completo",
            },
          ]}
        />

        <BotonGoogle />

        <p className={estilos.pie}>
          ¿Todavía no tenés cuenta? <Link href="/registrarse">Creá una</Link>
        </p>
      </main>
    </>
  );
}
