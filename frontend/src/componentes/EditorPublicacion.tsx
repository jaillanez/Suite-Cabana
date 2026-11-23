"use client";

import { useRef, useState, useTransition } from "react";
import Link from "next/link";

import {
  accionBorrarFoto,
  accionBorrarTarifa,
  accionBorrarUnidad,
  accionCambiarEstado,
  accionCrearTarifa,
  accionCrearUnidad,
  accionGuardarDatos,
  accionReordenarFotos,
  accionSubirFoto,
  type Resultado,
} from "@/lib/acciones-publicaciones";
import type { CatalogoAlta, PublicacionEdicion } from "@/lib/api";
import { pesos, plural } from "@/lib/formato";
import Estado, { TEXTOS_ESTADO } from "./EstadoPublicacion";
import {
  Alerta,
  ChevronIzq,
  ChevronDer,
  Cruz,
  ICONOS_COMODIDAD,
} from "./Iconos";
import CalendarioUnidad from "./CalendarioUnidad";
import MapaSelector from "./MapaSelector";
import UnidadesSalon from "./UnidadesSalon";
import estilos from "./EditorPublicacion.module.css";

export default function EditorPublicacion({
  inicial,
  catalogo,
  puedePublicar,
}: {
  inicial: PublicacionEdicion;
  catalogo: CatalogoAlta;
  puedePublicar: boolean;
}) {
  const [p, setP] = useState(inicial);
  const [aviso, setAviso] = useState<{
    mensaje: string;
    faltantes?: string[];
  } | null>(null);
  const [guardado, setGuardado] = useState(false);
  const [pendiente, empezar] = useTransition();
  const archivo = useRef<HTMLInputElement>(null);

  const bloqueada = p.estado === "en_revision";
  const esSalon = p.tipo === "salon_eventos";

  function aplicar(resultado: Resultado) {
    if ("publicacion" in resultado) {
      setP(resultado.publicacion);
      setAviso(null);
      setGuardado(true);
      setTimeout(() => setGuardado(false), 2200);
    } else {
      setAviso({ mensaje: resultado.error, faltantes: resultado.faltantes });
    }
  }

  const correr = (accion: () => Promise<Resultado>) =>
    empezar(async () => aplicar(await accion()));

  function guardar(datos: FormData) {
    const valor = (k: string) => String(datos.get(k) ?? "").trim();
    correr(() =>
      accionGuardarDatos(p.id, {
        titulo: valor("titulo"),
        descripcion: valor("descripcion"),
        reglas_casa: valor("reglas_casa") || null,
        subtipo_servicio_id: valor("subtipo_servicio_id") || null,
        politica_cancelacion_id: valor("politica_cancelacion_id") || null,
        direccion: valor("direccion") || null,
        confirmacion_inmediata: datos.get("confirmacion_inmediata") === "on",
        // Un salón no tiene ingreso y salida: sus horarios son los turnos.
        ...(esSalon
          ? { porcentaje_sena: Number(valor("porcentaje_sena") || 0) }
          : {
              hora_ingreso: valor("hora_ingreso") || null,
              hora_salida: valor("hora_salida") || null,
            }),
      }),
    );
  }

  function alternarComodidad(codigo: string) {
    const siguientes = p.comodidades.includes(codigo)
      ? p.comodidades.filter((c) => c !== codigo)
      : [...p.comodidades, codigo];
    correr(() => accionGuardarDatos(p.id, { comodidades: siguientes }));
  }

  function moverFoto(indice: number, paso: number) {
    const orden = p.fotos.map((f) => f.id);
    const destino = indice + paso;
    if (destino < 0 || destino >= orden.length) return;
    [orden[indice], orden[destino]] = [orden[destino], orden[indice]];
    correr(() => accionReordenarFotos(p.id, orden));
  }

  return (
    <div className={estilos.editor}>
      <header className={estilos.cabecera}>
        <div>
          <Link href="/mis-publicaciones" className={estilos.volver}>
            <ChevronIzq /> Mis publicaciones
          </Link>
          <h1>{p.titulo}</h1>
          <p className={estilos.lugar}>
            {p.localidad} · {p.provincia}
          </p>
        </div>
        <div className={estilos.acciones}>
          <Estado estado={p.estado} />
          {p.estado === "borrador" && (
            <button
              type="button"
              className={estilos.principal}
              disabled={pendiente || p.faltantes.length > 0 || !puedePublicar}
              onClick={() =>
                correr(() => accionCambiarEstado(p.id, "enviar-a-revision"))
              }
            >
              Mandar a revisión
            </button>
          )}
          {p.estado === "aprobada" && (
            <>
              {/* La ficha pública de los salones llega con la etapa 4 (docs/04). */}
              {!esSalon && (
                <Link
                  href={`/alojamiento/${p.slug}`}
                  className={estilos.secundario}
                >
                  Ver publicada
                </Link>
              )}
              <button
                type="button"
                className={estilos.secundario}
                disabled={pendiente}
                onClick={() =>
                  correr(() => accionCambiarEstado(p.id, "pausar"))
                }
              >
                Pausar
              </button>
            </>
          )}
          {p.estado === "pausada" && (
            <button
              type="button"
              className={estilos.principal}
              disabled={pendiente}
              onClick={() =>
                correr(() => accionCambiarEstado(p.id, "reactivar"))
              }
            >
              Reactivar
            </button>
          )}
          {p.estado === "rechazada" && (
            <button
              type="button"
              className={estilos.principal}
              disabled={pendiente}
              onClick={() =>
                correr(() => accionCambiarEstado(p.id, "volver-a-borrador"))
              }
            >
              Volver a editarla
            </button>
          )}
        </div>
      </header>

      <p className={estilos.explicaEstado}>{TEXTOS_ESTADO[p.estado].explica}</p>

      {p.motivo_rechazo && (
        <p className={estilos.rechazo}>
          <Alerta className={estilos.iconoChico} />
          <span>
            <strong>Qué hay que corregir:</strong> {p.motivo_rechazo}
          </span>
        </p>
      )}

      {aviso && (
        <div className={estilos.error} role="alert">
          <p>{aviso.mensaje}</p>
          {aviso.faltantes && (
            <ul>
              {aviso.faltantes.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {p.faltantes.length > 0 && p.estado !== "en_revision" && (
        <section className={estilos.faltantes}>
          <h2>
            {p.faltantes.length === 1
              ? "Falta una cosa antes de mandarla"
              : `Faltan ${p.faltantes.length} cosas antes de mandarla`}
          </h2>
          <ul>
            {p.faltantes.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          {!puedePublicar && (
            <p className={estilos.notaMP}>
              Además falta vincular tu cuenta de Mercado Pago, desde{" "}
              <Link href="/cuenta">tu cuenta</Link>.
            </p>
          )}
        </section>
      )}

      {guardado && <p className={estilos.guardado}>Guardado</p>}

      <fieldset className={estilos.bloque} disabled={bloqueada}>
        <h2>{esSalon ? "Datos del salón" : "Datos del alojamiento"}</h2>
        <form action={guardar} className={estilos.formulario}>
          <label className={estilos.completo}>
            <span>Nombre</span>
            <input
              name="titulo"
              defaultValue={p.titulo}
              maxLength={150}
              required
            />
          </label>
          <label className={estilos.completo}>
            <span>Descripción</span>
            <textarea
              name="descripcion"
              defaultValue={p.descripcion}
              rows={5}
              placeholder={
                esSalon
                  ? "Contá cómo es el lugar, para qué eventos sirve y qué incluye el alquiler."
                  : "Contá qué tiene, cómo es el entorno y a qué distancia está de lo que la gente busca."
              }
            />
          </label>
          <label>
            <span>{esSalon ? "Tipo de espacio" : "Tipo"}</span>
            <select
              name="subtipo_servicio_id"
              defaultValue={p.subtipo_servicio_id ?? ""}
            >
              <option value="">Sin elegir</option>
              {catalogo.subtipos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Política de cancelación</span>
            <select
              name="politica_cancelacion_id"
              defaultValue={p.politica_cancelacion_id ?? ""}
            >
              <option value="">Sin elegir</option>
              {catalogo.politicas.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.nombre}
                </option>
              ))}
            </select>
          </label>
          {esSalon ? (
            <label>
              <span>Seña para reservar (%)</span>
              <input
                type="number"
                name="porcentaje_sena"
                min={0}
                max={100}
                defaultValue={p.porcentaje_sena ?? ""}
                placeholder="Ej.: 30"
              />
              <small>
                Se paga online al reservar; el resto lo arreglás vos. Vacío: se
                paga todo.
              </small>
            </label>
          ) : (
            <>
              <label>
                <span>Ingreso desde</span>
                <input
                  type="time"
                  name="hora_ingreso"
                  defaultValue={p.hora_ingreso ?? ""}
                />
              </label>
              <label>
                <span>Salida hasta</span>
                <input
                  type="time"
                  name="hora_salida"
                  defaultValue={p.hora_salida ?? ""}
                />
              </label>
            </>
          )}
          <label className={estilos.completo}>
            <span>{esSalon ? "Reglas del lugar" : "Reglas de la casa"}</span>
            <textarea
              name="reglas_casa"
              defaultValue={p.reglas_casa ?? ""}
              rows={2}
              placeholder={
                esSalon
                  ? "Música hasta las 4, se permite catering propio, sin pirotecnia…"
                  : undefined
              }
            />
          </label>
          <label className={estilos.completo}>
            <span>Dirección</span>
            <input
              name="direccion"
              defaultValue={p.direccion ?? ""}
              maxLength={200}
            />
            <small>No se muestra hasta que la reserva esté confirmada.</small>
          </label>
          <label className={`${estilos.completo} ${estilos.casilla}`}>
            <input
              type="checkbox"
              name="confirmacion_inmediata"
              defaultChecked={p.confirmacion_inmediata}
            />
            <span>
              Confirmación inmediata
              <small>
                Si lo desactivás, tenés un plazo para aceptar o rechazar cada
                pedido.
              </small>
            </span>
          </label>
          <button
            type="submit"
            className={estilos.guardar}
            disabled={pendiente}
          >
            Guardar datos
          </button>
        </form>
      </fieldset>

      <fieldset className={estilos.bloque} disabled={bloqueada}>
        <h2>Dónde queda</h2>
        <MapaSelector
          lat={p.lat}
          lon={p.lon}
          onMover={(lat, lon) =>
            correr(() => accionGuardarDatos(p.id, { lat, lon }))
          }
        />
      </fieldset>

      <fieldset className={estilos.bloque} disabled={bloqueada}>
        <h2>Qué incluye</h2>
        <ul className={estilos.comodidades}>
          {catalogo.comodidades.map((c) => {
            const Icono = ICONOS_COMODIDAD[c.codigo];
            const activa = p.comodidades.includes(c.codigo);
            return (
              <li key={c.codigo}>
                <button
                  type="button"
                  className={`${estilos.chip} ${activa ? estilos.chipActivo : ""}`}
                  aria-pressed={activa}
                  disabled={pendiente}
                  onClick={() => alternarComodidad(c.codigo)}
                >
                  {Icono && <Icono className={estilos.iconoChip} />}
                  {c.nombre}
                </button>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <fieldset className={estilos.bloque} disabled={bloqueada}>
        <h2>
          Fotos <span className="cifra">{p.fotos.length}</span>
        </h2>
        <p className={estilos.ayuda}>
          Hacen falta al menos 5. La primera es la que se ve en los resultados.
          Se achican y optimizan solas al subirlas.
        </p>
        <ul className={estilos.fotos}>
          {p.fotos.map((f, i) => (
            <li key={f.id}>
              <img src={f.url} alt="" loading="lazy" />
              {i === 0 && (
                <span className={estilos.principalFoto}>Principal</span>
              )}
              <div className={estilos.controlesFoto}>
                <button
                  type="button"
                  onClick={() => moverFoto(i, -1)}
                  disabled={i === 0 || pendiente}
                  aria-label="Mover antes"
                >
                  <ChevronIzq />
                </button>
                <button
                  type="button"
                  onClick={() => moverFoto(i, 1)}
                  disabled={i === p.fotos.length - 1 || pendiente}
                  aria-label="Mover después"
                >
                  <ChevronDer />
                </button>
                <button
                  type="button"
                  onClick={() => correr(() => accionBorrarFoto(p.id, f.id))}
                  disabled={pendiente}
                  aria-label="Borrar foto"
                >
                  <Cruz />
                </button>
              </div>
            </li>
          ))}
          <li className={estilos.subir}>
            <input
              ref={archivo}
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                const elegidas = Array.from(e.target.files ?? []);
                e.target.value = "";
                empezar(async () => {
                  for (const f of elegidas) {
                    const datos = new FormData();
                    datos.append("archivo", f);
                    aplicar(await accionSubirFoto(p.id, datos));
                  }
                });
              }}
            />
            <span>{pendiente ? "Subiendo…" : "Agregar fotos"}</span>
          </li>
        </ul>
      </fieldset>

      {esSalon && (
        <fieldset className={estilos.bloque} disabled={bloqueada}>
          <UnidadesSalon p={p} correr={correr} pendiente={pendiente} />
        </fieldset>
      )}

      {!esSalon && (
        <fieldset className={estilos.bloque} disabled={bloqueada}>
          <h2>Unidades</h2>
          <p className={estilos.ayuda}>
            Cada unidad es lo que alguien reserva: una cabaña, un departamento,
            una habitación. Cada una lleva su capacidad y su tarifa.
          </p>

          <ul className={estilos.unidades}>
            {p.unidades.map((u) => (
              <li key={u.id} className={estilos.unidad}>
                <div className={estilos.unidadCabecera}>
                  <div>
                    <strong>{u.nombre}</strong>
                    <span className={estilos.unidadDetalle}>
                      hasta {plural(u.capacidad, "persona", "personas")}
                      {u.capacidad_base
                        ? ` · ${u.capacidad_base} sin cargo extra`
                        : ""}
                    </span>
                  </div>
                  <button
                    type="button"
                    className={estilos.borrar}
                    disabled={pendiente}
                    onClick={() => correr(() => accionBorrarUnidad(p.id, u.id))}
                  >
                    Quitar
                  </button>
                </div>

                <ul className={estilos.tarifas}>
                  {u.tarifas.map((t) => (
                    <li key={t.id}>
                      <span>
                        <strong>{t.nombre}</strong>
                        {t.fecha_desde && (
                          <span className={estilos.periodo}>
                            {t.fecha_desde} al {t.fecha_hasta}
                          </span>
                        )}
                        {t.estadia_minima > 1 && (
                          <span className={estilos.periodo}>
                            mínimo {t.estadia_minima} noches
                          </span>
                        )}
                        {t.estadia_maxima && (
                          <span className={estilos.periodo}>
                            máximo {t.estadia_maxima} noches
                          </span>
                        )}
                      </span>
                      <span className={`${estilos.precio} cifra`}>
                        {pesos(t.precio_noche)}
                      </span>
                      <button
                        type="button"
                        className={estilos.borrar}
                        disabled={pendiente}
                        onClick={() =>
                          correr(() => accionBorrarTarifa(p.id, u.id, t.id))
                        }
                        aria-label={`Borrar tarifa ${t.nombre}`}
                      >
                        <Cruz />
                      </button>
                    </li>
                  ))}
                  {u.tarifas.length === 0 && (
                    <li className={estilos.sinTarifa}>
                      Sin tarifa: así no se puede publicar ni calcular un
                      precio.
                    </li>
                  )}
                </ul>

                <form
                  className={estilos.filaForm}
                  action={(datos) => {
                    const v = (k: string) => String(datos.get(k) ?? "").trim();
                    correr(() =>
                      accionCrearTarifa(p.id, u.id, {
                        nombre: v("nombre") || "Tarifa",
                        precio_noche: v("precio_noche"),
                        fecha_desde: v("fecha_desde") || null,
                        fecha_hasta: v("fecha_hasta") || null,
                        estadia_minima: Number(v("estadia_minima") || 1),
                        estadia_maxima: v("estadia_maxima")
                          ? Number(v("estadia_maxima"))
                          : null,
                      }),
                    );
                  }}
                >
                  <input
                    name="nombre"
                    placeholder="Nombre (Base, Verano…)"
                    required
                  />
                  {/* step="any": con min=1 y step=100 el navegador rechaza 52000
                    por no caer en la grilla de pasos, y bloquea el envío sin avisar. */}
                  <input
                    name="precio_noche"
                    type="number"
                    min={1}
                    step="any"
                    placeholder="Precio por noche"
                    required
                  />
                  <input
                    name="fecha_desde"
                    type="date"
                    aria-label="Desde (temporada)"
                  />
                  <input
                    name="fecha_hasta"
                    type="date"
                    aria-label="Hasta (temporada)"
                  />
                  <input
                    name="estadia_minima"
                    type="number"
                    min={1}
                    className={estilos.noches}
                    placeholder="Mín. noches"
                    aria-label="Noches mínimas (opcional, 1 si queda vacío)"
                  />
                  {/* Vacío = sin máximo propio: rige el de la plataforma (365). */}
                  <input
                    name="estadia_maxima"
                    type="number"
                    min={1}
                    max={365}
                    className={estilos.noches}
                    placeholder="Máx. noches"
                    aria-label="Noches máximas (opcional)"
                  />
                  <button type="submit" disabled={pendiente}>
                    Agregar tarifa
                  </button>
                </form>

                <details className={estilos.agenda}>
                  <summary>Calendario y sincronización</summary>
                  <CalendarioUnidad
                    publicacionId={p.id}
                    unidadId={u.id}
                    bloqueado={bloqueada}
                  />
                </details>
              </li>
            ))}
          </ul>

          <form
            className={estilos.filaForm}
            action={(datos) => {
              const v = (k: string) => String(datos.get(k) ?? "").trim();
              correr(() =>
                accionCrearUnidad(p.id, {
                  nombre: v("nombre"),
                  capacidad: Number(v("capacidad")),
                  capacidad_base: v("capacidad_base")
                    ? Number(v("capacidad_base"))
                    : null,
                  cargo_limpieza: v("cargo_limpieza") || "0",
                }),
              );
            }}
          >
            <input
              name="nombre"
              placeholder="Nombre de la unidad"
              required
              maxLength={120}
            />
            <input
              name="capacidad"
              type="number"
              min={1}
              max={30}
              placeholder="Capacidad"
              required
            />
            <input
              name="capacidad_base"
              type="number"
              min={1}
              max={30}
              placeholder="Sin cargo extra"
            />
            <input
              name="cargo_limpieza"
              type="number"
              min={0}
              step="any"
              placeholder="Limpieza"
            />
            <button type="submit" disabled={pendiente}>
              Agregar unidad
            </button>
          </form>
        </fieldset>
      )}
    </div>
  );
}
