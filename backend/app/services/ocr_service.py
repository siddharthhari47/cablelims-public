"""
Marking OCR -- stub interface only.

Per CableLIMS_SDD_v2.md section 6.6, automated marking OCR is deliberately
out of scope for v1 (and doubly out of scope for a one-day MVP): every cable
standard treats fire-category misclassification as a safety-relevant error,
so this must be a confirmed-assist feature built carefully, not rushed.

This stub exists so the API shape (`profile capture accepts an image and
may return extracted fields`) is already correct, and a real OCR
implementation can be dropped in later without changing any caller.
"""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class OcrResult:
    available: bool
    extracted_fields: Optional[Dict[str, str]]
    confidence: Optional[float]
    note: str


def extract_marking(image_path: str) -> OcrResult:
    return OcrResult(
        available=False,
        extracted_fields=None,
        confidence=None,
        note="Automated marking OCR is not implemented in this MVP. "
             "Enter the profile manually from the marking photo.",
    )
