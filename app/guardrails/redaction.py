"""G3 - mask personal and banking detail on the way out.

Annual reports carry signatory details, bank mandates and contact pages.
An answer that quotes one of those has leaked it into a chat log, so the
last thing that happens to an answer is this pass.

Order matters. IBAN runs before account number, or the tail of an IBAN
matches the account pattern and the mask lands in the middle of it.

Financial figures must survive. £2,151.2m, 6.8% and page 59 are the whole
point of the product, so every pattern here is anchored on something a
figure does not have - a word boundary of eight or more digits, an IBAN's
country prefix, an @, a phone's punctuation.
"""

import re

from app.logging_config import get_logger

log = get_logger(__name__)

# Two letters, two check digits, then 11 to 30 alphanumerics, in groups
# of four or unbroken.
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{0,4}\b")

# UK sort code, 6 digits in three pairs.
SORT_CODE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

# A bare run of 8 to 17 digits. Long enough to be an account or card
# number and too long to be a figure in a report. Separators are not
# allowed, so 2,151.2 and 1,484.0 are untouched.
ACCOUNT = re.compile(r"(?<![\d.,])\d{8,17}(?![\d.]|,\d)")

# UK National Insurance: two letters, six digits, one of A-D.
NI_NUMBER = re.compile(r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b")

# UK UTR and company tax references, when labelled. Unlabelled 10-digit
# runs are caught by ACCOUNT.
TAX_ID = re.compile(
    r"\b(?:UTR|VAT(?:\s+(?:reg(?:istration)?|number|no\.?))?|EIN|TIN)"
    r"[:\s]+(?:GB\s?)?[\dA-Z][\dA-Z\s-]{6,15}\b",
    re.I,
)

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# +44 20 7946 0018, (020) 7946 0018, 07700 900123. A leading + or 0 is
# required, so a run of figures in a table is never read as a number to
# ring.
PHONE = re.compile(
    r"(?:\+\d{1,3}[\s-]?(?:\(\d{1,5}\)|\d{2,5})|\(0\d{2,4}\)|\b0\d{2,4})"
    r"[\s-]?\d{3,4}[\s-]?\d{3,4}\b"
)

# Applied in order.
PATTERNS = (
    ("email", EMAIL, "[email redacted]"),
    ("iban", IBAN, "[IBAN redacted]"),
    ("sort code", SORT_CODE, "[sort code redacted]"),
    ("tax id", TAX_ID, "[tax reference redacted]"),
    ("national insurance", NI_NUMBER, "[NI number redacted]"),
    ("phone", PHONE, "[phone number redacted]"),
    ("account", ACCOUNT, "[account number redacted]"),
)


def redact(text: str) -> str:
    """Mask personal and banking detail in an answer."""
    if not text:
        return text

    found: list[str] = []
    for name, pattern, replacement in PATTERNS:
        text, hits = pattern.subn(replacement, text)
        if hits:
            found.append(f"{name}x{hits}")

    if found:
        # Names and counts only. The matched text is the thing being
        # hidden, so it never reaches a log line.
        log.info("redacted %s", " ".join(found))

    return text
