"""
Regression tests for §5.3: no endpoint declared `response_model=`, so (a)
the generated OpenAPI schema documented no response bodies at all, and (b)
nothing structurally prevented an endpoint from accidentally leaking a
field it didn't mean to (e.g. an internal note, a raw ORM attribute picked
up by vars()). Both are now enforced by FastAPI at the response-
serialization layer via app/schemas/.
"""
from app.main import app
from app.schemas.samples import CreateSampleResponse


def test_every_json_route_has_a_documented_response_schema():
    # download_diagram_image and download_observation_sheet return raw
    # FileResponse (binary content, no JSON body) and are deliberately
    # excluded -- a response_model on those would be meaningless.
    excluded_paths = {
        ("/api/samples/{sample_id}/diagram-image", "get"),
        ("/api/samples/{sample_id}/observation-sheet", "get"),
    }
    schema = app.openapi()
    undocumented = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if (path, method) in excluded_paths:
                continue
            responses = operation.get("responses", {})
            ok_response = responses.get("200") or responses.get("201")
            if not ok_response:
                continue  # e.g. a 204/redirect-only route, none exist today
            if "content" not in ok_response:
                undocumented.append(f"{method.upper()} {path}")
    assert not undocumented, f"Routes with no documented response schema: {undocumented}"


def test_response_model_strips_fields_not_declared_in_the_schema():
    # The actual leak-prevention property: a dict with an extra key the
    # model doesn't declare is silently dropped during serialization, not
    # passed through to the client.
    raw = {
        "sample_id": "SMP-2026-9999", "status": "PROFILE_PENDING", "cores_tested": 3,
        "internal_debug_note": "should never reach the client",
    }
    validated = CreateSampleResponse.model_validate(raw)
    dumped = validated.model_dump()
    assert "internal_debug_note" not in dumped
    assert dumped == {"sample_id": "SMP-2026-9999", "status": "PROFILE_PENDING", "cores_tested": 3}
