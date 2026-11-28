"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  ApiError,
  aprobarPublicacion,
  bloquearHoras,
  borrarAdicional,
  soltarHoras,
  verAgendaHoraria,
  type AgendaHoraria,
  borrarFoto,
  borrarFranja,
  borrarTarifa,
  crearAdicional,
  crearFranja,
  guardarTarifaHoraria,
  quitarTarifaHoraria,
  borrarUnidad,
  cambiarEstado,
  crearPublicacion,
  crearTarifa,
  crearUnidad,
  editarPublicacion,
  rechazarPublicacion,
  reordenarFotos,
  subirFoto,
  agregarCalendario,
  bloquearFechas,
  quitarCalendario,
  sincronizarCalendario,
  soltarFechas,
  cargarReservaParticular,
  completarReservaExterna,
  descartarReservaExterna,
  leerCorreo,
  sincronizarTodo,
  verAgenda,
  type Agenda,
  type LecturaCorreo,
  type ReservaExterna,
  type ReservaParticular,
  type ResultadoSincronizarTodo,
  type PublicacionEdicion,
  agregarSalidaEspecial,
  anotarEnSalida,
  cambiarCupoSalida,
  crearPrecioPasajero,
  ubicarPorDireccion,
  importarAnuncio,
  type PropuestaAnuncio,
  crearLugarTraslado,
  editarLugarTraslado,
  quitarLugarTraslado,
  crearTramoTraslado,
  quitarTramoTraslado,
  guardarTarifaTraslado,
  crearTurno,
  quitarAnotado,
  quitarPrecioPasajero,
  quitarTurno,
  reanudarSalida,
  suspenderSalida,
  verSalidasPanel,
  type EleccionSalida,
  type SalidaPanel,
  type Suspension,
} from "./api";
import { tokenActual } from "./sesion";

export type Resultado =
  | { publicacion: PublicacionEdicion }
  | { error: string; faltantes?: string[] };

function problema(e: unknown, porDefecto: string): { error: string; faltantes?: string[] } {
  if (e instanceof ApiError) {
    const d = e.detalle;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      const obj = d as { mensaje?: string; faltantes?: string[] };
      if (obj.mensaje) return { error: obj.mensaje, faltantes: obj.faltantes };
    }
    if (Array.isArray(d)) {
      const primero = d[0] as { msg?: string } | undefined;
      // Pydantic antepone "Value error, " a los mensajes de los validadores propios.
      return { error: primero?.msg?.replace(/^Value error, /, "") ?? porDefecto };
    }
    return { error: e.message || porDefecto };
  }
  return { error: porDefecto };
}

/** Envuelve una llamada: consigue el token, traduce el error y refresca la lista. */
async function conSesion(
  llamada: (token: string) => Promise<PublicacionEdicion>,
  porDefecto: string,
): Promise<Resultado> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const publicacion = await llamada(token);
    revalidatePath("/mis-publicaciones");
    revalidatePath(`/mis-publicaciones/${publicacion.id}`);
    return { publicacion };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

export async function accionCrearPublicacion(_previo: unknown, datos: FormData) {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  const titulo = String(datos.get("titulo") ?? "").trim();
  const localidad_id = String(datos.get("localidad_id") ?? "");
  const subtipo = String(datos.get("subtipo_servicio_id") ?? "");
  const pedido = datos.get("tipo");
  const tipo =
    pedido === "salon_eventos" || pedido === "excursion" || pedido === "traslado"
      ? pedido
      : "alojamiento";
  if (!titulo || !localidad_id) return { error: "Falta el nombre o la localidad" };

  let creada: PublicacionEdicion;
  try {
    creada = await crearPublicacion(token, {
      titulo,
      localidad_id,
      subtipo_servicio_id: subtipo || undefined,
      tipo,
    });
  } catch (e) {
    return problema(e, "No pudimos crear la publicación.");
  }
  revalidatePath("/mis-publicaciones");
  redirect(`/mis-publicaciones/${creada.id}`);
}

export async function accionGuardarDatos(id: string, cambios: Record<string, unknown>) {
  return conSesion((t) => editarPublicacion(t, id, cambios), "No pudimos guardar los cambios.");
}

export async function accionBorrarFoto(id: string, fotoId: string) {
  return conSesion((t) => borrarFoto(t, id, fotoId), "No pudimos borrar la foto.");
}

export async function accionReordenarFotos(id: string, fotos: string[]) {
  return conSesion((t) => reordenarFotos(t, id, fotos), "No pudimos reordenar las fotos.");
}

export async function accionCrearUnidad(id: string, datos: Record<string, unknown>) {
  return conSesion((t) => crearUnidad(t, id, datos), "No pudimos crear la unidad.");
}

export async function accionBorrarUnidad(id: string, unidadId: string) {
  return conSesion((t) => borrarUnidad(t, id, unidadId), "No pudimos borrar la unidad.");
}

export async function accionCrearTarifa(
  id: string,
  unidadId: string,
  datos: Record<string, unknown>,
) {
  return conSesion((t) => crearTarifa(t, id, unidadId, datos), "No pudimos crear la tarifa.");
}

export async function accionBorrarTarifa(id: string, unidadId: string, tarifaId: string) {
  return conSesion(
    (t) => borrarTarifa(t, id, unidadId, tarifaId),
    "No pudimos borrar la tarifa.",
  );
}

/* --- Salones --- */

export async function accionCrearFranja(id: string, unidadId: string, datos: unknown) {
  return conSesion((t) => crearFranja(t, id, unidadId, datos), "No pudimos agregar el turno.");
}

export async function accionBorrarFranja(id: string, unidadId: string, franjaId: string) {
  return conSesion((t) => borrarFranja(t, id, unidadId, franjaId), "No pudimos quitar el turno.");
}

export async function accionGuardarTarifaHoraria(id: string, unidadId: string, datos: unknown) {
  return conSesion(
    (t) => guardarTarifaHoraria(t, id, unidadId, datos),
    "No pudimos guardar el precio por hora.",
  );
}

export async function accionQuitarTarifaHoraria(id: string, unidadId: string) {
  return conSesion(
    (t) => quitarTarifaHoraria(t, id, unidadId),
    "No pudimos quitar el precio por hora.",
  );
}

export async function accionCrearAdicional(id: string, unidadId: string, datos: unknown) {
  return conSesion(
    (t) => crearAdicional(t, id, unidadId, datos),
    "No pudimos agregar el adicional.",
  );
}

export async function accionBorrarAdicional(id: string, unidadId: string, adicionalId: string) {
  return conSesion(
    (t) => borrarAdicional(t, id, unidadId, adicionalId),
    "No pudimos quitar el adicional.",
  );
}

export async function accionCambiarEstado(
  id: string,
  accion: "enviar-a-revision" | "pausar" | "reactivar" | "volver-a-borrador",
) {
  return conSesion((t) => cambiarEstado(t, id, accion), "No pudimos cambiar el estado.");
}

export async function accionSubirFoto(id: string, datos: FormData): Promise<Resultado> {
  const archivo = datos.get("archivo");
  if (!(archivo instanceof File) || archivo.size === 0) return { error: "Elegí una imagen" };
  return conSesion((t) => subirFoto(t, id, archivo), "No pudimos subir la foto.");
}

/* --- Operador --- */

export async function accionAprobar(id: string): Promise<{ ok?: true; error?: string }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció." };
  try {
    await aprobarPublicacion(token, id);
  } catch (e) {
    return problema(e, "No pudimos aprobarla.");
  }
  revalidatePath("/admin/publicaciones");
  return { ok: true };
}

export async function accionRechazar(
  id: string,
  motivo: string,
): Promise<{ ok?: true; error?: string }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció." };
  if (motivo.trim().length < 5) {
    return { error: "Explicá qué hay que corregir: el prestador necesita saberlo." };
  }
  try {
    await rechazarPublicacion(token, id, motivo);
  } catch (e) {
    return problema(e, "No pudimos rechazarla.");
  }
  revalidatePath("/admin/publicaciones");
  return { ok: true };
}

/* --- Calendario --- */

export type ResultadoAgenda = { agenda: Agenda } | { error: string };

async function conAgenda(
  llamada: (token: string) => Promise<Agenda>,
  porDefecto: string,
): Promise<ResultadoAgenda> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { agenda: await llamada(token) };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

export async function accionVerAgenda(id: string, unidadId: string) {
  return conAgenda((t) => verAgenda(t, id, unidadId), "No pudimos traer el calendario.");
}

export async function accionBloquear(
  id: string,
  unidadId: string,
  datos: { desde: string; hasta: string; nota?: string },
) {
  return conAgenda(
    (t) => bloquearFechas(t, id, unidadId, datos),
    "No pudimos bloquear esas fechas.",
  );
}

export async function accionSoltar(id: string, unidadId: string, bloqueoId: string) {
  return conAgenda(
    (t) => soltarFechas(t, id, unidadId, bloqueoId),
    "No pudimos liberar esas fechas.",
  );
}

export async function accionAgregarCalendario(
  id: string,
  unidadId: string,
  datos: { nombre: string; url: string },
) {
  return conAgenda(
    (t) => agregarCalendario(t, id, unidadId, datos),
    "No pudimos agregar el calendario.",
  );
}

export async function accionQuitarCalendario(id: string, unidadId: string, calendarioId: string) {
  return conAgenda(
    (t) => quitarCalendario(t, id, unidadId, calendarioId),
    "No pudimos quitar el calendario.",
  );
}

export async function accionSincronizar(
  id: string,
  unidadId: string,
  calendarioId: string,
): Promise<{ detalle: string } | { error: string }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const r = await sincronizarCalendario(token, id, unidadId, calendarioId);
    return { detalle: r.detalle };
  } catch (e) {
    return problema(e, "No pudimos sincronizar.");
  }
}

/** Trae de nuevo todos los calendarios conectados, de todas las unidades. */
export async function accionSincronizarTodo(): Promise<
  ResultadoSincronizarTodo | { error: string }
> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const r = await sincronizarTodo(token);
    revalidatePath("/mi-calendario");
    return r;
  } catch (e) {
    return problema(e, "No pudimos sincronizar.");
  }
}

/* --- Reservas que entraron por fuera --- */

export type ResultadoExterna = { reserva: ReservaExterna } | { error: string };

async function conToken<T>(
  hacer: (token: string) => Promise<T>,
  falla: string,
): Promise<T | { error: string }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const r = await hacer(token);
    revalidatePath("/mi-calendario");
    return r;
  } catch (e) {
    return problema(e, falla);
  }
}

/** Una venta cerrada por WhatsApp, teléfono o en la puerta. */
export async function accionCargarVentaPropia(
  datos: ReservaParticular,
): Promise<ResultadoExterna> {
  const r = await conToken(
    (t) => cargarReservaParticular(t, datos),
    "No pudimos cargar la reserva.",
  );
  return "error" in r ? r : { reserva: r };
}

/** Pega el mail de confirmación y salen fechas, huésped y monto. */
export async function accionLeerCorreo(datos: {
  cuerpo: string;
  asunto?: string;
  remitente?: string;
  unidad_id?: string;
}): Promise<LecturaCorreo | { error: string }> {
  return conToken((t) => leerCorreo(t, datos), "No pudimos leer ese mensaje.");
}

export async function accionCompletarExterna(
  id: string,
  datos: { unidad_id?: string; fecha_inicio?: string; fecha_fin?: string; huesped?: string },
): Promise<ResultadoExterna> {
  const r = await conToken(
    (t) => completarReservaExterna(t, id, datos),
    "No pudimos completarla.",
  );
  return "error" in r ? r : { reserva: r };
}

export async function accionDescartarExterna(id: string): Promise<{ error?: string }> {
  const r = await conToken((t) => descartarReservaExterna(t, id), "No pudimos descartarla.");
  return r && "error" in r ? r : {};
}

/* --- Agenda por horas de un salón --- */

export type ResultadoAgendaHoraria = { agenda: AgendaHoraria } | { error: string };

async function conAgendaHoraria(
  llamada: (token: string) => Promise<AgendaHoraria>,
  porDefecto: string,
): Promise<ResultadoAgendaHoraria> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { agenda: await llamada(token) };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

export async function accionAgendaHoraria(id: string, unidadId: string, desde: string) {
  return conAgendaHoraria(
    (t) => verAgendaHoraria(t, id, unidadId, desde),
    "No pudimos traer la agenda.",
  );
}

export async function accionBloquearHoras(
  id: string,
  unidadId: string,
  datos: { dia: string; hora_desde: string; hora_hasta: string; nota?: string | null },
) {
  return conAgendaHoraria(
    (t) => bloquearHoras(t, id, unidadId, datos),
    "No pudimos bloquear ese horario.",
  );
}

export async function accionSoltarHoras(id: string, unidadId: string, bloqueoId: string) {
  return conAgendaHoraria(
    (t) => soltarHoras(t, id, unidadId, bloqueoId),
    "No pudimos liberar ese horario.",
  );
}

/* --- Excursiones (docs/05, etapa 3) --- */

export async function accionCrearTurno(id: string, unidadId: string, datos: unknown) {
  return conSesion((t) => crearTurno(t, id, unidadId, datos), "No pudimos agregar el turno.");
}

export async function accionQuitarTurno(id: string, unidadId: string, turnoId: string) {
  return conSesion((t) => quitarTurno(t, id, unidadId, turnoId), "No pudimos quitar el turno.");
}

export async function accionCrearPrecioPasajero(id: string, unidadId: string, datos: unknown) {
  return conSesion(
    (t) => crearPrecioPasajero(t, id, unidadId, datos),
    "No pudimos agregar el precio.",
  );
}

export async function accionQuitarPrecioPasajero(id: string, unidadId: string, precioId: string) {
  return conSesion(
    (t) => quitarPrecioPasajero(t, id, unidadId, precioId),
    "No pudimos quitar el precio.",
  );
}

/** Lee el texto pegado de un anuncio de Airbnb o Booking y devuelve la propuesta. */
export async function accionImportarAnuncio(
  id: string,
  texto: string,
): Promise<{ propuesta: PropuestaAnuncio } | { error: string }> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { propuesta: await importarAnuncio(token, id, texto) };
  } catch (e) {
    return problema(e, "No pudimos leer ese texto.");
  }
}

export async function accionUbicarPorDireccion(id: string) {
  return conSesion((t) => ubicarPorDireccion(t, id), "No pudimos ubicar la dirección.");
}

/* --- Traslados (docs/06, etapa 3) --- */

export async function accionCrearLugar(id: string, datos: unknown) {
  return conSesion((t) => crearLugarTraslado(t, id, datos), "No pudimos agregar el lugar.");
}

export async function accionEditarLugar(id: string, lugarId: string, datos: unknown) {
  return conSesion(
    (t) => editarLugarTraslado(t, id, lugarId, datos),
    "No pudimos guardar el lugar.",
  );
}

export async function accionQuitarLugar(id: string, lugarId: string) {
  return conSesion((t) => quitarLugarTraslado(t, id, lugarId), "No pudimos quitar el lugar.");
}

export async function accionCrearTramo(id: string, unidadId: string, datos: unknown) {
  return conSesion(
    (t) => crearTramoTraslado(t, id, unidadId, datos),
    "No pudimos agregar el recorrido.",
  );
}

export async function accionQuitarTramo(id: string, unidadId: string, tramoId: string) {
  return conSesion(
    (t) => quitarTramoTraslado(t, id, unidadId, tramoId),
    "No pudimos quitar el recorrido.",
  );
}

export async function accionGuardarTarifaTraslado(id: string, unidadId: string, datos: unknown) {
  return conSesion(
    (t) => guardarTarifaTraslado(t, id, unidadId, datos),
    "No pudimos guardar la tarifa.",
  );
}

export type ResultadoSalidas = { salidas: SalidaPanel[] } | { error: string };
export type ResultadoSalida =
  | { salida: SalidaPanel; suspension?: Omit<Suspension, "salida"> }
  | { error: string };

export async function accionSalidasPanel(
  id: string,
  unidadId: string,
  desde: string,
  hasta: string,
): Promise<ResultadoSalidas> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { salidas: await verSalidasPanel(token, id, unidadId, desde, hasta) };
  } catch (e) {
    return problema(e, "No pudimos traer las salidas.");
  }
}

async function conSalida(
  llamada: (token: string) => Promise<SalidaPanel>,
  porDefecto: string,
): Promise<ResultadoSalida> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    return { salida: await llamada(token) };
  } catch (e) {
    return problema(e, porDefecto);
  }
}

export async function accionSuspenderSalida(
  id: string,
  unidadId: string,
  datos: EleccionSalida & { motivo: string },
): Promise<ResultadoSalida> {
  const token = await tokenActual();
  if (!token) return { error: "Tu sesión venció. Ingresá de nuevo." };
  try {
    const { salida, ...suspension } = await suspenderSalida(token, id, unidadId, datos);
    revalidatePath("/mis-reservas");
    return { salida, suspension };
  } catch (e) {
    return problema(e, "No pudimos suspender la salida.");
  }
}

export async function accionReanudarSalida(id: string, unidadId: string, datos: EleccionSalida) {
  return conSalida(
    (t) => reanudarSalida(t, id, unidadId, datos),
    "No pudimos reanudar la salida.",
  );
}

export async function accionCambiarCupoSalida(
  id: string,
  unidadId: string,
  datos: EleccionSalida & { cupo: number },
) {
  return conSalida(
    (t) => cambiarCupoSalida(t, id, unidadId, datos),
    "No pudimos cambiar el cupo.",
  );
}

export async function accionAnotarEnSalida(
  id: string,
  unidadId: string,
  datos: EleccionSalida & { personas: number; nota?: string | null },
) {
  return conSalida(
    (t) => anotarEnSalida(t, id, unidadId, datos),
    "No pudimos anotar esos lugares.",
  );
}

export async function accionQuitarAnotado(id: string, unidadId: string, tomadoId: string) {
  return conSalida(
    (t) => quitarAnotado(t, id, unidadId, tomadoId),
    "No pudimos liberar esos lugares.",
  );
}

export async function accionAgregarSalidaEspecial(id: string, unidadId: string, datos: unknown) {
  return conSalida(
    (t) => agregarSalidaEspecial(t, id, unidadId, datos),
    "No pudimos agregar la salida.",
  );
}
