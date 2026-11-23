const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/* En el navegador se pide a la misma dirección del sitio y Next lo reenvía al
   backend (ver `next.config.ts`). Así no hay CORS que mantener: llamar directo
   al origen de la API obliga a listar cada dominio y cada puerto del frontend,
   y el día que cambia alguno lo único que se rompe son las llamadas del
   navegador —el autocompletado, subir fotos— y se rompen en silencio, porque el
   resto de la página la arma el servidor y sigue andando.
   En el servidor se llama directo: ahí no hay CORS y sobra el rodeo. */
const BASE = typeof window === "undefined" ? API_URL : new URL(API_URL).pathname.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detalle?: unknown,
  ) {
    super(message);
  }
}

/** Cliente único de la API. Toda regla de negocio vive en el backend. */
export async function api<T>(ruta: string, init?: RequestInit & { token?: string }): Promise<T> {
  const { token, ...resto } = init ?? {};
  const res = await fetch(`${BASE}${ruta}`, {
    cache: "no-store",
    ...resto,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...resto.headers,
    },
  });
  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    const detalle = (cuerpo as { detail?: unknown }).detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : ((detalle as { mensaje?: string })?.mensaje ?? res.statusText);
    throw new ApiError(res.status, mensaje, detalle);
  }
  // 204 no trae cuerpo: intentar leerlo como JSON revienta.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

/* Los importes viajan como string: en JSON todo número es float y el peso no se
   redondea alegremente. Se convierten a número solo para mostrarlos. */

export type Noche = { fecha: string; precio: string };

export type Precio = {
  noches: number;
  promedio_noche: string;
  alojamiento: string;
  descuento: string;
  porcentaje_descuento: string;
  limpieza: string;
  personas_extra: string;
  mascotas: string;
  subtotal: string;
  cargo_servicio: string;
  total: string;
  detalle_noches: Noche[];
};

export type UnidadResultado = {
  id: string;
  nombre: string;
  capacidad: number;
  precio: Precio;
};

export type Resultado = {
  publicacion_id: string;
  slug: string;
  titulo: string;
  subtipo: string | null;
  subtipo_codigo: string | null;
  prestador: string;
  localidad: string;
  provincia: string;
  confirmacion_inmediata: boolean;
  lat: number | null;
  lon: number | null;
  distancia_km: number | null;
  fotos: { url: string; descripcion: string | null }[];
  comodidades: string[];
  unidades_disponibles: number;
  unidad: UnidadResultado;
};

export type Busqueda = {
  total: number;
  pagina: number;
  por_pagina: number;
  paginas: number;
  noches: number;
  moneda: string;
  destino: {
    localidad: string | null;
    provincia: string | null;
    lat: number | null;
    lon: number | null;
  };
  resultados: Resultado[];
};

export type Destino = {
  nombre: string;
  slug: string;
  provincia: string;
  provincia_slug: string;
  publicaciones: number;
};

export type Filtros = {
  subtipos: { codigo: string; nombre: string }[];
  comodidades: { codigo: string; nombre: string; icono: string | null }[];
  ordenes: { codigo: string; nombre: string }[];
};

export const buscar = (parametros: URLSearchParams) =>
  api<Busqueda>(`/publicaciones/buscar?${parametros}`);

export const destinos = (q?: string) =>
  api<Destino[]>(`/destinos${q ? `?q=${encodeURIComponent(q)}` : ""}`);

export const filtrosDisponibles = () => api<Filtros>("/publicaciones/filtros");

/* --- Ficha de publicación y páginas por destino --- */

export type Comodidad = { codigo: string; nombre: string };

export type UnidadFicha = {
  id: string;
  nombre: string;
  capacidad: number;
  capacidad_base: number | null;
  tarifa_base: string | null;
  estadia_minima: number;
  cargo_limpieza: string;
  cargo_persona_extra: string;
  cargo_mascota: string;
  descuento_semanal: string;
  descuento_mensual: string;
  /** null cuando no se pidieron fechas: sin fechas no se sabe qué está libre. */
  disponible: boolean | null;
  motivo: string | null;
  precio: Precio | null;
};

export type Ficha = {
  publicacion_id: string;
  slug: string;
  titulo: string;
  descripcion: string;
  reglas_casa: string | null;
  subtipo: string | null;
  subtipo_codigo: string | null;
  localidad: string;
  localidad_slug: string;
  zona: string | null;
  provincia: string;
  /** Aproximadas (~1 km). La dirección y el punto exacto llegan con la reserva. */
  lat: number | null;
  lon: number | null;
  hora_ingreso: string | null;
  hora_salida: string | null;
  confirmacion_inmediata: boolean;
  es_demo: boolean;
  prestador: { razon_social: string; verificado: boolean; publica_desde: number };
  politica_cancelacion: {
    codigo: string;
    nombre: string;
    descripcion: string | null;
    tramos: { dias_antes: number; porcentaje_reintegro: number }[];
  } | null;
  fotos: { url: string; descripcion: string | null }[];
  comodidades: Comodidad[];
  unidades: UnidadFicha[];
  noches: number | null;
  /** Salones del mismo anfitrión (docs/04): "también tiene salón". */
  salones_del_anfitrion?: { titulo: string; slug: string }[];
  moneda: string;
};

export type ResumenDestino = {
  publicacion_id: string;
  slug: string;
  titulo: string;
  subtipo: string | null;
  localidad: string;
  provincia: string;
  zona: string | null;
  lat: number | null;
  lon: number | null;
  capacidad_maxima: number;
  tarifa_desde: string | null;
  confirmacion_inmediata: boolean;
  fotos: { url: string; descripcion: string | null }[];
  comodidades: string[];
};

export type PaginaDestino = {
  localidad: string;
  localidad_slug: string;
  provincia: string;
  provincia_slug: string;
  zonas: string[];
  total: number;
  pagina: number;
  por_pagina: number;
  paginas: number;
  publicaciones: ResumenDestino[];
};

export const ficha = (slug: string, parametros?: URLSearchParams) =>
  api<Ficha>(`/publicaciones/${encodeURIComponent(slug)}${parametros?.size ? `?${parametros}` : ""}`);

export const destino = (slug: string, parametros?: URLSearchParams) =>
  api<PaginaDestino>(
    `/destinos/${encodeURIComponent(slug)}/publicaciones${parametros?.size ? `?${parametros}` : ""}`,
  );

/* --- Cuentas y roles --- */

export type Sesion = { token: string; tipo_token: string; expira_en_minutos: number };

export type PrestadorCuenta = {
  id: string;
  razon_social: string;
  cuit: string | null;
  condicion_iva: string | null;
  verificado: boolean;
  puede_publicar: boolean;
  cuenta_cobro_vinculada: boolean;
  /** Nombre de la cuenta de Mercado Pago vinculada. La credencial no vuelve nunca. */
  cuenta_cobro: string | null;
  porcentaje_sena: number | null;
};

export type Cuenta = {
  id: string;
  email: string;
  nombre: string;
  apellido: string;
  telefono: string | null;
  email_verificado: boolean;
  telefono_verificado: boolean;
  es_viajero: boolean;
  es_prestador: boolean;
  es_operador: boolean;
  prestador: PrestadorCuenta | null;
};

export type PedidoVerificacion = { enviado: boolean; detalle: string; enlace: string | null };

export const registrarse = (datos: {
  email: string;
  password: string;
  nombre: string;
  apellido: string;
  telefono?: string;
  acepta_terminos: boolean;
}) => api<Sesion>("/auth/registro", { method: "POST", body: JSON.stringify(datos) });

export const ingresar = (datos: { email: string; password: string }) =>
  api<Sesion>("/auth/ingreso", { method: "POST", body: JSON.stringify(datos) });

export const miCuenta = (token: string) => api<Cuenta>("/auth/yo", { token });

export const pedirVerificacion = (token: string) =>
  api<PedidoVerificacion>("/auth/verificacion", { method: "POST", token });

export const confirmarEmail = (tokenVerificacion: string) =>
  api<Cuenta>("/auth/verificacion/confirmar", {
    method: "POST",
    body: JSON.stringify({ token: tokenVerificacion }),
  });

export const altaPrestador = (
  token: string,
  datos: { razon_social: string; cuit: string; condicion_iva: string; porcentaje_sena?: number },
) => api<Cuenta>("/auth/prestador", { method: "POST", token, body: JSON.stringify(datos) });

export const vincularMercadoPago = (token: string, access_token: string) =>
  api<PrestadorCuenta>("/auth/prestador/mercadopago", {
    method: "PUT",
    token,
    body: JSON.stringify({ access_token }),
  });

export const desvincularMercadoPago = (token: string) =>
  api<PrestadorCuenta>("/auth/prestador/mercadopago", { method: "DELETE", token });

export const ingresarConGoogle = (credencial: string) =>
  api<Sesion>("/auth/google", { method: "POST", body: JSON.stringify({ credencial }) });

/* --- Alta y edición de publicaciones (prestador) --- */

export type EstadoPublicacion =
  | "borrador"
  | "en_revision"
  | "aprobada"
  | "pausada"
  | "rechazada";

export type TarifaEdicion = {
  id: string;
  nombre: string;
  precio_noche: string;
  fecha_desde: string | null;
  fecha_hasta: string | null;
  estadia_minima: number;
  estadia_maxima: number | null;
  anticipacion_minima_dias: number;
  prioridad: number;
};

export type UnidadEdicion = {
  id: string;
  nombre: string;
  capacidad: number;
  capacidad_base: number | null;
  cargo_limpieza: string;
  cargo_persona_extra: string;
  cargo_mascota: string;
  descuento_semanal: string;
  descuento_mensual: string;
  activa: boolean;
  tarifas: TarifaEdicion[];
  /* Salones (docs/04). En alojamiento vienen vacíos. */
  capacidad_sentados: number | null;
  preparacion_minutos: number;
  franjas: FranjaEdicion[];
  tarifa_horaria: TarifaHorariaEdicion | null;
  adicionales: AdicionalEdicion[];
};

/** Precio por día de la semana: "0" es lunes, "6" domingo. */
export type PreciosPorDia = Record<string, string> | null;

export type FranjaEdicion = {
  id: string;
  nombre: string;
  hora_inicio: string;
  hora_fin: string;
  precio: string;
  precios_dia_semana: PreciosPorDia;
};

export type TarifaHorariaEdicion = {
  precio_hora: string;
  horas_minimas: number;
  hora_apertura: string;
  hora_cierre: string;
  precios_dia_semana: PreciosPorDia;
  recargo_nocturno_desde: string | null;
  recargo_nocturno_porcentaje: string;
};

export type AdicionalEdicion = {
  id: string;
  nombre: string;
  descripcion: string | null;
  precio: string;
  por_persona: boolean;
};

export type TipoServicioCodigo = "alojamiento" | "salon_eventos";

export type FotoEdicion = { id: string; url: string; orden: number; descripcion: string | null };

export type PublicacionEdicion = {
  id: string;
  tipo: TipoServicioCodigo;
  modo_reserva: "noches" | "horas";
  porcentaje_sena: number | null;
  slug: string;
  titulo: string;
  descripcion: string;
  reglas_casa: string | null;
  estado: EstadoPublicacion;
  motivo_rechazo: string | null;
  subtipo_servicio_id: string | null;
  localidad_id: string;
  localidad: string;
  provincia: string;
  zona_id: string | null;
  direccion: string | null;
  lat: number | null;
  lon: number | null;
  hora_ingreso: string | null;
  hora_salida: string | null;
  confirmacion_inmediata: boolean;
  politica_cancelacion_id: string | null;
  comodidades: string[];
  fotos: FotoEdicion[];
  unidades: UnidadEdicion[];
  faltantes: string[];
};

const MIS = "/mis-publicaciones";

export const misPublicaciones = (token: string) =>
  api<PublicacionEdicion[]>(MIS, { token });

export const miPublicacion = (token: string, id: string) =>
  api<PublicacionEdicion>(`${MIS}/${id}`, { token });

export const crearPublicacion = (
  token: string,
  datos: {
    titulo: string;
    localidad_id: string;
    subtipo_servicio_id?: string;
    tipo?: TipoServicioCodigo;
  },
) => api<PublicacionEdicion>(MIS, { method: "POST", token, body: JSON.stringify(datos) });

export const editarPublicacion = (token: string, id: string, cambios: Record<string, unknown>) =>
  api<PublicacionEdicion>(`${MIS}/${id}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(cambios),
  });

export const borrarFoto = (token: string, id: string, fotoId: string) =>
  api<PublicacionEdicion>(`${MIS}/${id}/fotos/${fotoId}`, { method: "DELETE", token });

export const reordenarFotos = (token: string, id: string, fotos: string[]) =>
  api<PublicacionEdicion>(`${MIS}/${id}/fotos`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ fotos }),
  });

export const crearUnidad = (token: string, id: string, datos: Record<string, unknown>) =>
  api<PublicacionEdicion>(`${MIS}/${id}/unidades`, {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const borrarUnidad = (token: string, id: string, unidadId: string) =>
  api<PublicacionEdicion>(`${MIS}/${id}/unidades/${unidadId}`, { method: "DELETE", token });

export const crearTarifa = (
  token: string,
  id: string,
  unidadId: string,
  datos: Record<string, unknown>,
) =>
  api<PublicacionEdicion>(`${MIS}/${id}/unidades/${unidadId}/tarifas`, {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const borrarTarifa = (token: string, id: string, unidadId: string, tarifaId: string) =>
  api<PublicacionEdicion>(`${MIS}/${id}/unidades/${unidadId}/tarifas/${tarifaId}`, {
    method: "DELETE",
    token,
  });

/* Salones: turnos, precio por hora y adicionales de un espacio. */
const UNIDAD = (id: string, unidadId: string) => `${MIS}/${id}/unidades/${unidadId}`;

const enviar = (token: string, ruta: string, method: string, datos?: unknown) =>
  api<PublicacionEdicion>(ruta, {
    method,
    token,
    ...(datos === undefined ? {} : { body: JSON.stringify(datos) }),
  });

export const crearFranja = (token: string, id: string, unidadId: string, datos: unknown) =>
  enviar(token, `${UNIDAD(id, unidadId)}/franjas`, "POST", datos);

export const borrarFranja = (token: string, id: string, unidadId: string, franjaId: string) =>
  enviar(token, `${UNIDAD(id, unidadId)}/franjas/${franjaId}`, "DELETE");

export const guardarTarifaHoraria = (
  token: string,
  id: string,
  unidadId: string,
  datos: unknown,
) => enviar(token, `${UNIDAD(id, unidadId)}/tarifa-horaria`, "PUT", datos);

export const quitarTarifaHoraria = (token: string, id: string, unidadId: string) =>
  enviar(token, `${UNIDAD(id, unidadId)}/tarifa-horaria`, "DELETE");

export const crearAdicional = (token: string, id: string, unidadId: string, datos: unknown) =>
  enviar(token, `${UNIDAD(id, unidadId)}/adicionales`, "POST", datos);

export const borrarAdicional = (
  token: string,
  id: string,
  unidadId: string,
  adicionalId: string,
) => enviar(token, `${UNIDAD(id, unidadId)}/adicionales/${adicionalId}`, "DELETE");

export const cambiarEstado = (
  token: string,
  id: string,
  accion: "enviar-a-revision" | "pausar" | "reactivar" | "volver-a-borrador",
) => api<PublicacionEdicion>(`${MIS}/${id}/${accion}`, { method: "POST", token });

/** La subida de fotos va como multipart: no lleva Content-Type propio. */
export async function subirFoto(token: string, id: string, archivo: File): Promise<PublicacionEdicion> {
  const cuerpo = new FormData();
  cuerpo.append("archivo", archivo);
  const res = await fetch(`${BASE}${MIS}/${id}/fotos`, {
    method: "POST",
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
    body: cuerpo,
  });
  if (!res.ok) {
    const cuerpoError = await res.json().catch(() => ({}));
    const detalle = (cuerpoError as { detail?: unknown }).detail;
    throw new ApiError(res.status, typeof detalle === "string" ? detalle : res.statusText, detalle);
  }
  return res.json() as Promise<PublicacionEdicion>;
}

/* --- Operador --- */

export type EnRevision = {
  id: string;
  slug: string;
  titulo: string;
  descripcion: string;
  estado: EstadoPublicacion;
  prestador: string;
  prestador_verificado: boolean;
  localidad: string;
  provincia: string;
  fotos: string[];
  unidades: number;
  capacidad_maxima: number;
  comodidades: string[];
  motivo_rechazo: string | null;
};

export type ResumenOperador = {
  en_revision: number;
  aprobadas: number;
  rechazadas: number;
  borradores: number;
};

export const colaOperador = (token: string, estado = "en_revision") =>
  api<EnRevision[]>(`/admin/publicaciones?estado=${estado}`, { token });

export const resumenOperador = (token: string) =>
  api<ResumenOperador>("/admin/publicaciones/resumen", { token });

export const aprobarPublicacion = (token: string, id: string) =>
  api<EnRevision>(`/admin/publicaciones/${id}/aprobar`, { method: "POST", token });

export const rechazarPublicacion = (token: string, id: string, motivo: string) =>
  api<EnRevision>(`/admin/publicaciones/${id}/rechazar`, {
    method: "POST",
    token,
    body: JSON.stringify({ motivo }),
  });

/* Catálogos para armar los formularios sin inventar códigos. */
export type Politica = { id: string; codigo: string; nombre: string };

export type CatalogoAlta = {
  localidades: { id: string; nombre: string; provincia: string; slug: string }[];
  subtipos: { id: string; codigo: string; nombre: string }[];
  politicas: Politica[];
  comodidades: (Comodidad & { icono: string | null })[];
};

export const catalogoAlta = (tipo: TipoServicioCodigo = "alojamiento") =>
  api<CatalogoAlta>(`/catalogos/alta?tipo=${tipo}`);

/* --- Calendario de una unidad --- */

export type Tramo = {
  id: string;
  desde: string;
  hasta: string;
  origen: "manual" | "ical" | "reserva" | "retencion";
  etiqueta: string;
  nota: string | null;
  calendario: string | null;
  editable: boolean;
};

export type CalendarioExterno = {
  id: string;
  nombre: string;
  url: string;
  ultima_sincronizacion: string | null;
  ultimo_error: string | null;
};

export type Agenda = {
  unidad_id: string;
  unidad: string;
  url_exportacion: string;
  tramos: Tramo[];
  calendarios: CalendarioExterno[];
};

export type Sincronizacion = {
  importados: number;
  descartados: number;
  detalle: string;
  calendarios: CalendarioExterno[];
};

const ruta = (id: string, unidadId: string) => `${MIS}/${id}/unidades/${unidadId}`;

export const verAgenda = (token: string, id: string, unidadId: string) =>
  api<Agenda>(`${ruta(id, unidadId)}/calendario`, { token });

export const bloquearFechas = (
  token: string,
  id: string,
  unidadId: string,
  datos: { desde: string; hasta: string; nota?: string },
) =>
  api<Agenda>(`${ruta(id, unidadId)}/bloqueos`, {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const soltarFechas = (token: string, id: string, unidadId: string, bloqueoId: string) =>
  api<Agenda>(`${ruta(id, unidadId)}/bloqueos/${bloqueoId}`, { method: "DELETE", token });

export const agregarCalendario = (
  token: string,
  id: string,
  unidadId: string,
  datos: { nombre: string; url: string },
) =>
  api<Agenda>(`${ruta(id, unidadId)}/calendarios`, {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const quitarCalendario = (
  token: string,
  id: string,
  unidadId: string,
  calendarioId: string,
) => api<Agenda>(`${ruta(id, unidadId)}/calendarios/${calendarioId}`, { method: "DELETE", token });

export const sincronizarCalendario = (
  token: string,
  id: string,
  unidadId: string,
  calendarioId: string,
) =>
  api<Sincronizacion>(`${ruta(id, unidadId)}/calendarios/${calendarioId}/sincronizar`, {
    method: "POST",
    token,
  });

/* --- Reservas y pagos --- */

export type EstadoReserva =
  | "pendiente_pago"
  | "pendiente_aprobacion"
  | "confirmada"
  | "cancelada"
  | "completada"
  | "en_reclamo";

export type PasarelaDisponible = {
  codigo: string;
  nombre: string;
  disponible: boolean;
  reparte_automaticamente: boolean;
  motivo: string | null;
};

export type ComisionReserva = {
  base: string;
  comision_neta: string;
  iva: string;
  comision_total: string;
  cargo_viajero: string;
  descuento_prestador: string;
  regla: string;
};

export type ItemReserva = {
  unidad_id: string;
  unidad: string;
  publicacion: string;
  slug: string;
  localidad: string;
  provincia: string;
  fecha_inicio: string;
  fecha_fin: string;
  noches: number;
  adultos: number;
  menores: number;
  mascotas: number;
  subtotal: string;
  desglose: Record<string, unknown>;
  comision: ComisionReserva | null;
  fotos: { url: string; descripcion: string | null }[];
  /** Eventos (salones): el horario exacto. En alojamiento, null. */
  inicio_en?: string | null;
  fin_en?: string | null;
  /** Solo con la reserva confirmada. */
  direccion: string | null;
  lat: number | null;
  lon: number | null;
};

export type Reserva = {
  codigo: string;
  estado: EstadoReserva;
  total: string;
  monto_sena: string | null;
  /** Con seña: lo que queda por pagarle al anfitrión. */
  saldo_con_anfitrion?: string | null;
  moneda: string;
  vence_pago_en: string | null;
  vence_aprobacion_en: string | null;
  cancelada_en: string | null;
  motivo_cancelacion: string | null;
  politica_cancelacion: {
    codigo: string;
    nombre: string;
    tramos: { dias_antes: number; porcentaje_reintegro: number }[];
  } | null;
  creada_en: string;
  items: ItemReserva[];
  pagos: { pasarela: string; estado: string; monto: string; id_externo: string | null }[];
  reintegro_si_cancela: { porcentaje: number; monto: string; motivo: string } | null;
};

export type Preferencia = {
  pasarela: string;
  url_pago: string;
  id_externo: string;
  total: string;
};

export const pasarelas = () => api<PasarelaDisponible[]>("/pasarelas");

export const crearReserva = (
  token: string,
  datos: {
    unidad_id: string;
    desde: string;
    hasta: string;
    adultos: number;
    menores?: number;
    mascotas?: number;
    acepta_terminos: boolean;
  },
) => api<Reserva>("/reservas", { method: "POST", token, body: JSON.stringify(datos) });

export const misReservas = (token: string) => api<Reserva[]>("/reservas", { token });

export const verReserva = (token: string, codigo: string) =>
  api<Reserva>(`/reservas/${codigo}`, { token });

export const pedirPago = (token: string, codigo: string, pasarela?: string) =>
  api<Preferencia>(`/reservas/${codigo}/pagar`, {
    method: "POST",
    token,
    body: JSON.stringify({ pasarela: pasarela ?? null }),
  });

export const cancelarReserva = (token: string, codigo: string, motivo: string) =>
  api<Reserva>(`/reservas/${codigo}/cancelar`, {
    method: "POST",
    token,
    body: JSON.stringify({ motivo }),
  });

export const reservasDelPrestador = (token: string) => api<Reserva[]>("/mis-reservas", { token });

export const aprobarReserva = (token: string, codigo: string) =>
  api<Reserva>(`/mis-reservas/${codigo}/aprobar`, { method: "POST", token });

export const rechazarReserva = (token: string, codigo: string, motivo: string) =>
  api<Reserva>(`/mis-reservas/${codigo}/rechazar`, {
    method: "POST",
    token,
    body: JSON.stringify({ motivo }),
  });

/** Solo en desarrollo: dispara la notificación que mandaría una billetera real. */
export const simularPago = (datos: { pago: string; reserva: string; estado: string }) =>
  api<{ estado: string; reserva: string; resultado?: string }>("/simulador/pagar", {
    method: "POST",
    body: JSON.stringify(datos),
  });

/* --- Paneles y favoritos --- */

export type FavoritoGuardado = {
  publicacion_id: string;
  slug: string;
  titulo: string;
  localidad: string;
  provincia: string;
  subtipo: string | null;
  capacidad_maxima: number;
  fotos: { url: string; descripcion: string | null }[];
};

export type LineaCobro = {
  codigo: string;
  estado: EstadoReserva;
  alojamiento: string;
  unidad: string;
  fecha_inicio: string;
  fecha_fin: string;
  paga_el_viajero: string;
  tu_precio: string;
  comision: string;
  iva_comision: string;
  te_queda: string;
  regla: string;
  pagado: boolean;
};

export type ResumenCobros = {
  reservas: number;
  paga_el_viajero: string;
  tu_precio: string;
  comision: string;
  te_queda: string;
  lineas: LineaCobro[];
};

export type LineaOperador = {
  codigo: string;
  estado: EstadoReserva;
  creada_en: string;
  viajero: string;
  prestador: string;
  alojamiento: string;
  localidad: string;
  fecha_inicio: string;
  fecha_fin: string;
  total: string;
  comision: string;
  iva: string;
  al_prestador: string;
  pasarela: string | null;
  pagado: boolean;
};

export type ResumenOperacion = {
  reservas: number;
  facturado: string;
  comision: string;
  iva: string;
  lineas: LineaOperador[];
};

export type ResumenComisiones = {
  reservas: number;
  base: string;
  comision_neta: string;
  iva: string;
  comision_total: string;
  la_paga_el_viajero: string;
  la_absorbe_el_prestador: string;
};

export const misFavoritos = (token: string) => api<FavoritoGuardado[]>("/favoritos", { token });

export const guardarFavorito = (token: string, id: string) =>
  api<void>(`/favoritos/${id}`, { method: "PUT", token });

export const sacarFavorito = (token: string, id: string) =>
  api<void>(`/favoritos/${id}`, { method: "DELETE", token });

export const misCobros = (token: string, params?: URLSearchParams) =>
  api<ResumenCobros>(`/mis-cobros${params?.size ? `?${params}` : ""}`, { token });

export const reservasOperador = (token: string, params?: URLSearchParams) =>
  api<ResumenOperacion>(`/admin/reservas${params?.size ? `?${params}` : ""}`, { token });

export const comisionesOperador = (token: string) =>
  api<ResumenComisiones>("/admin/comisiones", { token });

/* --- Calendario integrado (docs/01 §5 R3) --- */

export type Plataforma = {
  codigo: string;
  nombre: string;
  tiene_ical: boolean;
  donde_esta: string;
  ejemplo_url: string;
  nota: string;
  pasos: string[];
};

export type TramoAgenda = {
  desde: string;
  hasta: string;
  noches: number;
  origen: "manual" | "ical" | "reserva" | "retencion";
  etiqueta: string;
  nota: string | null;
  calendario: string | null;
  plataforma: string | null;
  editable: boolean;
};

export type UnidadAgenda = {
  unidad_id: string;
  unidad: string;
  capacidad: number;
  publicacion_id: string;
  publicacion: string;
  slug: string;
  estado: EstadoPublicacion;
  url_exportacion: string;
  tramos: TramoAgenda[];
  noches_ocupadas: number;
};

export type Conexion = {
  id: string;
  unidad_id: string;
  unidad: string;
  publicacion_id: string;
  publicacion: string;
  nombre: string;
  plataforma: string;
  plataforma_nombre: string;
  url: string;
  ultima_sincronizacion: string | null;
  ultimo_error: string | null;
};

export type AgendaGeneral = {
  desde: string;
  hasta: string;
  resumen: {
    unidades: number;
    conexiones: number;
    con_error: number;
    noches_ocupadas: number;
    sin_conectar: number;
  };
  unidades: UnidadAgenda[];
  conexiones: Conexion[];
  direccion_buzon: string;
};

export type ResultadoSincronizarTodo = {
  sincronizados: number;
  con_error: number;
  resultados: {
    calendario_id: string;
    nombre: string;
    unidad: string;
    plataforma: string;
    ok: boolean;
    detalle: string;
  }[];
};

export const canales = () => api<Plataforma[]>("/canales");

export const calendarioIntegrado = (token: string, params?: URLSearchParams) =>
  api<AgendaGeneral>(`/mi-calendario${params?.size ? `?${params}` : ""}`, { token });

export const sincronizarTodo = (token: string) =>
  api<ResultadoSincronizarTodo>("/mi-calendario/sincronizar", { method: "POST", token });

/* --- Reservas que entraron por fuera (Despegar, WhatsApp, teléfono) --- */

export type ReservaExterna = {
  id: string;
  unidad_id: string | null;
  unidad: string | null;
  publicacion: string | null;
  origen: "particular" | "correo";
  estado: "confirmada" | "por_revisar" | "descartada";
  plataforma: string;
  plataforma_nombre: string;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  huesped: string | null;
  contacto: string | null;
  personas: number | null;
  monto: string | null;
  codigo_externo: string | null;
  nota: string | null;
  faltantes: string[];
  creado_en: string;
};

export type LecturaCorreo = {
  reserva: ReservaExterna;
  nueva: boolean;
  detalle: string;
  unidad_leida: string | null;
};

export type ReservaParticular = {
  unidad_id: string;
  fecha_inicio: string;
  fecha_fin: string;
  huesped?: string;
  contacto?: string;
  personas?: number;
  monto?: string;
  plataforma?: string;
  nota?: string;
};

export const cargarReservaParticular = (token: string, datos: ReservaParticular) =>
  api<ReservaExterna>("/mi-calendario/reservas-externas", {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const leerCorreo = (
  token: string,
  datos: { cuerpo: string; asunto?: string; remitente?: string; unidad_id?: string },
) =>
  api<LecturaCorreo>("/mi-calendario/correo", {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const porRevisar = (token: string) =>
  api<ReservaExterna[]>("/mi-calendario/por-revisar", { token });

export const completarReservaExterna = (
  token: string,
  id: string,
  datos: { unidad_id?: string; fecha_inicio?: string; fecha_fin?: string; huesped?: string },
) =>
  api<ReservaExterna>(`/mi-calendario/reservas-externas/${id}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(datos),
  });

export const descartarReservaExterna = (token: string, id: string) =>
  api<void>(`/mi-calendario/reservas-externas/${id}`, { method: "DELETE", token });

/* --- Explorar: lo que hay publicado, sin pedir fechas --- */

export type PaginaExplorar = {
  total: number;
  pagina: number;
  por_pagina: number;
  paginas: number;
  publicaciones: ResumenDestino[];
  /** Desde dónde se midieron las distancias, si se midieron. */
  origen: [number, number] | null;
};

export const explorar = (params?: URLSearchParams) =>
  api<PaginaExplorar>(`/publicaciones/explorar${params?.size ? `?${params}` : ""}`);


/* --- Salones de eventos para el viajero (docs/04, etapa 4) --- */

export type PrecioDesde = { monto: string; detalle: string };

export type SalonResultado = {
  slug: string;
  titulo: string;
  subtipo: string | null;
  localidad: string;
  provincia: string;
  lat: number | null;
  lon: number | null;
  fotos: { url: string; descripcion: string | null }[];
  comodidades: string[];
  capacidad_maxima: number;
  sentados_maximo: number | null;
  precio_desde: PrecioDesde | null;
  confirmacion_inmediata: boolean;
  disponible: boolean | null;
  es_demo: boolean;
};

export type BusquedaSalones = {
  total: number;
  pagina: number;
  paginas: number;
  resultados: SalonResultado[];
};

export type DestinoSalon = { nombre: string; slug: string; provincia: string; salones: number };

export type AdicionalSalon = {
  id: string;
  nombre: string;
  descripcion: string | null;
  precio: string;
  por_persona: boolean;
};

export type EspacioSalon = {
  id: string;
  nombre: string;
  capacidad: number;
  capacidad_sentados: number | null;
  capacidad_base: number | null;
  cargo_persona_extra: string;
  preparacion_minutos: number;
  franjas: {
    id: string;
    nombre: string;
    hora_inicio: string;
    hora_fin: string;
    precio: string;
    termina_al_dia_siguiente: boolean;
  }[];
  por_horas: {
    precio_hora: string;
    horas_minimas: number;
    hora_apertura: string;
    hora_cierre: string;
  } | null;
  adicionales: AdicionalSalon[];
};

export type FichaSalon = {
  publicacion_id: string;
  slug: string;
  titulo: string;
  descripcion: string;
  reglas: string | null;
  subtipo: string | null;
  localidad: string;
  localidad_slug: string;
  provincia: string;
  zona: string | null;
  lat: number | null;
  lon: number | null;
  confirmacion_inmediata: boolean;
  porcentaje_sena: number | null;
  es_demo: boolean;
  prestador: { razon_social: string; verificado: boolean; publica_desde: number };
  politica_cancelacion: {
    codigo: string;
    nombre: string;
    descripcion: string | null;
    tramos: { dias_antes: number; porcentaje_reintegro: number }[];
  } | null;
  fotos: { url: string; descripcion: string | null }[];
  comodidades: { codigo: string; nombre: string }[];
  espacios: EspacioSalon[];
  alojamientos_del_anfitrion: { titulo: string; slug: string }[];
  moneda: string;
};

export type DisponibilidadSalon = {
  unidad_id: string;
  dia: string;
  capacidad: number;
  capacidad_sentados: number | null;
  preparacion_minutos: number;
  franjas: {
    id: string;
    nombre: string;
    inicio: string;
    fin: string;
    precio: string;
    libre: boolean;
  }[];
  por_horas: {
    precio_hora: string;
    horas_minimas: number;
    apertura: string;
    cierre: string;
    recargo_nocturno_desde: string | null;
    recargo_nocturno_porcentaje: string;
  } | null;
  ocupado: { inicio: string; fin: string }[];
  adicionales: AdicionalSalon[];
};

export type PedidoEvento = {
  unidad_id: string;
  dia: string;
  invitados: number;
  franja_id?: string | null;
  hora_inicio?: string | null;
  horas?: number | null;
  adicionales?: string[];
};

export type CotizacionEvento = {
  inicio: string;
  fin: string;
  invitados: number;
  alquiler: string;
  lineas: { concepto: string; monto: string }[];
  subtotal: string;
  cargo_servicio: string;
  total: string;
  sena: string | null;
  a_pagar_ahora: string;
  saldo_con_anfitrion: string | null;
};

export const buscarSalones = (params: URLSearchParams) =>
  api<BusquedaSalones>(`/salones/buscar?${params}`);

export const destinosSalones = () => api<DestinoSalon[]>("/salones/destinos");

export const fichaSalon = (slug: string) =>
  api<FichaSalon>(`/salones/ficha/${encodeURIComponent(slug)}`);

export const disponibilidadSalon = (unidadId: string, dia: string) =>
  api<DisponibilidadSalon>(`/salones/unidades/${unidadId}/disponibilidad?dia=${dia}`);

export const cotizarEvento = (pedido: PedidoEvento) =>
  api<CotizacionEvento>("/salones/cotizacion", {
    method: "POST",
    body: JSON.stringify(pedido),
  });

export const reservarEvento = (
  token: string,
  pedido: PedidoEvento & { acepta_terminos: boolean },
) =>
  api<Reserva>("/salones/reservas", { method: "POST", token, body: JSON.stringify(pedido) });


/* --- Agenda por horas de un salón (docs/04, etapa 5) --- */

export type TramoHorario = {
  id: string;
  inicio: string;
  fin: string;
  origen: string;
  etiqueta: string;
  nota: string | null;
  reserva: string | null;
  editable: boolean;
};

export type AgendaHoraria = {
  unidad_id: string;
  unidad: string;
  desde: string;
  dias: number;
  preparacion_minutos: number;
  tramos: TramoHorario[];
};

const AGENDA_SALON = (id: string, unidadId: string) =>
  `/mis-publicaciones/${id}/unidades/${unidadId}`;

export const verAgendaHoraria = (
  token: string,
  id: string,
  unidadId: string,
  desde: string,
  dias = 7,
) =>
  api<AgendaHoraria>(
    `${AGENDA_SALON(id, unidadId)}/agenda-horaria?desde=${desde}&dias=${dias}`,
    { token },
  );

export const bloquearHoras = (
  token: string,
  id: string,
  unidadId: string,
  datos: { dia: string; hora_desde: string; hora_hasta: string; nota?: string | null },
) =>
  api<AgendaHoraria>(`${AGENDA_SALON(id, unidadId)}/bloqueos-horarios`, {
    method: "POST",
    token,
    body: JSON.stringify(datos),
  });

export const soltarHoras = (token: string, id: string, unidadId: string, bloqueoId: string) =>
  api<AgendaHoraria>(`${AGENDA_SALON(id, unidadId)}/bloqueos-horarios/${bloqueoId}`, {
    method: "DELETE",
    token,
  });
