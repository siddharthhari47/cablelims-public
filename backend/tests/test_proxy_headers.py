"""
B4 (Review #2 remediation): with Caddy reverse-proxying every request to
uvicorn over loopback, request.client.host would otherwise report Caddy's
own address (127.0.0.1) for every device on the lab network -- silently
collapsing C5's per-(username, ip) login-throttle bucketing and making
every AuditEvent's IP field meaningless. start_cablelims.bat now passes
uvicorn `--proxy-headers --forwarded-allow-ips=127.0.0.1`, which makes
uvicorn trust an X-Forwarded-For header from a loopback-connecting peer
(Caddy) and substitute it for request.client.host -- exactly what Caddy's
reverse_proxy directive sends by default.

TestClient can't exercise this directly (it talks to the FastAPI app via
httpx's ASGITransport, never through uvicorn's own CLI/Config wrapping, so
`--proxy-headers` itself is never in the loop). This tests the exact ASGI
middleware that flag installs -- uvicorn.middleware.proxy_headers.
ProxyHeadersMiddleware -- directly, with explicit control over the
simulated peer address (which TestClient itself doesn't expose), proving
both halves of the trust boundary: a loopback-connecting proxy's forwarded
header IS honoured, and a non-loopback peer's forwarded header is NOT
(so a device on the LAN can't spoof its own IP by just sending the header
itself).
"""
import anyio
import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# This project has no other async tests / no pytest-asyncio or pytest-anyio
# plugin configured -- rather than add that just for this one file,
# anyio.run() drives the async httpx call from an ordinary sync test
# function, matching every other test in this suite.


async def _whoami(request):
    return JSONResponse({"client_host": request.client.host if request.client else None})


def _wrapped_app():
    # trusted_hosts="127.0.0.1" matches start_cablelims.bat's
    # --forwarded-allow-ips=127.0.0.1 exactly.
    inner = Starlette(routes=[Route("/whoami", _whoami)])
    return ProxyHeadersMiddleware(inner, trusted_hosts="127.0.0.1")


def test_forwarded_for_is_honoured_from_a_loopback_peer():
    # Simulates Caddy: the immediate TCP peer is 127.0.0.1 (Caddy running
    # on the same machine), carrying the real device's address in
    # X-Forwarded-For, exactly what Caddy's reverse_proxy sends.
    async def _run():
        transport = httpx.ASGITransport(app=_wrapped_app(), client=("127.0.0.1", 54321))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/whoami", headers={"X-Forwarded-For": "192.168.1.42"})

    resp = anyio.run(_run)
    assert resp.json()["client_host"] == "192.168.1.42"


def test_forwarded_for_is_ignored_from_a_non_loopback_peer():
    # A request that did NOT come through Caddy (peer is some other LAN
    # address, not 127.0.0.1) must not have its claimed X-Forwarded-For
    # honoured -- otherwise any device could just set that header itself
    # and spoof a different source IP for login-throttle/audit purposes.
    async def _run():
        transport = httpx.ASGITransport(app=_wrapped_app(), client=("192.168.1.99", 54321))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/whoami", headers={"X-Forwarded-For": "10.0.0.1"})

    resp = anyio.run(_run)
    assert resp.json()["client_host"] == "192.168.1.99"
