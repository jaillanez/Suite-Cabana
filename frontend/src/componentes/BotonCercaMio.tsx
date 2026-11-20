"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Ubicacion } from "./Iconos";
import estilos from "./BotonCercaMio.module.css";

/* La ubicación se pide sólo si el visitante la toca. Pedirla sola al entrar es
   un cartel del navegador antes de que la persona sepa para qué, y la respuesta
   casi siempre es «no». Acá el botón dice qué va a pasar y recién ahí pregunta. */
export default function BotonCercaMio({ activo }: { activo: boolean }) {
  const router = useRouter();
  const params = useSearchParams();
  const [buscando, setBuscando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pedir() {
    if (!navigator.geolocation) {
      setError("Tu navegador no comparte la ubicación.");
      return;
    }
    setBuscando(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const siguiente = new URLSearchParams(params);
        siguiente.set("lat", coords.latitude.toFixed(6));
        siguiente.set("lon", coords.longitude.toFixed(6));
        siguiente.delete("pagina");
        router.push(`/buscar?${siguiente}`);
      },
      () => {
        setBuscando(false);
        setError("No pudimos acceder a tu ubicación. Podés elegir un destino de la lista.");
      },
      { timeout: 10000, maximumAge: 300000 },
    );
  }

  function limpiar() {
    const siguiente = new URLSearchParams(params);
    siguiente.delete("lat");
    siguiente.delete("lon");
    siguiente.delete("pagina");
    router.push(`/buscar${siguiente.size ? `?${siguiente}` : ""}`);
  }

  return (
    <div className={estilos.caja}>
      <button
        type="button"
        className={estilos.boton}
        onClick={activo ? limpiar : pedir}
        disabled={buscando}
      >
        <Ubicacion className={estilos.pin} />
        {buscando ? "Buscando…" : activo ? "Ver todos" : "Cerca mío"}
      </button>
      {error && (
        <p className={estilos.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
