"Decide whether a job posting matches a search's keywords."

from __future__ import annotations

from typing import Iterable, Sequence

from .text import tokenize


def _haystack(*parts: str) -> str:
    return tokenize(" ".join(part for part in parts if part))


# French aliases are checked locally; they do not create extra LinkedIn queries.
ALIASES: dict[str, tuple[str, ...]] = {
    "avionics": ("avionique", "systèmes avioniques"),
    "avionics systems": ("systèmes avioniques",),
    "aircraft systems engineer": (
        "ingénieur système aéronautique", "ingénieur systèmes aéronautiques",
        "ingénieur systèmes avioniques", "ingénieur système avionique",
    ),
    "aircraft systems": ("systèmes aéronautiques",),
    "flight controls": ("commandes de vol", "systèmes de commandes de vol"),
    "flight control systems": ("systèmes de commandes de vol",),
    "autoflight": ("pilotage automatique", "systèmes de pilotage automatique"),
    "flight management systems": ("systèmes de gestion de vol",),
    "aircraft navigation systems": ("systèmes de navigation aéronautique",),
    "aircraft communications": ("communications aéronautiques",),
    "avionics support": ("support avionique", "support systèmes avioniques"),
    "aircraft support engineer": ("ingénieur support aéronautique", "support technique aéronautique"),
    "aircraft customer support": ("support client aéronautique",),
    "aircraft technical support": ("support technique aéronautique",),
    "aircraft product support": ("support produit aéronautique",),
    "aerospace customer support": ("support client aérospatial", "support client aéronautique"),
    "aerospace technical support": ("support technique aérospatial", "support technique aéronautique"),
    "aerospace product support": ("support produit aérospatial", "support produit aéronautique"),
    "in-service support engineer": ("ingénieur soutien en service", "support en service aéronautique"),
    "customer support avionics": ("support client avionique",),
    "aircraft systems engineering": ("ingénierie des systèmes aéronautiques", "ingénierie systèmes aéronautiques"),
    "aerospace systems engineer": ("ingénieur systèmes aérospatiaux",),
    "aviation systems engineer": ("ingénieur systèmes aéronautiques",),
    "aircraft system integration": ("intégration des systèmes aéronautiques",),
    "aircraft systems integration": ("intégration des systèmes aéronautiques",),
    "aircraft systems support": ("support systèmes aéronautiques",),
    "avionics systems engineer": ("ingénieur systèmes avioniques", "ingénieur système avionique"),
    "aircraft electrical systems": ("systèmes électriques aéronautiques",),
    "flight systems engineer": ("ingénieur systèmes de vol",),
}


ACRONYM_LENGTH = 3


def _contains(haystack: str, term: str) -> bool:
    """True when term starts a word in haystack."""
    needle = tokenize(term).strip()
    if not needle:
        return False
    if len(needle.replace(" ", "")) <= ACRONYM_LENGTH:
        return f" {needle} " in haystack
    return f" {needle}" in haystack


def _keyword_matches(haystack: str, keyword: str) -> bool:
    if _contains(haystack, keyword):
        return True
    aliases = ALIASES.get(tokenize(keyword).strip(), ())
    return any(_contains(haystack, alias) for alias in aliases)


def matched_keywords(text: str, keywords: Sequence[str]) -> list[str]:
    """Return matched configured keywords, in config order."""
    haystack = _haystack(text)
    return [keyword for keyword in keywords if _keyword_matches(haystack, keyword)]


def matches(
    text: str,
    keywords: Sequence[str],
    mode: str = "any",
    exclude: Iterable[str] = (),
) -> list[str]:
    """Return matched keywords, or an empty list when the posting is rejected."""
    haystack = _haystack(text)
    if any(_contains(haystack, term) for term in exclude):
        return []

    hits = [keyword for keyword in keywords if _keyword_matches(haystack, keyword)]
    if mode == "all":
        return hits if len(hits) == len(keywords) else []
    return hits
