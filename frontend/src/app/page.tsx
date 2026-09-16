import styles from "./page.module.css";

export default function Inicio() {
  return (
    <main>
      <section className={styles.hero}>
        <h1 className={styles.titulo}>Encontrá dónde quedarte, reservá con quien te recibe.</h1>
        <form className={styles.buscador} action="/buscar" method="get">
          <label className={styles.campo}>
            Destino
            <input name="destino" placeholder="Provincia o localidad" required />
          </label>
          <label className={styles.campo}>
            Llegada
            <input name="desde" type="date" required />
          </label>
          <label className={styles.campo}>
            Salida
            <input name="hasta" type="date" required />
          </label>
          <label className={styles.campo}>
            Personas
            <input name="personas" type="number" min={1} defaultValue={2} />
          </label>
          <button className={styles.boton} type="submit">
            Buscar alojamiento
          </button>
        </form>
      </section>
    </main>
  );
}
