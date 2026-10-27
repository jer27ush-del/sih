"""Document intake: real file-type check, size limit, checksum, scan hook, private storage."""
import hashlib
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.db.models import Max

from common.exceptions import BusinessRuleError
from portal.models import SystemSettings

from .models import Document

# Magic bytes identify the real file type, regardless of what the filename claims.
SIGNATURES = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
]


def detect_mime(head: bytes):
    for signature, mime in SIGNATURES:
        if head.startswith(signature):
            return mime
    return None


def scan_upload(file_obj) -> str:
    """Malware-scan hook. This release ships no scanner, so uploads are marked UNSCANNED.
    Before production, connect ClamAV (or similar) here and return CLEAN or INFECTED.
    With REQUIRE_MALWARE_SCAN=true, unscanned uploads are refused."""
    return Document.ScanStatus.UNSCANNED


def store_document(fdr, uploaded, actor):
    cfg = SystemSettings.load()
    size = uploaded.size
    if size == 0:
        raise BusinessRuleError("The uploaded file is empty.")
    if size > cfg.document_max_bytes:
        raise BusinessRuleError(f"The file is larger than the {cfg.document_max_bytes // (1024 * 1024)} MB limit.")

    mime = detect_mime(uploaded.read(16))
    uploaded.seek(0)
    if mime is None or mime not in cfg.allowed_document_types:
        raise BusinessRuleError("Only PDF, PNG or JPEG files are accepted, and the content must match the file type.")

    scan = scan_upload(uploaded)
    if scan == Document.ScanStatus.INFECTED:
        raise BusinessRuleError("The file failed the malware scan and was not stored.")
    if scan == Document.ScanStatus.UNSCANNED and settings.REQUIRE_MALWARE_SCAN:
        raise BusinessRuleError("Uploads are disabled until a malware scanner is configured.")

    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)

    storage_name = f"{fdr.pk}/{uuid.uuid4().hex}.bin"
    path = Path(settings.PRIVATE_UPLOAD_ROOT) / storage_name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as out:
        for chunk in uploaded.chunks():
            out.write(chunk)

    version = (fdr.documents.aggregate(top=Max("version"))["top"] or 0) + 1
    fdr.documents.filter(active=True).update(active=False)  # older versions are kept, not deleted
    return Document.objects.create(
        fdr=fdr,
        storage_name=storage_name,
        original_name=os.path.basename(uploaded.name or "upload")[:255],
        mime_type=mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
        version=version,
        uploaded_by=actor,
        active=True,
        scan_status=scan,
    )


def absolute_path(document):
    return Path(settings.PRIVATE_UPLOAD_ROOT) / document.storage_name
