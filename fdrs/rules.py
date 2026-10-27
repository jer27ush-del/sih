"""Automated verification rules (Section 6 of the design document).

These are pure functions: they take plain values and return flags. They never
reject a record on their own; they only mark it for an officer's attention.
Bank confirmation is the one rule that gates the Verified status.
"""
from datetime import date

PASS, WARNING, FAIL = "pass", "warning", "fail"


def run_rules(
    *,
    fdr_number,
    bank,
    branch,
    amount_paise,
    issue_date,
    maturity_date,
    documents,
    duplicate_exists,
    bank_confirmed,
    allowed_mime_types,
    minimum_tenure_days,
    amount_min_paise,
    amount_max_paise,
    today=None,
):
    """`documents` is a list of dicts with keys: mime_type, size_bytes, active, scan_status."""
    today = today or date.today()
    usable_docs = [
        d for d in documents
        if d["active"] and d["size_bytes"] > 0 and d["mime_type"] in allowed_mime_types
        and d["scan_status"] in ("clean", "unscanned")
    ]
    has_usable_doc = bool(usable_docs)
    tenure_days = (maturity_date - issue_date).days

    return {
        "required_fields": PASS if (
            fdr_number.strip() and bank.strip() and branch.strip() and amount_paise > 0
            and issue_date and maturity_date and has_usable_doc
        ) else FAIL,
        "duplicate_reference": FAIL if duplicate_exists else PASS,
        "date_logic": PASS if (maturity_date > issue_date and issue_date <= today) else WARNING,
        "tenure_validity": PASS if tenure_days >= minimum_tenure_days else WARNING,
        "amount_range": PASS if amount_min_paise <= amount_paise <= amount_max_paise and amount_paise > 0 else WARNING,
        "document_quality": PASS if has_usable_doc else WARNING,
        "bank_confirmation": PASS if bank_confirmed else FAIL,
    }
