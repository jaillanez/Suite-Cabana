const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Cliente único de la API. Toda regla de negocio vive en el backend. */
export async function api<T>(ruta: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${ruta}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const detalle = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detalle.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}
