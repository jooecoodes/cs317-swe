import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.session import get_session


DbSession = Annotated[Session, Depends(get_session)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends()]


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("ADMIN_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin privileges required.")
