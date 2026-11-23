/* Set propio, 20x20, trazo 1.6, todo en currentColor. Un único peso para que la
   fila de comodidades se lea como una sola familia. */

type Props = { className?: string; titulo?: string };

const base = {
  width: 20,
  height: 20,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

const Svg = ({ children, className, titulo }: Props & { children: React.ReactNode }) => (
  <svg {...base} className={className} aria-hidden={titulo ? undefined : true} role={titulo ? "img" : undefined}>
    {titulo && <title>{titulo}</title>}
    {children}
  </svg>
);

export const Wifi = (p: Props) => (
  <Svg {...p}>
    <path d="M2.5 7.5a12 12 0 0 1 15 0M5 10.6a8 8 0 0 1 10 0M7.6 13.7a4 4 0 0 1 4.8 0" />
    <circle cx="10" cy="16.6" r="0.9" fill="currentColor" stroke="none" />
  </Svg>
);

export const Pileta = (p: Props) => (
  <Svg {...p}>
    <path d="M2 14.5c1.3 0 1.3 1.2 2.7 1.2S6 14.5 7.3 14.5s1.3 1.2 2.7 1.2 1.3-1.2 2.7-1.2 1.3 1.2 2.6 1.2S18.7 14.5 20 14.5" />
    <path d="M6.5 13V5.2A2.2 2.2 0 0 1 8.7 3M13.5 13V5.2A2.2 2.2 0 0 1 15.7 3M6.5 7.2h7M6.5 10.4h7" />
  </Svg>
);

export const Mascotas = (p: Props) => (
  <Svg {...p}>
    <ellipse cx="6.2" cy="6.6" rx="1.7" ry="2.2" />
    <ellipse cx="13.8" cy="6.6" rx="1.7" ry="2.2" />
    <ellipse cx="3.4" cy="11.4" rx="1.5" ry="1.9" />
    <ellipse cx="16.6" cy="11.4" rx="1.5" ry="1.9" />
    <path d="M10 10.6c2.4 0 4.3 2 4.3 4a2.4 2.4 0 0 1-2.6 2.4c-.7 0-1.1-.3-1.7-.3s-1 .3-1.7.3a2.4 2.4 0 0 1-2.6-2.4c0-2 1.9-4 4.3-4Z" />
  </Svg>
);

export const Cochera = (p: Props) => (
  <Svg {...p}>
    <path d="M3 12.5h14M4.4 12.5 5.8 7.6A1.6 1.6 0 0 1 7.3 6.5h5.4a1.6 1.6 0 0 1 1.5 1.1l1.4 4.9" />
    <path d="M3 12.5v3.2h2.4v-1.4M17 12.5v3.2h-2.4v-1.4" />
    <circle cx="6.6" cy="12.5" r="0.9" fill="currentColor" stroke="none" />
    <circle cx="13.4" cy="12.5" r="0.9" fill="currentColor" stroke="none" />
  </Svg>
);

export const Parrilla = (p: Props) => (
  <Svg {...p}>
    <path d="M3.2 8h13.6l-1.4 4.2a4 4 0 0 1-3.8 2.7H8.4a4 4 0 0 1-3.8-2.7L3.2 8Z" />
    <path d="M6.6 14.9 5.4 17.5M13.4 14.9l1.2 2.6M7.4 5.6c0-1 1.2-1 1.2-2M11.4 5.6c0-1 1.2-1 1.2-2" />
  </Svg>
);

export const Aire = (p: Props) => (
  <Svg {...p}>
    <rect x="2.6" y="4.4" width="14.8" height="6.4" rx="1.6" />
    <path d="M5.4 8.2h9.2M5.8 13.4c0 1.5 1.4 1.5 1.4 3M10 13.4c0 1.5 1.4 1.5 1.4 3M14.2 13.4c0 1.5 1.4 1.5 1.4 3" />
  </Svg>
);

export const Calefaccion = (p: Props) => (
  <Svg {...p}>
    <path d="M10 2.6c2.6 2.6 3.6 4.4 3.6 6.2a3.6 3.6 0 0 1-7.2 0c0-1.8 1-3.6 3.6-6.2Z" />
    <path d="M10 17.4c2.6 0 4.4-1.5 4.4-1.5M10 17.4c-2.6 0-4.4-1.5-4.4-1.5" />
  </Svg>
);

export const Desayuno = (p: Props) => (
  <Svg {...p}>
    <path d="M3.4 9.2h9.2v3.2a4 4 0 0 1-4 4h-1.2a4 4 0 0 1-4-4V9.2Z" />
    <path d="M12.6 10.2h1.8a1.9 1.9 0 0 1 0 3.8h-1.8M3 17.4h11" />
    <path d="M6.4 6.4c0-1 1-1 1-2M9.6 6.4c0-1 1-1 1-2" />
  </Svg>
);

export const Lavarropas = (p: Props) => (
  <Svg {...p}>
    <rect x="3.6" y="2.8" width="12.8" height="14.4" rx="1.8" />
    <circle cx="10" cy="11.6" r="3.6" />
    <path d="M6.4 5.6h1.6M12.4 5.6h1.6M7.4 11.2c1.4-.9 2-.2 3.2-.2s1.6-.7 2-1" />
  </Svg>
);

export const Tv = (p: Props) => (
  <Svg {...p}>
    <rect x="2.4" y="4.6" width="15.2" height="9.6" rx="1.6" />
    <path d="M7 17.2h6M10 14.2v3" />
  </Svg>
);

export const RopaBlanca = (p: Props) => (
  <Svg {...p}>
    <path d="M2.4 14.6V6.4M2.4 11.4h15.2v3.2M17.6 14.6v-3.2a2.4 2.4 0 0 0-2.4-2.4H9.6v2.4" />
    <circle cx="6.2" cy="8.4" r="1.8" />
  </Svg>
);

export const Accesible = (p: Props) => (
  <Svg {...p}>
    <circle cx="11.4" cy="4.2" r="1.7" />
    <path d="M8 7.6h5v4.2h-2.6l2.8 5M13 11.8a4.4 4.4 0 1 1-5.6 4.2" />
  </Svg>
);

export const Personas = (p: Props) => (
  <Svg {...p}>
    <circle cx="7.6" cy="6.6" r="2.8" />
    <path d="M2.6 16.6a5 5 0 0 1 10 0M13.4 4.2a2.8 2.8 0 0 1 0 5.4M14.6 11.8a5 5 0 0 1 3 4.8" />
  </Svg>
);

export const Rayo = (p: Props) => (
  <Svg {...p}>
    <path d="M11.2 2.4 4.8 11h4.2l-.6 6.6L15.4 9h-4.4l.2-6.6Z" />
  </Svg>
);

export const Mapa = (p: Props) => (
  <Svg {...p}>
    <path d="M7.4 3.4 2.6 5.2v11.4l4.8-1.8 5.2 1.8 4.8-1.8V3.4l-4.8 1.8L7.4 3.4Z" />
    <path d="M7.4 3.4v11.4M12.6 5.2v11.4" />
  </Svg>
);

export const Lista = (p: Props) => (
  <Svg {...p}>
    <path d="M7 5.4h10M7 10h10M7 14.6h10M3.4 5.4h.01M3.4 10h.01M3.4 14.6h.01" />
  </Svg>
);

export const Lupa = (p: Props) => (
  <Svg {...p}>
    <circle cx="9" cy="9" r="5.4" />
    <path d="m13.2 13.2 3.6 3.6" />
  </Svg>
);

export const Cruz = (p: Props) => (
  <Svg {...p}>
    <path d="m5.4 5.4 9.2 9.2M14.6 5.4l-9.2 9.2" />
  </Svg>
);

export const ChevronIzq = (p: Props) => (
  <Svg {...p}>
    <path d="M12.4 4.6 7 10l5.4 5.4" />
  </Svg>
);

export const ChevronDer = (p: Props) => (
  <Svg {...p}>
    <path d="M7.6 4.6 13 10l-5.4 5.4" />
  </Svg>
);

export const ChevronAbajo = (p: Props) => (
  <Svg {...p}>
    <path d="M4.6 7.6 10 13l5.4-5.4" />
  </Svg>
);

export const Filtro = (p: Props) => (
  <Svg {...p}>
    <path d="M2.8 5.4h14.4M5.4 10h9.2M8 14.6h4" />
  </Svg>
);

export const Alerta = (p: Props) => (
  <Svg {...p}>
    <path d="M10 2.8 18 16.6H2L10 2.8Z" />
    <path d="M10 8v3.4M10 14.2h.01" />
  </Svg>
);

export const Corazon = ({ relleno = false, ...p }: Props & { relleno?: boolean }) => (
  <Svg {...p}>
    <path
      d="M10 16.8S3.2 12.9 3.2 8.2a3.6 3.6 0 0 1 6.8-1.7 3.6 3.6 0 0 1 6.8 1.7c0 4.7-6.8 8.6-6.8 8.6Z"
      fill={relleno ? "currentColor" : "none"}
    />
  </Svg>
);

/** Globo de conversación (genérico, no el logo de una marca). */
export const Mensaje = (p: Props) => (
  <Svg {...p}>
    <path d="M3.5 15.8 4.6 12.6A6.6 6.6 0 1 1 7.3 15.3z" />
  </Svg>
);

export const Ubicacion = (p: Props) => (
  <Svg {...p}>
    <path d="M10 17.4s5.6-4.7 5.6-9a5.6 5.6 0 1 0-11.2 0c0 4.3 5.6 9 5.6 9Z" />
    <circle cx="10" cy="8.2" r="2.1" />
  </Svg>
);

/** Íconos de comodidad por código del catálogo. Sin ícono, no se dibuja nada. */
export const ICONOS_COMODIDAD: Record<string, ((p: Props) => React.ReactElement) | undefined> = {
  wifi: Wifi,
  pileta: Pileta,
  mascotas: Mascotas,
  cochera: Cochera,
  parrilla: Parrilla,
  aire: Aire,
  calefaccion: Calefaccion,
  desayuno: Desayuno,
  lavarropas: Lavarropas,
  tv: Tv,
  ropa_blanca: RopaBlanca,
  accesible: Accesible,
};
