"""Strict cell parsers and field declarations.

The importer never fixes source data. A parser either returns a clean value
or raises CellError; a CellError fails the whole row (it is skipped and
reported). The only transformation applied anywhere is stripping leading and
trailing whitespace, which reads past Excel's presentation rather than
altering the data.
"""

from dataclasses import dataclass
from typing import Any, Callable

Parser = Callable[[Any], Any]


class CellError(ValueError):
    """A cell value that does not pass strict validation.

    The message becomes the reported reason for skipping the row.
    """


def strict_str(value: Any) -> str | None:
    """A text cell: stripped string; empty becomes None.

    Numbers are stringified (Excel stores e.g. the identifier 29 as an int).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CellError(f"expected text, got boolean {value!r}")
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    raise CellError(f"expected text, got {type(value).__name__} {value!r}")


def strict_int(value: Any) -> int | None:
    """An integer cell: int, or a float with no fractional part.

    Anything else — including strings such as '>7000' or '5000, 1200' —
    is a validation failure.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CellError(f"expected an integer, got boolean {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise CellError(f"expected an integer, got {value!r}")


def strict_choice(*allowed: str) -> Parser:
    """A cell whose stripped value must be one of the allowed strings."""

    def parse(value: Any) -> str | None:
        text = strict_str(value)
        if text is None:
            return None
        if text not in allowed:
            raise CellError(f"expected one of {list(allowed)}, got {text!r}")
        return text

    return parse


def strict_canonical(*canonical: str) -> Parser:
    """A cell matched case-insensitively against canonical labels.

    Returns the canonical spelling (e.g. 'LOST' → 'Lost'). A documented,
    deliberate exception to the no-normalization rule.
    """
    by_fold = {label.casefold(): label for label in canonical}

    def parse(value: Any) -> str | None:
        text = strict_str(value)
        if text is None:
            return None
        match = by_fold.get(text.casefold())
        if match is None:
            raise CellError(f"expected one of {list(canonical)}, got {text!r}")
        return match

    return parse


def strict_yesno(value: Any) -> bool | None:
    """A YES/NO cell (case-insensitive) → bool; empty or 'N/A' → None.

    Anything else — 'to be verified', 'NO (?)' — is a validation failure.
    """
    text = strict_str(value)
    if text is None:
        return None
    fold = text.casefold()
    if fold == "yes":
        return True
    if fold == "no":
        return False
    if fold == "n/a":
        return None
    raise CellError(f"expected YES, NO or N/A, got {text!r}")


def strict_tristate(value: Any) -> bool | None:
    """A tri-state cell: YES → True, NO → False, unknown → None.

    'N/A', '?', 'Unknown' and empty all mean unknown; anything else
    ('to be verified', stray values) is a validation failure.
    """
    text = strict_str(value)
    if text is None:
        return None
    fold = text.casefold()
    if fold == "yes":
        return True
    if fold == "no":
        return False
    if fold in {"n/a", "?", "unknown"}:
        return None
    raise CellError(f"expected YES, NO, N/A, ? or Unknown, got {text!r}")


@dataclass(frozen=True)
class FieldSpec:
    """One Excel column: exact header, strict parser, required-ness."""

    column: str
    parser: Parser
    required: bool = False
