import base64
import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BasicAuthMiddleware:
    """HTTP Basic gate for the management UI/API. Any username; shared password."""

    def __init__(self, app: ASGIApp, password: str, exempt_prefixes: tuple[str, ...]) -> None:
        self._app = app
        self._password = password
        self._exempt = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(self._exempt):
            await self._app(scope, receive, send)
            return
        provided = self._extract_password(scope)
        if provided is None or not secrets.compare_digest(provided, self._password):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="document-intelligence"'},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    def _extract_password(scope: Scope) -> str | None:
        header = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        if not header.startswith("Basic "):
            return None
        try:
            decoded = base64.b64decode(header[6:]).decode()
        except Exception:
            return None
        return decoded.split(":", 1)[1] if ":" in decoded else None
