import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Los Búhos · Cabañas y experiencias en Argentina",
  description: "Reservá cabañas, excursiones y más, directo con prestadores locales.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-AR">
      <body>{children}</body>
    </html>
  );
}
