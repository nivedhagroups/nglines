import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, customers, dashboard, expenses, governance, profile, sales, settings as settings_api
from app.core.config import settings
from app.core.errors import install_error_handlers


app = FastAPI(
    title="Nivedha Groups API",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Business-ID", "Idempotency-Key", "If-Match"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


install_error_handlers(app)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(sales.router, prefix="/api/v1")
app.include_router(expenses.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(settings_api.router, prefix="/api/v1")
app.include_router(governance.router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
async def liveness() -> dict:
    return {"status": "ok"}