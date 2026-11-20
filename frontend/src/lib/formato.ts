const PESOS = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  maximumFractionDigits: 0,
});

const PESOS_EXACTO = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  minimumFractionDigits: 2,
});

const DIA_MES = new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "short" });
const DIA_MES_ANIO = new Intl.DateTimeFormat("es-AR", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** Los importes llegan como string para no perder precisión; acá solo se muestran. */
export const pesos = (valor: string | number) => PESOS.format(Number(valor));
export const pesosExactos = (valor: string | number) => PESOS_EXACTO.format(Number(valor));

/** Fechas ISO sin hora: se leen como locales, no como UTC. */
export function fecha(iso: string): Date {
  const [anio, mes, dia] = iso.split("-").map(Number);
  return new Date(anio, mes - 1, dia);
}

export const diaMes = (iso: string) => DIA_MES.format(fecha(iso));
export const diaMesAnio = (iso: string) => DIA_MES_ANIO.format(fecha(iso));

export function rangoFechas(desde: string, hasta: string): string {
  return `${diaMes(desde)} al ${diaMes(hasta)}`;
}

export const plural = (n: number, singular: string, plural_: string) =>
  `${n} ${n === 1 ? singular : plural_}`;

/** Una distancia legible: metros si es poco, kilómetros con un decimal si no.
    Redondea siempre —`3.8831274760553254 km` no es un dato, es ruido— y no se
    come el ancho de la tarjeta con dieciséis decimales. */
export const distanciaCorta = (km: number | null) =>
  km === null
    ? null
    : km < 1
      ? `${Math.round(km * 1000)} m`
      : `${km.toFixed(1).replace(".", ",")} km`;

export const distancia = (km: number | null) =>
  km === null ? null : `a ${distanciaCorta(km)} del centro`;

/** Fecha local en ISO. Con toISOString, después de las 21:00 en Argentina el
    mínimo del campo saltaba a mañana y el viajero no podía elegir hoy. */
export function hoyISO(dias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  const dosDigitos = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dosDigitos(d.getMonth() + 1)}-${dosDigitos(d.getDate())}`;
}

/** Un slug de destino, presentable mientras la API no devolvió el nombre real. */
export const legible = (slug: string) =>
  slug
    .split("-")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
