"use client";

import { useCallback, useRef, useState } from "react";

import { ChevronDer, ChevronIzq } from "./Iconos";
import estilos from "./GaleriaTarjeta.module.css";

type Foto = { url: string; descripcion: string | null };

/* Carril con scroll-snap en vez de flechas con hover: en el teléfono, que es el
   dispositivo principal, el pulgar es el único control que existe. Las flechas
   quedan para el mouse. */
export default function GaleriaTarjeta({ fotos, titulo }: { fotos: Foto[]; titulo: string }) {
  const carril = useRef<HTMLDivElement>(null);
  const [indice, setIndice] = useState(0);
  const cantidad = fotos.length;

  const alScrollear = useCallback(() => {
    const el = carril.current;
    if (!el) return;
    setIndice(Math.round(el.scrollLeft / el.clientWidth));
  }, []);

  if (cantidad === 0) {
    return (
      <div className={`${estilos.marco} ${estilos.vacio}`}>
        <span>Sin fotos cargadas</span>
      </div>
    );
  }

  const mover = (paso: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const el = carril.current;
    if (!el) return;
    const destino = Math.min(Math.max(indice + paso, 0), cantidad - 1);
    el.scrollTo({ left: destino * el.clientWidth, behavior: "smooth" });
  };

  return (
    <div className={estilos.marco}>
      <div
        ref={carril}
        className={estilos.carril}
        onScroll={alScrollear}
        tabIndex={0}
        role="group"
        aria-label={`Fotos de ${titulo}`}
      >
        {fotos.map((f, i) => (
          <img
            key={f.url}
            src={f.url}
            alt={i === 0 ? `${titulo}, foto principal` : `${titulo}, foto ${i + 1}`}
            loading={i === 0 ? "eager" : "lazy"}
            decoding="async"
          />
        ))}
      </div>

      {cantidad > 1 && (
        <>
          <button
            type="button"
            className={`${estilos.flecha} ${estilos.izq}`}
            onClick={mover(-1)}
            disabled={indice === 0}
            aria-label="Foto anterior"
          >
            <ChevronIzq />
          </button>
          <button
            type="button"
            className={`${estilos.flecha} ${estilos.der}`}
            onClick={mover(1)}
            disabled={indice === cantidad - 1}
            aria-label="Foto siguiente"
          >
            <ChevronDer />
          </button>
          <div className={estilos.puntos} aria-hidden="true">
            {fotos.slice(0, 6).map((f, i) => (
              <span key={f.url} className={i === indice ? estilos.activo : undefined} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
