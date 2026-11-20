import type { Metadata } from "next";
import { Archivo } from "next/font/google";

import PieDePagina from "@/componentes/PieDePagina";

import "./globals.css";

// Archivo (Omnibus-Type, Buenos Aires): grotesca de trabajo con cifras tabulares
// parejas, que es lo que una página de precios necesita.
const archivo = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--fuente",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Alojamientos en Argentina",
  description:
    "Buscá y reservá cabañas, casas y departamentos en todo el país, directo con quien te recibe.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-AR" className={archivo.variable}>
      <body>
        <a className="saltar" href="#resultados">
          Saltar a los resultados
        </a>
        {children}
        <PieDePagina />
      </body>
    </html>
  );
}
