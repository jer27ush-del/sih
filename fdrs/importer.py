"""Bulk import of existing FDRs from CSV (Page 7).

Every row is validated before anything is saved. Money is parsed from rupees
into integer paise with Decimal, never with floating point.
"""
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

REQUIRED_COLUMNS = [
    "fdr_number", "bank", "branch", "amount_rupees", "issue_date", "maturity_date",
    "interest_rate", "payout_type", "category",
]
OPTIONAL_COLUMNS = ["lien_marked", "held_in_favour_of_aicte"]
MAX_ROWS = 5000
TEMPLATE_HEADER = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
TEMPLATE_SAMPLE = [
    "DEMO-FDR-1001", "Sample National Bank", "Chennai Main", "500000.00", "2026-01-15", "2027-01-15",
    "6.50", "cumulative", "Security Deposit", "yes", "yes",
]
TRUE_WORDS = {"yes", "y", "true", "1"}
FALSE_WORDS = {"no", "n", "false", "0", ""}


class ImportFormatError(ValueError):
    """The file as a whole cannot be read (wrong encoding, missing columns, too many rows)."""


def template_csv() -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TEMPLATE_HEADER)
    writer.writerow(TEMPLATE_SAMPLE)
    return buffer.getvalue()


def parse_amount_paise(text: str) -> int:
    cleaned = text.replace(",", "").replace("₹", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Amount must be a number, for example 500000 or 500000.00.") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("Amount must be a positive number.")
    paise = value * 100
    if paise != paise.to_integral_value():
        raise ValueError("Amount may have at most two decimal places.")
    return int(paise)


def parse_date(text: str, label: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be in YYYY-MM-DD format.") from exc


def parse_bool(text: str, label: str, default: bool) -> bool:
    if text == "":
        return default
    lowered = text.lower()
    if lowered in TRUE_WORDS:
        return True
    if lowered in FALSE_WORDS:
        return False
    raise ValueError(f"{label} must be yes or no.")


def parse_csv(data: bytes, max_bytes: int):
    if len(data) > max_bytes:
        raise ImportFormatError("The file is larger than the upload limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError("The file must be a UTF-8 encoded CSV.") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        raise ImportFormatError(f"Missing required column(s): {', '.join(missing)}.")

    rows = []
    for index, raw in enumerate(reader, start=2):  # line 1 is the header
        if index - 1 > MAX_ROWS:
            raise ImportFormatError(f"A single import is limited to {MAX_ROWS} rows.")
        values = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        rows.append(_validate_row(index, values))
    return rows


def _validate_row(line: int, values: dict) -> dict:
    errors = []
    parsed = {}
    for column in REQUIRED_COLUMNS:
        if not values.get(column):
            errors.append(f"{column.replace('_', ' ')} is required")

    if not errors:
        try:
            parsed["fdr_number"] = values["fdr_number"]
            parsed["bank"] = values["bank"]
            parsed["branch"] = values["branch"]
            parsed["category"] = values["category"]
            parsed["amount_paise"] = parse_amount_paise(values["amount_rupees"])
            parsed["issue_date"] = parse_date(values["issue_date"], "Issue date")
            parsed["maturity_date"] = parse_date(values["maturity_date"], "Maturity date")
            parsed["interest_rate"] = Decimal(values["interest_rate"])
            if not (Decimal("0") <= parsed["interest_rate"] <= Decimal("100")):
                raise ValueError("Interest rate must be between 0 and 100.")
            payout = values["payout_type"].lower()
            if payout not in ("cumulative", "periodic"):
                raise ValueError("Payout type must be 'cumulative' or 'periodic'.")
            parsed["payout_type"] = payout
            parsed["lien_marked"] = parse_bool(values.get("lien_marked", ""), "Lien marked", False)
            parsed["held_in_favour_of_aicte"] = parse_bool(
                values.get("held_in_favour_of_aicte", ""), "Held in favour of AICTE", True
            )
            if parsed["maturity_date"] <= parsed["issue_date"]:
                raise ValueError("Maturity date must be after the issue date.")
        except (ValueError, InvalidOperation) as exc:
            errors.append(str(exc))
    return {"line": line, "data": parsed, "errors": errors, "raw": values}


def classify(rows, existing_keys, banks, categories):
    """Mark each row valid / error / duplicate. `existing_keys` holds (fdr_number, bank) pairs,
    lower-cased, already in the portal. Within-file repeats are duplicates too."""
    seen = {}
    lowered_banks = {b.lower() for b in banks}
    lowered_categories = {c.lower() for c in categories}
    for row in rows:
        if not row["errors"]:
            data = row["data"]
            if data["bank"].lower() not in lowered_banks:
                row["errors"].append("Bank is not in the configured bank list.")
            if data["category"].lower() not in lowered_categories:
                row["errors"].append("Category is not in the configured category list.")

        if row["errors"]:
            row["status"] = "error"
            continue

        key = (row["data"]["fdr_number"].lower(), row["data"]["bank"].lower())
        if key in existing_keys:
            row["status"], row["reason"] = "duplicate", "This FDR number already exists for this bank."
        elif key in seen:
            row["status"], row["reason"] = "duplicate", f"Repeats line {seen[key]} in this file."
        else:
            seen[key] = row["line"]
            row["status"], row["reason"] = "valid", ""
    return rows
