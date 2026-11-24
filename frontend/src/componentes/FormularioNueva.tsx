"use client";

import { useActionState, useState } from "react";

import { accionCrearPublicacion } from "@/lib/acciones-publicaciones";
import type { CatalogoAlta, TipoServicioCodigo } from "@/lib/api";
import { Alerta } from "./Iconos";
import estilos from "./FormularioAuth.module.css";
import propios from "./FormularioNueva.module.css";

const TIPOS: { codigo: TipoServicioCodigo; nombre: string; detalle: string }[] =
  [
    {
      codigo: "alojamiento",
      nombre: "Alojamiento",
      detalle: "Cabañas, casas, departamentos. Se reserva por noche.",
    },
    {
      codigo: "salon_eventos",
      nombre: "Salón de eventos",
      detalle:
        "Salón, quincho o espacio al aire libre. Se reserva por turno o por horas.",
    },
    {
      codigo: "excursion",
      nombre: "Excursión o actividad",
      detalle:
        "Cabalgatas, trekking, visitas a bodegas. Se reserva por salida y cantidad de personas.",
    },
    {
      codigo: "traslado",
      nombre: "Traslados",
      detalle:
        "Aeropuerto, terminal, entre localidades. Se reserva el vehículo entero, con chofer, por viaje.",
    },
  ];

export default function FormularioNueva({
  catalogos,
  tipoInicial = "alojamiento",
}: {
  catalogos: Record<TipoServicioCodigo, CatalogoAlta>;
  tipoInicial?: TipoServicioCodigo;
}) {
  const [estado, ejecutar, pendiente] = useActionState(
    accionCrearPublicacion,
    {} as {
      error?: string;
    },
  );
  const [tipo, setTipo] = useState<TipoServicioCodigo>(tipoInicial);
  const catalogo = catalogos[tipo];
  const esSalon = tipo === "salon_eventos";
  const esExcursion = tipo === "excursion";
  const esTraslado = tipo === "traslado";

  return (
    <form action={ejecutar} className={estilos.formulario}>
      {estado?.error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {estado.error}
        </p>
      )}

      <fieldset className={propios.tipos}>
        <legend>Qué vas a publicar</legend>
        {TIPOS.map((t) => (
          <label key={t.codigo} className={propios.tipo}>
            <input
              type="radio"
              name="tipo"
              value={t.codigo}
              checked={tipo === t.codigo}
              onChange={() => setTipo(t.codigo)}
            />
            <span>
              <strong>{t.nombre}</strong>
              <small>{t.detalle}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <div className={estilos.campos}>
        <label className={estilos.completo}>
          <span>
            {esSalon
              ? "Nombre del salón"
              : esExcursion
                ? "Nombre de la excursión"
                : esTraslado
                  ? "Nombre de tu servicio de traslados"
                  : "Nombre del alojamiento"}
          </span>
          <input
            name="titulo"
            required
            maxLength={150}
            placeholder={
              esSalon
                ? "Quincho Los Algarrobos"
                : esExcursion
                  ? "Cabalgata al Dique"
                  : esTraslado
                    ? "Traslados del Valle"
                    : "Cabañas del Arroyo"
            }
          />
        </label>

        <label className={estilos.medio}>
          <span>Localidad</span>
          <select name="localidad_id" required defaultValue="">
            <option value="" disabled>
              Elegí una…
            </option>
            {catalogo.localidades.map((l) => (
              <option key={l.id} value={l.id}>
                {l.nombre} · {l.provincia}
              </option>
            ))}
          </select>
        </label>

        {/* key: al cambiar de tipo, el subtipo elegido del otro tipo no puede quedar. */}
        <label className={estilos.medio} key={tipo}>
          <span>
            {esSalon
              ? "Tipo de espacio"
              : esExcursion
                ? "Tipo de actividad"
                : esTraslado
                  ? "Tipo de traslado"
                  : "Tipo"}
          </span>
          <select name="subtipo_servicio_id" defaultValue="">
            <option value="">Elegir después</option>
            {catalogo.subtipos.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nombre}
              </option>
            ))}
          </select>
        </label>
      </div>

      <button type="submit" className={estilos.enviar} disabled={pendiente}>
        {pendiente ? "Creando…" : "Crear borrador"}
      </button>
    </form>
  );
}
