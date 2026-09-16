# Suite Cabaña

Marketplace turístico (nombre de trabajo: Los Búhos). Alojamientos, excursiones, gastronomía y traslados con reserva, pago y comisión configurable.

Especificaciones en [`docs/`](docs/): visión general (00) y fases 1 a 3.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Base de datos | PostgreSQL 16 + PostGIS |
| Frontend | Next.js (App Router, TypeScript) |
| Pagos | Mercado Pago (modo marketplace) |

## Estructura

```
backend/    API FastAPI, modelos, motor de comisiones, migraciones
frontend/   Web Next.js
docs/       PRD por fase
```

## Arranque local

```bash
cp .env.example .env
docker compose up -d db redis

# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload        # http://localhost:8000/docs

# Frontend
cd ../frontend
npm install
npm run dev                          # http://localhost:3000
```

## Estado

Bloque 1 del plan de Fase 1 (docs/01 §8): base técnica, modelo de datos completo con migraciones, motor de comisiones con tests y endpoint de simulación (`POST /api/v1/comisiones/simular`).

Nuevas migraciones: `alembic revision --autogenerate -m "..."`.

## Tests

```bash
cd backend && pytest
```
