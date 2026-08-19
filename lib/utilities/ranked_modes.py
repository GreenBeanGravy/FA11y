"""Shared Fortnite ranked-mode identifiers and display ordering."""
from __future__ import annotations

from typing import Iterable, Mapping


RANKED_MODE_NAMES = {
    "ranked-br-combined": "Battle Royale",
    "ranked-blastberry-combined": "Reload",
    "ranked_blastberry_build": "Reload",
    "ranked_blastberry_nobuild": "Reload Zero Build",
    "ranked-figment-build": "OG",
    "ranked-figment-nobuild": "OG Zero Build",
    "ranked-squareclub": "Arena Box Fights",
}

# Used only when Epic's active-track discovery endpoint is unavailable.
FALLBACK_RANKING_TYPES = tuple(RANKED_MODE_NAMES)

# FA11y intentionally displays the core BR, Reload, OG, and Arena modes. Match
# by family so a newly consolidated/split track can be discovered without
# requiring an exact identifier in every consumer first.
SUPPORTED_RANKING_TYPE_PREFIXES = (
    "ranked-br",
    "ranked_blastberry",
    "ranked-blastberry",
    "ranked-figment",
    "ranked-squareclub",
)


def is_supported_ranking_type(ranking_type: object) -> bool:
    return isinstance(ranking_type, str) and ranking_type.startswith(
        SUPPORTED_RANKING_TYPE_PREFIXES
    )


def ranked_mode_name(ranking_type: str) -> str:
    """Return a friendly label, including a readable fallback for new types."""
    known = RANKED_MODE_NAMES.get(ranking_type)
    if known:
        return known
    return ranking_type.replace("_", "-").replace("ranked-", "", 1).replace(
        "-", " "
    ).title()


def ordered_ranking_types(ranked_data: Mapping[str, object]) -> Iterable[str]:
    """Yield known modes in UI order, then any newly discovered modes."""
    yielded = set()
    for ranking_type in FALLBACK_RANKING_TYPES:
        if ranking_type in ranked_data:
            yielded.add(ranking_type)
            yield ranking_type
    for ranking_type in sorted(ranked_data):
        if ranking_type not in yielded:
            yield ranking_type
