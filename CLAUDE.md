# Guía para agentes de código

Leé `docs/00-vision-general.md` antes de cualquier cambio de modelo o arquitectura. La fase en curso es la **Fase 1** (`docs/01-fase1-lanzamiento.md`); el orden de trabajo es el de su sección 8.

## Principios no negociables

1. **Modelo genérico de servicio.** Alojamiento es solo el primer `TipoServicio`. Nada de tablas o lógica "de cabañas" que impida excursiones, gastronomía o traslados (Fase 2).
2. **Reserva con ítems.** Toda reserva tiene `ItemReserva`, aunque en Fase 1 haya uno solo (Fase 3: paquetes).
3. **Toda la lógica de negocio en el backend.** Precios, comisiones, beneficios y disponibilidad se calculan en la API. El frontend (y la futura app) solo muestran.
4. **Comisión con snapshot.** Cada reserva guarda `ComisionAplicada` con la regla y los montos. Cambiar una regla nunca altera reservas existentes.
5. **Dinero en `Decimal`** (`Numeric(14, 2)` en BD). Nunca `float`.
6. **Cero dobles reservas.** Retención de fechas con vencimiento y control de concurrencia en BD (restricción de exclusión o bloqueo de fila).
7. **Webhooks idempotentes.** Las notificaciones de Mercado Pago se registran por id y se procesan una sola vez.

## Convenciones

- Código, tablas y endpoints en español; `snake_case` en Python y BD.
- API versionada en `/api/v1`.
- Esquema solo con migraciones Alembic; nunca `create_all` fuera de tests.
- Cada regla de negocio nueva lleva test en `backend/tests/`.
- `ruff check .` y `pytest` deben pasar antes de cada commit.

## Mapa del backend

```
app/core/        configuración, BD, seguridad
app/models/      modelos SQLAlchemy (docs/00 §6)
app/services/    lógica de negocio pura (comisiones.py = motor, docs/00 §7)
app/api/v1/      endpoints
```
