# Ingear API (FastAPI + PostgreSQL)

API REST para soportar el flujo de negocio de Ingear: **Clientes → Oportunidades → Proyectos → Cotizaciones → Despachos**, incluyendo **Productos** e **integraciones M:N** (proyecto–empleado, proyecto–cliente, proyecto–despacho).

---

## 🚀 Stack

- **FastAPI** (OpenAPI/Swagger)
- **SQLAlchemy 2.0**
- **PostgreSQL** (psycopg)
- **Pydantic v2** + **pydantic-settings**
- **Uvicorn**

Dependencias principales (`requirements.txt`):
- fastapi==0.115.6
- uvicorn[standard]==0.34.0
- SQLAlchemy==2.0.36
- psycopg[binary]==3.2.5
- pydantic==2.10.3
- pydantic-settings==2.6.1
- python-dotenv==1.0.1

---

## 📁 Estructura del proyecto

```txt
API_INGEAR/
├─ app/
│  ├─ main.py                 # Crea FastAPI, CORS y monta /api/v1
│  ├─ core/
│  │  └─ config.py            # Settings (.env)
│  ├─ db/
│  │  ├─ base.py              # DeclarativeBase
│  │  └─ session.py           # Engine + SessionLocal + get_db()
│  ├─ api/
│  │  └─ v1/
│  │     ├─ api.py            # Incluye routers por recurso
│  │     └─ endpoints/        # Endpoints REST (CRUD y relaciones)
│  ├─ models/                 # Modelos SQLAlchemy (tablas)
│  ├─ schemas/                # Schemas Pydantic (Create/Update/Out)
│  └─ crud/                   # CRUDBase + módulos por entidad
├─ requirements.txt
└─ .env
