"use client";

import { useActionState } from "react";

import Link from "next/link";

import type { Estado } from "@/lib/acciones";
import { Alerta } from "./Iconos";
import estilos from "./FormularioAuth.module.css";

type Campo = {
  nombre: string;
  etiqueta: string;
  tipo?: string;
  autoComplete?: string;
  requerido?: boolean;
  ayuda?: string;
  ancho?: "medio" | "completo";
};

export default function FormularioAuth({
  accion,
  campos,
  enviar,
  ocultos = {},
  conTerminos = false,
}: {
  accion: (previo: Estado, datos: FormData) => Promise<Estado>;
  campos: Campo[];
  enviar: string;
  ocultos?: Record<string, string>;
  /** docs/01 §5 R11: los términos se aceptan al registrarse. */
  conTerminos?: boolean;
}) {
  const [estado, ejecutar, pendiente] = useActionState(accion, {});

  return (
    <form action={ejecutar} className={estilos.formulario}>
      {Object.entries(ocultos).map(([clave, valor]) => (
        <input key={clave} type="hidden" name={clave} value={valor} />
      ))}

      {estado.error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {estado.error}
        </p>
      )}

      <div className={estilos.campos}>
        {campos.map((c) => (
          <label
            key={c.nombre}
            className={c.ancho === "medio" ? estilos.medio : estilos.completo}
          >
            <span>{c.etiqueta}</span>
            <input
              name={c.nombre}
              type={c.tipo ?? "text"}
              autoComplete={c.autoComplete}
              required={c.requerido ?? true}
              aria-describedby={c.ayuda ? `${c.nombre}-ayuda` : undefined}
            />
            {c.ayuda && (
              <small id={`${c.nombre}-ayuda`} className={estilos.ayuda}>
                {c.ayuda}
              </small>
            )}
          </label>
        ))}
      </div>

      {conTerminos && (
        <label className={estilos.terminos}>
          <input type="checkbox" name="acepta_terminos" required />
          <span>
            Acepto los <Link href="/terminos">términos y condiciones</Link> y la{" "}
            <Link href="/privacidad">política de privacidad</Link>.
          </span>
        </label>
      )}

      <button type="submit" className={estilos.enviar} disabled={pendiente}>
        {pendiente ? "Un momento…" : enviar}
      </button>
    </form>
  );
}
