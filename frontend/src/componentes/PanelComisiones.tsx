"use client";

/* Reglas de comisión del operador (docs/00 §7.4): la lista, el alta y edición
   (con historial) y el simulador. Qué regla gana y cuánto se cobra lo decide el
   backend; acá solo se cargan datos y se muestra lo que responde. */

import { Fragment, useEffect, useState, useTransition } from "react";

import {
  accionEstadoRegla,
  accionGuardarRegla,
  accionHistorialRegla,
  accionSimular,
} from "@/lib/acciones-comisiones";
import type {
  CatalogoComisiones,
  HistorialRegla,
  QuienPaga,
  ReglaComisionIn,
  ReglaComisionOp,
  SimulacionComision,
} from "@/lib/api";
import { diaMesAnio, hoyISO, pesos, pesosExactos } from "@/lib/formato";
import estilos from "./PanelComisiones.module.css";

const QUIEN: Record<QuienPaga, string> = {
  prestador: "la paga el prestador",
  viajero: "la paga el viajero (cargo de servicio)",
  dividido: "dividida",
};

const num = (v: string | null) => (v == null ? 0 : Number(v));

function valor(r: ReglaComisionOp): string {
  const partes: string[] = [];
  if (num(r.porcentaje)) partes.push(`${num(r.porcentaje).toLocaleString("es-AR")} %`);
  if (num(r.monto_fijo)) partes.push(pesos(r.monto_fijo));
  let texto = partes.join(" + ") || "Sin comisión";
  if (r.minimo) texto += `, mín. ${pesos(r.minimo)}`;
  if (r.maximo) texto += `, máx. ${pesos(r.maximo)}`;
  return texto;
}

function quien(r: ReglaComisionOp): string {
  return r.quien_paga === "dividido"
    ? `el viajero paga el ${num(r.porcentaje_viajero)} %`
    : QUIEN[r.quien_paga];
}

function alcance(r: ReglaComisionOp): string {
  if (r.es_default) return "Todo lo que no tenga una regla más específica";
  const partes = [
    r.subtipo_servicio ? `${r.tipo_servicio ?? ""} · ${r.subtipo_servicio}` : r.tipo_servicio,
    r.localidad ? `${r.localidad}${r.provincia ? `, ${r.provincia}` : ""}` : r.provincia,
    r.servicio_desde || r.servicio_hasta
      ? `temporada ${r.servicio_desde ? diaMesAnio(r.servicio_desde) : "…"} al ${r.servicio_hasta ? diaMesAnio(r.servicio_hasta) : "…"}`
      : null,
  ].filter(Boolean);
  return partes.join(" · ") + (r.otras_condiciones ? " · y otras condiciones" : "");
}

/* --- Formulario --- */

function Formulario({
  regla,
  catalogo,
  listo,
  cancelar,
}: {
  regla: ReglaComisionOp | null; // null: nueva
  catalogo: CatalogoComisiones;
  listo: (r: ReglaComisionOp) => void;
  cancelar: () => void;
}) {
  const [tipo, setTipo] = useState(regla?.tipo_servicio_id ?? "");
  const [provincia, setProvincia] = useState(regla?.provincia_id ?? "");
  const [quienPaga, setQuienPaga] = useState<QuienPaga>(regla?.quien_paga ?? "prestador");
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();
  const general = regla?.es_default ?? false;
  const subtipos = catalogo.tipos.find((t) => t.id === tipo)?.subtipos ?? [];
  const localidades = catalogo.provincias.find((p) => p.id === provincia)?.localidades ?? [];

  function guardar(f: FormData) {
    const v = (k: string) => String(f.get(k) ?? "").trim();
    const o = (k: string) => v(k) || null;
    const datos: ReglaComisionIn = {
      nombre: v("nombre"),
      descripcion: o("descripcion"),
      prioridad: Number(v("prioridad") || 0),
      vigente_desde: o("vigente_desde"),
      vigente_hasta: o("vigente_hasta"),
      tipo_servicio_id: general ? null : o("tipo_servicio_id"),
      subtipo_servicio_id: general ? null : o("subtipo_servicio_id"),
      provincia_id: general ? null : o("provincia_id"),
      localidad_id: general ? null : o("localidad_id"),
      servicio_desde: general ? null : o("servicio_desde"),
      servicio_hasta: general ? null : o("servicio_hasta"),
      porcentaje: v("porcentaje") || "0",
      monto_fijo: v("monto_fijo") || "0",
      minimo: o("minimo"),
      maximo: o("maximo"),
      quien_paga: quienPaga,
      porcentaje_viajero: quienPaga === "dividido" ? v("porcentaje_viajero") || "0" : "0",
      iva_incluido: f.get("iva_incluido") === "on",
    };
    setError(null);
    empezar(async () => {
      try {
        const r = await accionGuardarRegla(regla?.id ?? null, datos);
        if ("error" in r) setError(r.error);
        else listo(r.ok);
      } catch {
        setError("Actualizamos el sitio mientras editabas. Recargá la página y probá de nuevo.");
      }
    });
  }

  const d = (k: keyof ReglaComisionOp) => (regla?.[k] as string | null | undefined) ?? "";

  return (
    <form action={guardar} className={estilos.formulario}>
      <h2>{regla ? `Editar «${regla.nombre}»` : "Nueva regla"}</h2>
      {regla && regla.reservas > 0 && (
        <p className={estilos.aviso}>
          Ya se usó en {regla.reservas} {regla.reservas === 1 ? "reserva" : "reservas"}: esas
          no cambian. El cambio vale para las reservas que se hagan desde ahora.
        </p>
      )}

      <fieldset>
        <legend>Qué es</legend>
        <label className={estilos.ancho}>
          <span>Nombre</span>
          <input name="nombre" defaultValue={d("nombre")} required minLength={3} maxLength={120}
                 placeholder="Excursiones, Traslados en Mendoza, Temporada alta…" />
        </label>
        <label className={estilos.ancho}>
          <span>Nota interna (opcional)</span>
          <input name="descripcion" defaultValue={d("descripcion")} maxLength={500} />
        </label>
      </fieldset>

      {general ? (
        <p className={estilos.aviso}>
          Es la regla general: aplica a todo lo que no tenga otra más específica. No lleva tipo,
          zona ni temporada.
        </p>
      ) : (
        <fieldset>
          <legend>A qué se aplica (al menos una)</legend>
          <label>
            <span>Tipo de servicio</span>
            <select name="tipo_servicio_id" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Cualquiera</option>
              {catalogo.tipos.map((t) => (
                <option key={t.id} value={t.id}>{t.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Subtipo</span>
            {/* key: al cambiar de tipo, el subtipo del otro no puede quedar elegido. */}
            <select name="subtipo_servicio_id" key={tipo} defaultValue={tipo === regla?.tipo_servicio_id ? d("subtipo_servicio_id") : ""}
                    disabled={!tipo}>
              <option value="">Cualquiera</option>
              {subtipos.map((s) => (
                <option key={s.id} value={s.id}>{s.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Provincia</span>
            <select name="provincia_id" value={provincia} onChange={(e) => setProvincia(e.target.value)}>
              <option value="">Cualquiera</option>
              {catalogo.provincias.map((p) => (
                <option key={p.id} value={p.id}>{p.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Localidad</span>
            <select name="localidad_id" key={provincia} defaultValue={provincia === regla?.provincia_id ? d("localidad_id") : ""}
                    disabled={!provincia}>
              <option value="">Cualquiera</option>
              {localidades.map((l) => (
                <option key={l.id} value={l.id}>{l.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Temporada: servicio desde</span>
            <input type="date" name="servicio_desde" defaultValue={d("servicio_desde")} />
          </label>
          <label>
            <span>hasta</span>
            <input type="date" name="servicio_hasta" defaultValue={d("servicio_hasta")} />
          </label>
        </fieldset>
      )}

      <fieldset>
        <legend>Cuánto</legend>
        <label>
          <span>Porcentaje</span>
          <input type="number" name="porcentaje" min={0} max={100} step="any"
                 defaultValue={regla ? num(regla.porcentaje) : ""} placeholder="0" />
        </label>
        <label>
          <span>Monto fijo por reserva</span>
          <input type="number" name="monto_fijo" min={0} step="any"
                 defaultValue={regla && num(regla.monto_fijo) ? num(regla.monto_fijo) : ""} placeholder="0" />
        </label>
        <label>
          <span>Mínimo</span>
          <input type="number" name="minimo" min={0} step="any" defaultValue={d("minimo")} />
        </label>
        <label>
          <span>Máximo</span>
          <input type="number" name="maximo" min={0} step="any" defaultValue={d("maximo")} />
        </label>
        <label>
          <span>Quién la paga</span>
          <select value={quienPaga} onChange={(e) => setQuienPaga(e.target.value as QuienPaga)}>
            <option value="prestador">El prestador (se descuenta de su cobro)</option>
            <option value="viajero">El viajero (cargo de servicio)</option>
            <option value="dividido">Dividida</option>
          </select>
        </label>
        {quienPaga === "dividido" && (
          <label>
            <span>Parte del viajero (%)</span>
            <input type="number" name="porcentaje_viajero" min={1} max={99} step="any" required
                   defaultValue={regla && num(regla.porcentaje_viajero) ? num(regla.porcentaje_viajero) : ""} />
          </label>
        )}
        <label className={estilos.casilla}>
          <input type="checkbox" name="iva_incluido" defaultChecked={regla?.iva_incluido ?? false} />
          <span>El IVA ya está incluido en el porcentaje</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>Cuándo y desempate</legend>
        <label>
          <span>Vale para reservas hechas desde</span>
          <input type="date" name="vigente_desde" defaultValue={d("vigente_desde")} />
        </label>
        <label>
          <span>hasta</span>
          <input type="date" name="vigente_hasta" defaultValue={d("vigente_hasta")} />
        </label>
        <label>
          <span>Prioridad (si empata con otra)</span>
          <input type="number" name="prioridad" min={0} max={1000} defaultValue={regla?.prioridad ?? 0} />
        </label>
      </fieldset>

      {error && (
        <p className={estilos.error} role="alert">
          {error}
        </p>
      )}
      <div className={estilos.botones}>
        <button type="submit" className={estilos.principal} disabled={pendiente}>
          {pendiente ? "Guardando…" : "Guardar"}
        </button>
        <button type="button" className={estilos.secundario} onClick={cancelar} disabled={pendiente}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

/* --- Historial --- */

const ACCIONES = { alta: "Alta", edicion: "Cambio", baja: "Baja" } as const;

function cambios(h: HistorialRegla): string {
  if (!h.antes || !h.despues) return "";
  return Object.keys(h.despues)
    .filter((k) => String(h.antes![k] ?? "") !== String(h.despues![k] ?? ""))
    .map((k) => `${k}: ${h.antes![k] ?? "—"} → ${h.despues![k] ?? "—"}`)
    .join(" · ");
}

function Historial({ id }: { id: string }) {
  const [filas, setFilas] = useState<HistorialRegla[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let vigente = true;
    accionHistorialRegla(id).then((r) => {
      if (!vigente) return;
      if ("error" in r) setError(r.error);
      else setFilas(r.ok);
    });
    return () => {
      vigente = false;
    };
  }, [id]);
  if (error) return <p className={estilos.error}>{error}</p>;
  if (!filas) return <p className={estilos.nota}>Trayendo el historial…</p>;
  if (!filas.length) return <p className={estilos.nota}>Sin cambios registrados.</p>;
  return (
    <ol className={estilos.historial}>
      {filas.map((h) => (
        <li key={`${h.fecha}-${h.accion}`}>
          <strong>{ACCIONES[h.accion]}</strong> · {new Date(h.fecha).toLocaleString("es-AR")}
          {h.usuario ? ` · ${h.usuario}` : ""}
          {cambios(h) && <small>{cambios(h)}</small>}
        </li>
      ))}
    </ol>
  );
}

/* --- Simulador --- */

function Simulador({ catalogo }: { catalogo: CatalogoComisiones }) {
  const [tipo, setTipo] = useState("");
  const [provincia, setProvincia] = useState("");
  const [resultado, setResultado] = useState<SimulacionComision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();
  const subtipos = catalogo.tipos.find((t) => t.id === tipo)?.subtipos ?? [];
  const localidades = catalogo.provincias.find((p) => p.id === provincia)?.localidades ?? [];

  function simular(f: FormData) {
    const o = (k: string) => String(f.get(k) ?? "").trim() || null;
    setError(null);
    empezar(async () => {
      const r = await accionSimular({
        monto: o("monto") ?? "0",
        fecha_servicio: o("fecha_servicio") ?? hoyISO(),
        tipo_servicio_id: o("tipo_servicio_id"),
        subtipo_servicio_id: o("subtipo_servicio_id"),
        provincia_id: o("provincia_id"),
        localidad_id: o("localidad_id"),
      });
      if ("error" in r) setError(r.error);
      else setResultado(r.ok);
    });
  }

  return (
    <section className={estilos.simulador}>
      <h2>Simular una reserva</h2>
      <p className={estilos.nota}>
        Qué regla aplicaría y cuánto se cobraría. No reserva ni guarda nada.
      </p>
      <form action={simular} className={estilos.formulario}>
        <fieldset>
          <label>
            <span>Tipo</span>
            <select name="tipo_servicio_id" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Cualquiera</option>
              {catalogo.tipos.map((t) => (
                <option key={t.id} value={t.id}>{t.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Subtipo</span>
            <select name="subtipo_servicio_id" key={tipo} disabled={!tipo}>
              <option value="">—</option>
              {subtipos.map((s) => (
                <option key={s.id} value={s.id}>{s.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Provincia</span>
            <select name="provincia_id" value={provincia} onChange={(e) => setProvincia(e.target.value)}>
              <option value="">Cualquiera</option>
              {catalogo.provincias.map((p) => (
                <option key={p.id} value={p.id}>{p.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Localidad</span>
            <select name="localidad_id" key={provincia} disabled={!provincia}>
              <option value="">—</option>
              {localidades.map((l) => (
                <option key={l.id} value={l.id}>{l.nombre}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Monto del prestador</span>
            <input type="number" name="monto" min={0} step="any" required defaultValue={100000} />
          </label>
          <label>
            <span>Fecha del servicio</span>
            <input type="date" name="fecha_servicio" defaultValue={hoyISO(30)} />
          </label>
        </fieldset>
        <div className={estilos.botones}>
          <button type="submit" className={estilos.principal} disabled={pendiente}>
            {pendiente ? "Calculando…" : "Simular"}
          </button>
        </div>
      </form>
      {error && <p className={estilos.error} role="alert">{error}</p>}
      {resultado && (
        <div className={estilos.resultado}>
          <p>
            Aplica <strong>{resultado.regla_nombre}</strong>: comisión{" "}
            <strong className="cifra">{pesosExactos(resultado.comision_total)}</strong> (IVA{" "}
            {pesosExactos(resultado.iva)}). El viajero paga{" "}
            <span className="cifra">{pesosExactos(resultado.total_viajero)}</span>; al prestador
            le quedan <span className="cifra">{pesosExactos(resultado.neto_prestador)}</span>.
          </p>
          <details>
            <summary>Por qué</summary>
            <ul>
              {resultado.explicacion.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </section>
  );
}

/* --- Panel --- */

export default function PanelComisiones({
  inicial,
  catalogo,
}: {
  inicial: ReglaComisionOp[];
  catalogo: CatalogoComisiones;
}) {
  const [reglas, setReglas] = useState(inicial);
  const [editando, setEditando] = useState<ReglaComisionOp | "nueva" | null>(null);
  const [historial, setHistorial] = useState<string | null>(null);
  const [verInactivas, setVerInactivas] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  const poner = (r: ReglaComisionOp) =>
    setReglas((lista) =>
      lista.some((x) => x.id === r.id) ? lista.map((x) => (x.id === r.id ? r : x)) : [...lista, r],
    );

  function estado(r: ReglaComisionOp) {
    setError(null);
    empezar(async () => {
      const res = await accionEstadoRegla(r.id, !r.activa);
      if ("error" in res) setError(res.error);
      else poner(res.ok);
    });
  }

  const inactivas = reglas.filter((r) => !r.activa).length;
  const visibles = reglas.filter((r) => r.activa || verInactivas);

  return (
    <div className={estilos.panel}>
      {error && <p className={estilos.error} role="alert">{error}</p>}

      <div className={estilos.cabecera}>
        <button type="button" className={estilos.principal} onClick={() => setEditando("nueva")}
                disabled={editando !== null}>
          Nueva regla
        </button>
        {inactivas > 0 && (
          <label className={estilos.casilla}>
            <input type="checkbox" checked={verInactivas} onChange={(e) => setVerInactivas(e.target.checked)} />
            <span>Ver las desactivadas ({inactivas})</span>
          </label>
        )}
      </div>

      {editando === "nueva" && (
        <Formulario regla={null} catalogo={catalogo} cancelar={() => setEditando(null)}
                    listo={(r) => { poner(r); setEditando(null); }} />
      )}

      <ul className={estilos.lista}>
        {visibles.map((r) => (
          <Fragment key={r.id}>
            <li className={`${estilos.regla} ${!r.activa ? estilos.apagada : ""}`}>
              <div className={estilos.datos}>
                <strong>
                  {r.nombre}
                  {r.es_default && <span className={estilos.etiqueta}>General</span>}
                  {!r.activa && <span className={estilos.etiqueta}>Desactivada</span>}
                </strong>
                <span>{alcance(r)}</span>
                <span className={estilos.valor}>
                  <strong className="cifra">{valor(r)}</strong> · {quien(r)}
                  {r.iva_incluido ? " · IVA incluido" : " · más IVA"}
                </span>
                <small>
                  {r.vigente_desde || r.vigente_hasta
                    ? `Para reservas del ${r.vigente_desde ? diaMesAnio(r.vigente_desde) : "…"} al ${r.vigente_hasta ? diaMesAnio(r.vigente_hasta) : "…"} · `
                    : ""}
                  {r.prioridad ? `prioridad ${r.prioridad} · ` : ""}
                  usada en {r.reservas} {r.reservas === 1 ? "reserva" : "reservas"}
                </small>
              </div>
              <div className={estilos.acciones}>
                <button type="button" onClick={() => setEditando(r)} disabled={editando !== null || pendiente}>
                  Editar
                </button>
                {!r.es_default && (
                  <button type="button" onClick={() => estado(r)} disabled={pendiente}>
                    {r.activa ? "Desactivar" : "Activar"}
                  </button>
                )}
                <button type="button" aria-expanded={historial === r.id}
                        onClick={() => setHistorial(historial === r.id ? null : r.id)}>
                  Historial
                </button>
              </div>
              {historial === r.id && (
                <div className={estilos.ancho}>
                  <Historial id={r.id} />
                </div>
              )}
            </li>
            {editando !== null && editando !== "nueva" && editando.id === r.id && (
              <li>
                <Formulario regla={editando} catalogo={catalogo} cancelar={() => setEditando(null)}
                            listo={(x) => { poner(x); setEditando(null); }} />
              </li>
            )}
          </Fragment>
        ))}
      </ul>

      <Simulador catalogo={catalogo} />
    </div>
  );
}
