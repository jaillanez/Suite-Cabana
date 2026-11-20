import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { accionRegistrarse } from "@/lib/acciones";
import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import BotonGoogle from "@/componentes/BotonGoogle";
import FormularioAuth from "@/componentes/FormularioAuth";
import estilos from "../cuenta/cuenta.module.css";

export const metadata: Metadata = { title: "Crear cuenta", robots: { index: false } };

export default async function Registrarse() {
  if (await cuentaActual()) redirect("/cuenta");

  return (
    <>
      <Encabezado />
      <main className={estilos.angosta}>
        <h1>Creá tu cuenta</h1>
        <p className={estilos.bajada}>
          Con la misma cuenta podés reservar como viajero y, si querés, publicar tu alojamiento.
        </p>

        <FormularioAuth
          accion={accionRegistrarse}
          enviar="Crear cuenta"
          conTerminos
          campos={[
            { nombre: "nombre", etiqueta: "Nombre", autoComplete: "given-name", ancho: "medio" },
            {
              nombre: "apellido",
              etiqueta: "Apellido",
              autoComplete: "family-name",
              ancho: "medio",
            },
            {
              nombre: "email",
              etiqueta: "Correo",
              tipo: "email",
              autoComplete: "email",
              ancho: "completo",
            },
            {
              nombre: "telefono",
              etiqueta: "Teléfono",
              tipo: "tel",
              autoComplete: "tel",
              requerido: false,
              ayuda: "Opcional. Lo usamos para avisarte de tus reservas.",
              ancho: "completo",
            },
            {
              nombre: "password",
              etiqueta: "Contraseña",
              tipo: "password",
              autoComplete: "new-password",
              ayuda: "Al menos 8 caracteres.",
              ancho: "completo",
            },
          ]}
        />

        <BotonGoogle />

        <p className={estilos.pie}>
          ¿Ya tenés cuenta? <Link href="/ingresar">Ingresá</Link>
        </p>
      </main>
    </>
  );
}
