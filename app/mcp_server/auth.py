import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Static Bearer-token gate for MCP paths. Constant-time comparison.

    Wraps the MCP ASGI app (mounted at root, serving /mcp): non-/mcp paths pass
    through unauthenticated so the inner app can 404 them normally.
    """

    def __init__(self, app: ASGIApp, token: str, path_prefix: str = "/mcp") -> None:
        self._app = app
        self._expected = f"Bearer {token}"
        self._path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._path_prefix):
            await self._app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        provided = headers.get(b"authorization", b"").decode("latin-1")
        if not secrets.compare_digest(provided, self._expected):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "message": "Send 'Authorization: Bearer <MCP_API_KEY>'.",
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
