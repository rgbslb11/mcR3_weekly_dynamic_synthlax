from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock

P4 = {"SEC", "Big Ten", "Big 12", "ACC"}
G5 = {"Pac-12", "Mountain West", "American", "Atlantic-8", "ECL"}


@dataclass(frozen=True)
class CFPSelection:
    seeds: dict[int, str]
    bid_types: dict[str, str]


def select_governed_14_team_cfp(
    committee_order: list[str],
    conference_of: dict[str, str],
    conference_champions: dict[str, str],
) -> CFPSelection:
    rank = {t: i + 1 for i, t in enumerate(committee_order)}
    qualifiers: set[str] = set()
    bid_types: dict[str, str] = {}

    for conf in sorted(P4):
        champ = conference_champions.get(conf)
        if champ is None:
            raise GovernanceBlock(f"Missing governed champion for {conf}")
        qualifiers.add(champ)
        bid_types[champ] = "AUTO_P4_CHAMPION"

    g5_champs = [conference_champions.get(c) for c in G5 if conference_champions.get(c)]
    if not g5_champs:
        raise GovernanceBlock("No G5 conference champions available for CG-8 auto-bid")
    g5_auto = min(g5_champs, key=lambda t: rank[t])
    qualifiers.add(g5_auto)
    bid_types[g5_auto] = "AUTO_HIGHEST_RANKED_G5_CHAMPION"

    if "ND" in rank and rank["ND"] <= 14:
        qualifiers.add("ND")
        bid_types["ND"] = "AUTO_NOTRE_DAME_TOP14"

    for team in committee_order:
        if len(qualifiers) >= 14:
            break
        if team not in qualifiers:
            qualifiers.add(team)
            bid_types[team] = "AT_LARGE"

    seeded = sorted(qualifiers, key=lambda t: rank[t])
    if len(seeded) != 14:
        raise GovernanceBlock(f"CFP selection produced {len(seeded)} teams, expected 14")
    return CFPSelection(seeds={i + 1: t for i, t in enumerate(seeded)}, bid_types=bid_types)


def bracket_games_from_seeds(selection: CFPSelection) -> dict[str, tuple[str, str] | str]:
    s = selection.seeds
    return {
        "PLAYIN_11_14": (s[11], s[14]),
        "PLAYIN_12_13": (s[12], s[13]),
        "BYE_1": s[1],
        "BYE_2": s[2],
        "BYE_3": s[3],
        "BYE_4": s[4],
        # First-round 5v12 and 6v11 slots depend on play-in winners; 7v10 and 8v9 are fixed.
        "R1_7_10": (s[7], s[10]),
        "R1_8_9": (s[8], s[9]),
    }


# --- Quarterfinal opponent mapping (governance-gated) -------------------------
#
# The Playoff Calendar's Bracket_Flow sheet fixes the quarterfinal *slots* and the
# semifinal pairing:
#
#     E = 1 v W(R1)   F = 2 v W(R1)   G = 3 v W(R1)   H = 4 v W(R1)
#     Semi A = W(E) v W(H)            Semi B = W(F) v W(G)
#
# What it never states is *which* first-round winner lands in E, F, G or H. Both
# candidate rules below satisfy every recorded constraint, including integrity
# item P-3 (seeds 1 and 2 in opposite halves), and they disagree whenever an
# upset changes the surviving seed order. The mapping is therefore genuinely
# unresolved rather than merely unstated, and inferring one would silently pick a
# bracket shape that the governed sources do not endorse.

QUARTERFINAL_MAPPING_OPTIONS = (
    # Fixed bracket: quarterfinal opponent determined by the bracket slot a first
    # round game occupies, irrespective of which team wins it.
    "FIXED_BRACKET_MAPPING",
    # Reseeding: the highest remaining seed plays the lowest remaining seed.
    "RESEED_BY_ORIGINAL_SEED",
)


def require_governed_quarterfinal_mapping(mapping_policy: str | None) -> str:
    """Fail closed until the R1-winner to quarterfinal mapping is governed."""
    if mapping_policy is None:
        raise GovernanceBlock(
            "CFP quarterfinal R1-winner mapping is not explicit in the Bracket Regime "
            "or Playoff Calendar. Bracket_Flow fixes only 'E = 1 v W(R1)' style slots. "
            f"An explicit ruling is required, from {sorted(QUARTERFINAL_MAPPING_OPTIONS)}."
        )
    if mapping_policy not in QUARTERFINAL_MAPPING_OPTIONS:
        raise GovernanceBlock(
            f"Unknown quarterfinal mapping policy {mapping_policy!r}; "
            f"expected one of {sorted(QUARTERFINAL_MAPPING_OPTIONS)}."
        )
    return mapping_policy
