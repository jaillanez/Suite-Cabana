"use client";

import { useActionState } from "react";

import { accionCambiarTelefono } from "@/lib/acciones";
import estilos from "./CambiarTelefono.module.css";

/* El WhatsApp de la cuenta. Con la reserva confirmada, viajero y anfitrión se
   escriben por ahí desde la reserva; el anfitrión lo necesita para publicar. */
export default function CambiarTelefono({ actual }: { actual: string | null }) {
  const [estado, guardar, pendiente] = useActionState(accionCambiarTelefono, {
    telefono: actual,
  });

  return (
    <form action={guardar} className={estilos.form}>
      <input
        name="telefono"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        defaultValue={estado.telefono ?? ""}
        key={estado.telefono ?? ""}
        placeholder="264 412 3456"
        aria-label="Tu WhatsApp"
        required
      />
      <button type="submit" disabled={pendiente}>
        {pendiente ? "Guardando…" : actual ? "Cambiar" : "Guardar"}
      </button>
      {estado.error && (
        <p className={estilos.error} role="alert">
          {estado.error}
        </p>
      )}
      {estado.aviso && !estado.error && <p className={estilos.aviso}>{estado.aviso}</p>}
    </form>
  );
}
