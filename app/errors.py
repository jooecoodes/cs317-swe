from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from queries import (
    DuplicateEmployeeCode,
    DuplicateViolationType,
    EmployeeNotFound,
    ViolationRecordNotFound,
    ViolationTypeInactive,
    ViolationTypeInUse,
    ViolationTypeNotFound,
)


ERROR_STATUS: dict[type[Exception], int] = {
    EmployeeNotFound: 404,
    ViolationTypeNotFound: 404,
    ViolationRecordNotFound: 404,
    DuplicateEmployeeCode: 409,
    DuplicateViolationType: 409,
    ViolationTypeInUse: 409,
    ViolationTypeInactive: 400,
}


def register_error_handlers(app: FastAPI) -> None:
    for exc_type, code in ERROR_STATUS.items():
        async def handler(request: Request, exc: Exception, code: int = code) -> JSONResponse:
            return JSONResponse(
                status_code=code,
                content={"detail": str(exc), "error": type(exc).__name__},
            )
        app.add_exception_handler(exc_type, handler)
