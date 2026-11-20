"use client";

import { useActionState } from "react";

import { accionCrearPublicacion } from "@/lib/acciones-publicaciones";
import type { CatalogoAlta } from "@/lib/api";
import { Alerta } from "./Iconos";
import estilos from "./FormularioAuth.module.css";

export default function FormularioNueva({ catalogo }: { catalogo: CatalogoAlta }) {
  const [estado, ejecutar, pendiente] = useActionState(accionCrearPublicacion, {} as {
    error?: string;
  });

  return (
    <form action={ejecutar} className={estilos.formulario}>
      {estado?.error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {estado.error}
        </p>
      )}

      <div className={estilos.campos}>
        <label className={estilos.completo}>
          <span>Nombre del alojamiento</span>
          <input name="titulo" required maxLength={150} placeholder="Cabañas del Arroyo" />
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

        <label className={estilos.medio}>
          <span>Tipo</span>
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
