"""
File integrity checksums (H10) -- SHA-256 of a certificate's generated
.docx file, computed once at generation time and stored on
Certificate.file_checksum_sha256. A small standalone module (not inlined
into docx_report_filler.py) so a future amendment/reissue feature can
reuse this same function to verify an EXISTING certificate file against
its stored checksum -- e.g. confirming a downloaded copy matches what the
system actually generated -- without importing the whole report-filling
module just for that.
"""
import hashlib

# Certificates are small (a few hundred KB), but reading in chunks rather
# than the whole file at once keeps this correct if it's ever reused
# against a much larger file later.
_CHUNK_SIZE = 1024 * 1024


def compute_file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
