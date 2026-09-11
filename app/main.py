from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.routers import analytics, employees, violation_types, violations


def create_app() -> FastAPI:
    app = FastAPI(title="Violation Tracker API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(employees.router)
    app.include_router(violation_types.router)
    app.include_router(violations.router)
    app.include_router(analytics.router)

    return app


app = create_app()
