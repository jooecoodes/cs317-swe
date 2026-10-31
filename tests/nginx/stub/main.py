"""Stub service for Tier-2 nginx tests. Switches role via ROLE env var."""
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ROLE = os.environ.get("ROLE", "app")
app = FastAPI()


if ROLE == "auth":
    # Mimics auth/main.py /verify but with fixed "valid" credentials.
    #   Cookie auth_session=good         -> session user  (X-User)
    #   Bearer device-good + POST /app3/ -> device token  (X-Device)
    @app.get("/verify")
    async def verify(request: Request):
        cookie = request.headers.get("cookie", "")
        authz = request.headers.get("authorization", "")
        method = request.headers.get("x-original-method", "").upper()
        uri = request.headers.get("x-original-uri", "")
        if "auth_session=good" in cookie:
            return JSONResponse({"ok": True}, headers={
                "X-User": "Test User",
                "X-Username": "testuser",
            })
        if authz == "Bearer device-good":
            if method == "POST" and uri.startswith("/app3/"):
                return JSONResponse({"ok": True}, headers={
                    "X-Device": "testuser:phone-1",
                })
            return JSONResponse({"error": "forbidden"}, status_code=401)
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    @app.post("/login")
    async def login():
        r = JSONResponse({"ok": True})
        r.set_cookie("auth_session", "good", path="/")
        return r

    @app.post("/device-login")
    async def device_login():
        return {"token": "device-good"}

else:
    @app.api_route("/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def echo(request: Request, path: str):
        return {
            "path": path,
            "method": request.method,
            "x_actor": request.headers.get("x-actor"),
            "x_device": request.headers.get("x-device"),
            "host": request.headers.get("host"),
        }
