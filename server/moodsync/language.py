"""Normalize language names and regional codes to one language code."""
import re


def canonical_language(value: str | None) -> str | None:
    value = str(value or "").strip().lower().replace("_", "-")
    if value in {"", "unknown", "und", "none"}:
        return None
    aliases = {"english": "en", "eng": "en", "french": "fr", "fra": "fr", "hindi": "hi",
               "spanish": "es", "spa": "es", "german": "de", "deu": "de", "japanese": "ja"}
    value = aliases.get(value, value.split("-")[0])
    return value if re.fullmatch(r"[a-z]{2,3}", value) else None
