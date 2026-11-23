"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { destinos, type Destino } from "@/lib/api";
import { diaMes, hoyISO } from "@/lib/formato";
import { Lupa, Personas, Ubicacion } from "./Iconos";
import estilos from "./BarraBusqueda.module.css";

const resumenFechas = (desde: string, hasta: string) => `${diaMes(desde)}–${diaMes(hasta)}`;

export type ValoresBusqueda = {
  localidad?: string;
  localidadNombre?: string;
  provincia?: string;
  desde?: string;
  hasta?: string;
  personas?: number;
};

type Props = {
  valores?: ValoresBusqueda;
  /** En la home ocupa todo el ancho; en resultados vive dentro de la barra fija. */
  variante?: "hero" | "compacta";
  /** Parámetros a conservar al buscar de nuevo (filtros, orden). */
  conservar?: Record<string, string | string[]>;
};

export default function BarraBusqueda({
  valores = {},
  variante = "hero",
  conservar = {},
}: Props) {
  const router = useRouter();
  const idLista = useId();

  const [texto, setTexto] = useState(valores.localidadNombre ?? "");
  const [elegido, setElegido] = useState<Destino | null>(
    valores.localidad && valores.localidadNombre
      ? {
          slug: valores.localidad,
          nombre: valores.localidadNombre,
          provincia: valores.provincia ?? "",
          provincia_slug: "",
          publicaciones: 0,
        }
      : null,
  );
  const [sugerencias, setSugerencias] = useState<Destino[]>([]);
  const [abierto, setAbierto] = useState(false);
  const [resaltado, setResaltado] = useState(-1);
  const [desde, setDesde] = useState(valores.desde ?? "");
  const [hasta, setHasta] = useState(valores.hasta ?? "");
  const [personas, setPersonas] = useState(valores.personas ?? 2);
  const [error, setError] = useState<string | null>(null);
  const [expandido, setExpandido] = useState(false);
  const contenedor = useRef<HTMLFormElement>(null);

  useEffect(() => {
    let vigente = true;
    const t = setTimeout(async () => {
      try {
        const lista = await destinos(texto.trim() || undefined);
        if (vigente) setSugerencias(lista);
      } catch {
        if (vigente) setSugerencias([]);
      }
    }, 180);
    return () => {
      vigente = false;
      clearTimeout(t);
    };
  }, [texto]);

  useEffect(() => {
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  function elegir(destino: Destino) {
    setElegido(destino);
    setTexto(destino.nombre);
    setAbierto(false);
    setResaltado(-1);
    setError(null);
  }

  function teclas(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!abierto || sugerencias.length === 0) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const paso = e.key === "ArrowDown" ? 1 : -1;
      setResaltado((i) => (i + paso + sugerencias.length) % sugerencias.length);
    } else if (e.key === "Enter" && resaltado >= 0) {
      e.preventDefault();
      elegir(sugerencias[resaltado]);
    } else if (e.key === "Escape") {
      setAbierto(false);
    }
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    const destino = elegido ?? sugerencias.find((d) => d.nombre.toLowerCase() === texto.toLowerCase());
    if (!destino) {
      setError("Elegí un destino de la lista");
      setAbierto(true);
      return;
    }
    if (!desde || !hasta) {
      setError("Necesitamos las fechas para saber qué hay libre");
      return;
    }
    if (hasta <= desde) {
      setError("La salida tiene que ser posterior a la llegada");
      return;
    }

    const params = new URLSearchParams();
    for (const [clave, valor] of Object.entries(conservar)) {
      if (clave === "pagina") continue;
      for (const v of Array.isArray(valor) ? valor : [valor]) params.append(clave, v);
    }
    params.set("localidad", destino.slug);
    params.set("desde", desde);
    params.set("hasta", hasta);
    params.set("personas", String(personas));
    setExpandido(false);
    router.push(`/buscar?${params}`);
  }

  const minimo = hoyISO();

  return (
    <form
      ref={contenedor}
      className={`${estilos.barra} ${estilos[variante]} ${expandido ? estilos.expandido : ""}`}
      onSubmit={enviar}
      role="search"
    >
      {/* En el teléfono la barra fija se pliega a una línea: el buscador no puede
          comerse media pantalla cuando lo que importa son los resultados. */}
      <button
        type="button"
        className={estilos.resumen}
        onClick={() => setExpandido((v) => !v)}
        aria-expanded={expandido}
      >
        <Lupa className={estilos.icono} />
        <span>
          <strong>{texto || "¿A dónde vas?"}</strong>
          <span className={estilos.resumenDetalle}>
            {desde && hasta ? `${resumenFechas(desde, hasta)} · ` : ""}
            {personas === 1 ? "1 persona" : `${personas} personas`}
          </span>
        </span>
      </button>

      <div className={estilos.campos}>
      <div className={`${estilos.campo} ${estilos.destino}`}>
        <label htmlFor={`${idLista}-destino`}>Destino</label>
        <div className={estilos.conIcono}>
          <Ubicacion className={estilos.icono} />
          <input
            id={`${idLista}-destino`}
            value={texto}
            onChange={(e) => {
              setTexto(e.target.value);
              setElegido(null);
              setAbierto(true);
            }}
            onFocus={() => setAbierto(true)}
            onKeyDown={teclas}
            placeholder="¿A dónde vas?"
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="words"
            role="combobox"
            aria-expanded={abierto}
            aria-controls={idLista}
            aria-autocomplete="list"
            aria-activedescendant={resaltado >= 0 ? `${idLista}-${resaltado}` : undefined}
          />
        </div>
        {abierto && sugerencias.length > 0 && (
          <ul className={estilos.sugerencias} id={idLista} role="listbox">
            {sugerencias.map((d, i) => (
              <li key={d.slug} id={`${idLista}-${i}`} role="option" aria-selected={i === resaltado}>
                <button
                  type="button"
                  className={i === resaltado ? estilos.resaltado : undefined}
                  onMouseEnter={() => setResaltado(i)}
                  onClick={() => elegir(d)}
                >
                  <Ubicacion className={estilos.iconoSugerencia} />
                  <span>
                    <strong>{d.nombre}</strong>
                    <span className={estilos.provincia}>{d.provincia}</span>
                  </span>
                  <span className={`${estilos.cuenta} cifra`}>{d.publicaciones}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={estilos.campo}>
        <label htmlFor={`${idLista}-desde`}>Llegada</label>
        <input
          id={`${idLista}-desde`}
          type="date"
          value={desde}
          min={minimo}
          max={hoyISO(365)}
          onChange={(e) => {
            setDesde(e.target.value);
            if (hasta && hasta <= e.target.value) setHasta("");
            setError(null);
          }}
        />
      </div>

      <div className={estilos.campo}>
        <label htmlFor={`${idLista}-hasta`}>Salida</label>
        <input
          id={`${idLista}-hasta`}
          type="date"
          value={hasta}
          min={desde || minimo}
          onChange={(e) => {
            setHasta(e.target.value);
            setError(null);
          }}
        />
      </div>

      <div className={`${estilos.campo} ${estilos.personas}`}>
        <label htmlFor={`${idLista}-personas`}>Personas</label>
        <div className={estilos.conIcono}>
          <Personas className={estilos.icono} />
          <select
            id={`${idLista}-personas`}
            value={personas}
            onChange={(e) => setPersonas(Number(e.target.value))}
          >
            {/* El rótulo de arriba ya dice PERSONAS: repetirlo trunca la opción. */}
            {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      <button className={estilos.buscar} type="submit">
        <Lupa />
        <span>Buscar</span>
      </button>
      </div>

      {error && (
        <p className={estilos.error} role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
