"""
Regression tests for SEC-6: marking/diagram image uploads had no size
limit, no content-type validation, no magic-byte check, no extension
allowlist, no re-encode, and no EXIF stripping -- the client-supplied
filename's extension was trusted verbatim (so a ".html" upload was stored
as-is), and a phone photo's EXIF (GPS coordinates, device identifiers) was
kept indefinitely, unstripped.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import CableProfile, Sample, Standard, User
from app.services.auth_service import hash_password
from app.services.image_upload import MAX_UPLOAD_BYTES


def _real_jpeg_bytes(size=(20, 20), color=(120, 60, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _jpeg_with_exif_bytes() -> bytes:
    img = Image.new("RGB", (10, 10), color=(10, 20, 30))
    exif = img.getexif()
    exif[271] = "Test Phone Manufacturer"  # Make
    exif[272] = "Test Phone Model"          # Model
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestSessionLocal()
    assistant = User(username="asst_upl", full_name="Assistant Upload", role="SCIENTIFIC_ASSISTANT",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(assistant)
    db.flush()

    standard = Standard(standard_id="STD-UPL", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-UPL-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=assistant.id, assigned_assistant_id=assistant.id)
    db.add(sample)
    db.flush()
    db.add(CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                         confirmed=True, tested_core_colors=["RED"]))
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-UPL-0001"
        yield c

    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "asst_upl", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_a_real_image_upload_succeeds(client):
    token = _token(client)
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("diagram.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_html_content_disguised_with_a_jpg_extension_is_rejected(client):
    # The exact bug: the extension was trusted verbatim. Real content
    # validation must reject this regardless of what the filename claims.
    token = _token(client)
    html_payload = b"<html><body><script>alert(document.cookie)</script></body></html>"
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("innocent.jpg", io.BytesIO(html_payload), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_svg_upload_is_rejected(client):
    # SVG can carry <script> -- and isn't decodable by Pillow as a raster
    # image, so it's rejected the same way any other non-raster content is.
    token = _token(client)
    svg_payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("diagram.svg", io.BytesIO(svg_payload), "image/svg+xml")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_empty_file_is_rejected(client):
    token = _token(client)
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_oversized_upload_is_rejected(client):
    token = _token(client)
    oversized = b"\x00" * (MAX_UPLOAD_BYTES + 1024)
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("huge.jpg", io.BytesIO(oversized), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 413


def test_stored_diagram_is_always_a_jpeg_regardless_of_uploaded_filename(client):
    token = _token(client)
    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        # A misleading .png filename on genuinely-JPEG bytes -- the stored
        # extension must be server-determined, never taken from the client.
        files={"file": ("photo.png", io.BytesIO(_real_jpeg_bytes()), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    dl = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers={"Authorization": f"Bearer {token}"})
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "image/jpeg"
    assert dl.content[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_download_response_carries_nosniff_and_attachment_headers(client):
    token = _token(client)
    client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("d.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    dl = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers={"Authorization": f"Bearer {token}"})
    assert dl.headers.get("x-content-type-options") == "nosniff"
    assert "attachment" in dl.headers.get("content-disposition", "")


def test_exif_is_stripped_from_the_stored_image(client):
    # The privacy gap: a phone photo's EXIF (GPS coordinates, device
    # identifiers) must not survive into the stored/served file.
    token = _token(client)
    source = _jpeg_with_exif_bytes()
    source_img = Image.open(io.BytesIO(source))
    assert source_img.getexif().get(271) == "Test Phone Manufacturer"  # sanity: the source really has EXIF

    resp = client.post(
        f"/api/samples/{client.sample_id}/diagram-image",
        files={"file": ("photo.jpg", io.BytesIO(source), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    dl = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers={"Authorization": f"Bearer {token}"})
    stored_img = Image.open(io.BytesIO(dl.content))
    stored_exif = stored_img.getexif()
    assert 271 not in stored_exif, "EXIF Make tag survived re-encoding -- privacy data was not stripped"
    assert len(stored_exif) == 0, f"expected no EXIF data at all, found: {dict(stored_exif)}"


def test_marking_image_upload_is_hardened_the_same_way_as_diagram_image(client):
    # SEC-6 specifically flagged upload_marking_image as inconsistent with
    # its sibling -- confirm both endpoints go through the same hardening.
    token = _token(client)
    resp = client.post(
        f"/api/samples/{client.sample_id}/marking-image",
        files={"file": ("m.html", io.BytesIO(b"<script>alert(1)</script>"), "text/html")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/samples/{client.sample_id}/marking-image",
        files={"file": ("m.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
