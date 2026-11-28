"use client";

/* "¿Ya lo publicás en Airbnb o Booking?": el prestador pega el texto de su anuncio
   y el backend propone descripción, reglas, horarios, comodidades y capacidad.
   No se guarda nada hasta que lo revisa y aplica; todo se puede corregir antes. */

import { useState, useTransition } from "react";

import {
  accionCrearUnidad,
  accionGuardarDatos,
  accionImportarAnuncio,
  type Resultado,
} from "@/lib/acciones-publicaciones";
import type { CatalogoAlta, PropuestaAnuncio, PublicacionEdicion } from "@/lib/api";
import { plural } from "@/lib/formato";
import estilos from "./EditorPublicacion.module.css";
import propios from "./ImportarAnuncio.module.css";

const hora = (h: string | null) => (h ? h.slice(0, 5) : "");

export default function ImportarAnuncio({
  p,
  catalogo,
  correr,
  pendiente,
}: {
  p: PublicacionEdicion;
  catalogo: CatalogoAlta;
  correr: (accion: () => Promise<Resultado>) => void;
  pendiente: boolean;
}) {
  const [texto, setTexto] = useState("");
  const [propuesta, setPropuesta] = useState<PropuestaAnuncio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leyendo, empezar] = useTransition();

  function leer() {
    setError(null);
    empezar(async () => {
      try {
        const r = await accionImportarAnuncio(p.id, texto);
        if ("error" in r) setError(r.error);
        else setPropuesta(r.propuesta);
      } catch {
        setError("Actualizamos el sitio mientras editabas. Recargá la página y probá de nuevo.");
      }
    });
  }

  const nombre = (codigo: string) =>
    catalogo.comodidades.find((c) => c.codigo === codigo)?.nombre ?? codigo;

  function aplicar(datos: FormData) {
    if (!propuesta) return;
    const usar = (k: string) => datos.get(`usar_${k}`) === "on";
    const v = (k: string) => String(datos.get(k) ?? "").trim();
    const cambios: Record<string, unknown> = {};
    if (usar("descripcion")) cambios.descripcion = v("descripcion");
    if (usar("reglas")) cambios.reglas_casa = v("reglas_casa") || null;
    if (usar("horarios")) {
      if (v("hora_ingreso")) cambios.hora_ingreso = v("hora_ingreso");
      if (v("hora_salida")) cambios.hora_salida = v("hora_salida");
    }
    if (usar("comodidades")) {
      // Se suman a las que ya tenía: lo que marcó a mano no se pierde.
      cambios.comodidades = [...new Set([...p.comodidades, ...propuesta.comodidades])];
    }
    const crearUnidad = usar("unidad") && v("unidad_nombre") && Number(v("unidad_capacidad")) > 0;
    correr(async () => {
      let r: Resultado = { publicacion: p };
      if (Object.keys(cambios).length) {
        r = await accionGuardarDatos(p.id, cambios);
        if ("error" in r) return r;
      }
      if (crearUnidad) {
        r = await accionCrearUnidad(p.id, {
          nombre: v("unidad_nombre"),
          capacidad: Number(v("unidad_capacidad")),
        });
      }
      if (!("error" in r)) {
        setPropuesta(null);
        setTexto("");
      }
      return r;
    });
  }

  const capacidad = propuesta
    ? [
        propuesta.huespedes && plural(propuesta.huespedes, "huésped", "huéspedes"),
        propuesta.dormitorios && plural(propuesta.dormitorios, "dormitorio", "dormitorios"),
        propuesta.camas && plural(propuesta.camas, "cama", "camas"),
        propuesta.banos && `${propuesta.banos} ${propuesta.banos === "1" ? "baño" : "baños"}`,
      ].filter(Boolean)
    : [];

  return (
    <details className={propios.importar}>
      <summary>¿Ya lo publicás en Airbnb o Booking? Traé los datos de ahí</summary>

      {!propuesta ? (
        <div className={propios.pegar}>
          <ol className={propios.pasos}>
            <li>Abrí tu anuncio en Airbnb o Booking, en la computadora.</li>
            <li>
              Seleccioná toda la página (<kbd>Ctrl</kbd>+<kbd>A</kbd>, o <kbd>⌘</kbd>+<kbd>A</kbd> en
              Mac) y copiala.
            </li>
            <li>Pegala acá abajo. Leemos la descripción, las reglas, los horarios y lo que ofrece.</li>
          </ol>
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={6}
            maxLength={30000}
            placeholder="Pegá acá el texto de tu anuncio"
            aria-label="Texto del anuncio"
          />
          {error && (
            <p className={estilos.sinTarifa} role="alert">
              {error}
            </p>
          )}
          <button
            type="button"
            className={estilos.principal}
            disabled={leyendo || texto.trim().length < 20}
            onClick={leer}
          >
            {leyendo ? "Leyendo…" : "Leer el anuncio"}
          </button>
          <p className={estilos.ayuda}>
            Las fotos no se pueden copiar así: descargalas de tu anuncio y subilas todas juntas
            en Fotos, más abajo. El calendario se conecta aparte, en cada unidad, para que no
            haya dobles reservas.
          </p>
        </div>
      ) : (
        <form action={aplicar} className={propios.propuesta}>
          <p className={estilos.ayuda}>
            Esto es lo que encontramos. Corregí lo que haga falta, destildá lo que no quieras y
            aplicalo. Nada se guarda hasta que tocás &quot;Aplicar&quot;.
          </p>

          {propuesta.descripcion && (
            <fieldset className={propios.parte}>
              <label className={propios.usar}>
                <input type="checkbox" name="usar_descripcion" defaultChecked />
                <strong>Descripción</strong>
                {p.descripcion && <small>reemplaza la que tenés</small>}
              </label>
              <textarea name="descripcion" defaultValue={propuesta.descripcion} rows={6} />
            </fieldset>
          )}

          {propuesta.reglas_casa && (
            <fieldset className={propios.parte}>
              <label className={propios.usar}>
                <input type="checkbox" name="usar_reglas" defaultChecked />
                <strong>Reglas de la casa</strong>
              </label>
              <textarea name="reglas_casa" defaultValue={propuesta.reglas_casa} rows={4} />
            </fieldset>
          )}

          {(propuesta.hora_ingreso || propuesta.hora_salida) && (
            <fieldset className={propios.parte}>
              <label className={propios.usar}>
                <input type="checkbox" name="usar_horarios" defaultChecked />
                <strong>Horarios</strong>
              </label>
              <div className={propios.horas}>
                <label>
                  <span>Ingreso desde</span>
                  <input type="time" name="hora_ingreso" defaultValue={hora(propuesta.hora_ingreso)} />
                </label>
                <label>
                  <span>Salida hasta</span>
                  <input type="time" name="hora_salida" defaultValue={hora(propuesta.hora_salida)} />
                </label>
              </div>
            </fieldset>
          )}

          {propuesta.comodidades.length > 0 && (
            <fieldset className={propios.parte}>
              <label className={propios.usar}>
                <input type="checkbox" name="usar_comodidades" defaultChecked />
                <strong>Sumar estas comodidades</strong>
              </label>
              <p className={propios.lista}>{propuesta.comodidades.map(nombre).join(" · ")}</p>
            </fieldset>
          )}

          {capacidad.length > 0 && (
            <fieldset className={propios.parte}>
              <p>
                <strong>Capacidad del anuncio:</strong> {capacidad.join(" · ")}
              </p>
              {p.unidades.length === 0 && propuesta.huespedes ? (
                <>
                  <label className={propios.usar}>
                    <input type="checkbox" name="usar_unidad" defaultChecked />
                    <strong>Crear la unidad</strong>
                    <small>después le cargás la tarifa</small>
                  </label>
                  <div className={propios.horas}>
                    <label>
                      <span>Nombre</span>
                      <input name="unidad_nombre" defaultValue="Cabaña" maxLength={120} />
                    </label>
                    <label>
                      <span>Personas</span>
                      <input
                        type="number"
                        name="unidad_capacidad"
                        min={1}
                        max={30}
                        defaultValue={Math.min(propuesta.huespedes, 30)}
                      />
                    </label>
                  </div>
                </>
              ) : (
                <p className={estilos.ayuda}>Revisá que coincida con tus unidades, más abajo.</p>
              )}
            </fieldset>
          )}

          <div className={propios.botones}>
            <button type="submit" className={estilos.principal} disabled={pendiente}>
              Aplicar
            </button>
            <button
              type="button"
              className={estilos.secundario}
              disabled={pendiente}
              onClick={() => setPropuesta(null)}
            >
              Descartar
            </button>
          </div>
        </form>
      )}
    </details>
  );
}
