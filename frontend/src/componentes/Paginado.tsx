"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { ChevronDer, ChevronIzq } from "./Iconos";
import estilos from "./Paginado.module.css";

/* Enlaces reales, no scroll infinito: las páginas por destino tienen que ser
   rastreables por buscadores (docs/01 §5 R4). */
export default function Paginado({ pagina, paginas }: { pagina: number; paginas: number }) {
  const pathname = usePathname();
  const params = useSearchParams();

  if (paginas <= 1) return null;

  const enlace = (n: number) => {
    const siguiente = new URLSearchParams(params);
    if (n === 1) siguiente.delete("pagina");
    else siguiente.set("pagina", String(n));
    return `${pathname}?${siguiente}`;
  };

  const numeros = Array.from({ length: paginas }, (_, i) => i + 1).filter(
    (n) => n === 1 || n === paginas || Math.abs(n - pagina) <= 1,
  );

  return (
    <nav className={estilos.paginado} aria-label="Páginas de resultados">
      {pagina > 1 ? (
        <Link href={enlace(pagina - 1)} className={estilos.flecha} rel="prev">
          <ChevronIzq />
          <span>Anterior</span>
        </Link>
      ) : (
        <span className={`${estilos.flecha} ${estilos.inactivo}`} aria-hidden="true">
          <ChevronIzq />
          <span>Anterior</span>
        </span>
      )}

      <ul className={estilos.numeros}>
        {numeros.map((n, i) => (
          <li key={n}>
            {i > 0 && n - numeros[i - 1] > 1 && <span className={estilos.puntos}>…</span>}
            {n === pagina ? (
              <span className={`${estilos.numero} ${estilos.actual} cifra`} aria-current="page">
                {n}
              </span>
            ) : (
              <Link href={enlace(n)} className={`${estilos.numero} cifra`}>
                {n}
              </Link>
            )}
          </li>
        ))}
      </ul>

      {pagina < paginas ? (
        <Link href={enlace(pagina + 1)} className={estilos.flecha} rel="next">
          <span>Siguiente</span>
          <ChevronDer />
        </Link>
      ) : (
        <span className={`${estilos.flecha} ${estilos.inactivo}`} aria-hidden="true">
          <span>Siguiente</span>
          <ChevronDer />
        </span>
      )}
    </nav>
  );
}
