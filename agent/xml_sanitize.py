from __future__ import annotations

import re


def sanitize_xml(text: str) -> str:
    """Remove illegal numeric character references that Tally emits (e.g. &#4;)."""

    def allowed(value: int) -> bool:
        return value in {9, 10, 13} or 32 <= value <= 55295 or 57344 <= value <= 65533 or 65536 <= value <= 1114111

    text = re.sub(r"&#([0-9]+);", lambda match: match.group(0) if allowed(int(match.group(1))) else "", text)
    return re.sub(
        r"&#x([0-9A-Fa-f]+);",
        lambda match: match.group(0) if allowed(int(match.group(1), 16)) else "",
        text,
    )
