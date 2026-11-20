"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import { accionIngresarConGoogle } from "@/lib/acciones";
import estilos from "./BotonGoogle.module.css";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: Record<string, unknown>) => void;
          renderButton: (el: HTMLElement, opciones: Record<string, unknown>) => void;
        };
      };
    };
  }
}

/* Solo aparece si hay NEXT_PUBLIC_GOOGLE_CLIENT_ID. Sin credencial configurada no
   se muestra un botón que no puede funcionar. */
export default function BotonGoogle() {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const contenedor = useRef<HTMLDivElement>(null);
  const [listo, setListo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!listo || !clientId || !contenedor.current || !window.google) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: async (respuesta: { credential?: string }) => {
        if (!respuesta.credential) {
          setError("Google no devolvió una credencial");
          return;
        }
        const resultado = await accionIngresarConGoogle(respuesta.credential);
        if (resultado?.error) setError(resultado.error);
      },
    });
    window.google.accounts.id.renderButton(contenedor.current, {
      theme: "outline",
      size: "large",
      width: 320,
      text: "continue_with",
      locale: "es-419",
    });
  }, [listo, clientId]);

  if (!clientId) return null;

  return (
    <div className={estilos.caja}>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setListo(true)}
      />
      <div className={estilos.separador}>
        <span>o</span>
      </div>
      <div ref={contenedor} className={estilos.boton} />
      {error && (
        <p className={estilos.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
