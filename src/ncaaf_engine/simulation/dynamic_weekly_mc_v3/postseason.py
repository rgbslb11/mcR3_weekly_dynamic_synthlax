from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

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
    if mapping_policy == "RESEED_BY_ORIGINAL_SEED":
        # Superseded after this function was written. Kept in the option tuple so
        # the historical candidate set stays visible, refused here so no caller
        # can select it.
        raise GovernanceBlock(
            "RESEED_BY_ORIGINAL_SEED is superseded by ruling R2-NO-RESEED: there is no "
            "reseeding. The remaining question is which first-round winner fills each "
            "quarterfinal slot, which the official artifact never states."
        )
    return mapping_policy


# --- R2 playoff topology ------------------------------------------------------
#
# Ruling R2-G5-SEED5 makes the Group-of-5 automatic bid a seed, not just a bid,
# and ruling R2-NO-RESEED fixes the bracket. Both are encoded here against what
# the official 2026 Playoff Calendar and Bracket Regime actually state. The one
# thing neither artifact states — which first-round winner fills quarterfinal
# slot E, F, G or H — is still not stated, so it is still refused.

from .rulings import R2_G5_AUTO_BID, R2_NO_RESEEDING  # noqa: E402

#: FACT — the five Group-of-5 conferences. Identical to :data:`G5`, named
#: separately because the ruling enumerates them and the count is load-bearing.
G5_CONFERENCES: tuple[str, ...] = ("AAC", "Atlantic-8", "ECL", "Mountain West", "Pac-12")

#: The AAC appears in the schedule and team master as "American".
G5_CONFERENCE_ALIASES = {"AAC": "American", "American": "American"}

#: FACT — ruling R2-G5-SEED5. Exact, not a floor, and not a ceiling either: a
#: champion ranked 1st and a champion ranked 14th both land on seed 5.
G5_AUTOMATIC_BID_SEED = 5
G5_AUTOMATIC_BID_COUNT = 1

#: FACT — Bracket Regime LOCKED S3 / Playoff Calendar Bracket_Flow.
PLAY_IN_SEEDS: tuple[int, ...] = (11, 12, 13, 14)

#: FACT — Bracket Regime LOCKED S2.
BYE_SEEDS: tuple[int, ...] = (1, 2, 3, 4)

#: FACT — Playoff Calendar Bracket_Flow: "G1 = 12 v 13 (Minneapolis);
#: G2 = 11 v 14 (Atlanta)"; Bracket Regime S4: "First Round 5v12, 6v11, 7v10, 8v9".
GOVERNED_PLAY_IN_EDGES = {"PLAYIN_G1": (12, 13), "PLAYIN_G2": (11, 14)}
GOVERNED_ROUND_1_EDGES = {
    "R1_A_5_12": (5, 12),
    "R1_B_6_11": (6, 11),
    "R1_C_7_10": (7, 10),
    "R1_D_8_9": (8, 9),
}

#: FACT — Bracket_Flow: "E = 1 v W(R1); F = 2 v W(R1); G = 3 v W(R1); H = 4 v W(R1)".
GOVERNED_QUARTERFINAL_HOSTS = {"QF_E": 1, "QF_F": 2, "QF_G": 3, "QF_H": 4}

#: FACT — Bracket_Flow / Rulings_Register P-3.
GOVERNED_SEMIFINAL_EDGES = {"SEMI_A": ("QF_E", "QF_H"), "SEMI_B": ("QF_F", "QF_G")}

#: DERIVED — ruling R2-NO-RESEED removes reseeding from the option set. What
#: remains unstated is the slot assignment, not the mapping family.
RESEEDING_PERMITTED = False
QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT = False
QUARTERFINAL_MAPPING_BLOCKER = "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT"


def g5_conference_key(conference: str) -> str:
    return G5_CONFERENCE_ALIASES.get(conference, conference)


def g5_automatic_bid_champion(
    committee_order: Sequence[str], conference_champions: Mapping[str, str]
) -> str:
    """The single highest-ranked Group-of-5 conference champion.

    Champion status is required: a higher-ranked G5 team that did not win its
    conference does not take this bid.
    """
    rank = {t: i for i, t in enumerate(committee_order)}
    candidates: list[str] = []
    for conf in G5_CONFERENCES:
        champ = conference_champions.get(g5_conference_key(conf)) or conference_champions.get(conf)
        if champ is None:
            continue
        if champ not in rank:
            raise GovernanceBlock(
                f"G5 champion {champ} ({conf}) is absent from the committee board"
            )
        candidates.append(champ)
    if not candidates:
        raise GovernanceBlock(
            "No Group-of-5 conference champion is available for the automatic bid "
            f"(ruling {R2_G5_AUTO_BID.convergence_id})."
        )
    return min(sorted(set(candidates)), key=lambda t: rank[t])


def apply_g5_automatic_bid_seed(
    selection: CFPSelection,
    committee_order: Sequence[str],
    conference_champions: Mapping[str, str],
) -> CFPSelection:
    """Re-seed the field so the G5 automatic-bid champion sits at seed 5 exactly.

    Every other qualifier keeps its committee-rank order around that fixed slot.
    Reseeding between rounds is a different thing entirely and remains forbidden.
    """
    champion = g5_automatic_bid_champion(committee_order, conference_champions)
    rank = {t: i for i, t in enumerate(committee_order)}
    field = list(selection.seeds.values())
    if champion not in field:
        raise GovernanceBlock(
            f"G5 automatic-bid champion {champion} is not in the selected field"
        )

    # A G5 champion ranked inside the top four is still seeded 5. Bracket Regime
    # S2 ("The FOUR HIGHEST-RANKED TEAMS OVERALL receive a first-round bye") is
    # the older language and is superseded to exactly that extent: the bye seeds
    # stay 1-4, and the team that would otherwise have been 5th moves up into
    # the vacated bye. This is a supersession, not a fresh governance question --
    # ruling R2-G5-SEED5 says seed 5 exactly, not seed 5 or lower.

    others = sorted((t for t in field if t != champion), key=lambda t: rank[t])
    seeds: dict[int, str] = {}
    cursor = iter(others)
    for seed in range(1, len(field) + 1):
        seeds[seed] = champion if seed == G5_AUTOMATIC_BID_SEED else next(cursor)

    bid_types = dict(selection.bid_types)
    bid_types[champion] = "AUTO_HIGHEST_RANKED_G5_CHAMPION"
    return CFPSelection(seeds=seeds, bid_types=bid_types)


def g5_automatic_bid_audit(
    selection: CFPSelection, conference_of: Mapping[str, str]
) -> dict[str, object]:
    """Confirm exactly one G5 automatic bid, seeded 5, and out of the play-in."""
    auto = sorted(
        t for t, b in selection.bid_types.items() if b == "AUTO_HIGHEST_RANKED_G5_CHAMPION"
    )
    if len(auto) != G5_AUTOMATIC_BID_COUNT:
        raise GovernanceBlock(
            f"{len(auto)} Group-of-5 automatic bids were issued; ruling "
            f"{R2_G5_AUTO_BID.convergence_id} allows exactly {G5_AUTOMATIC_BID_COUNT}."
        )
    champion = auto[0]
    seed_of = {t: s for s, t in selection.seeds.items()}
    seed = seed_of[champion]
    if seed != G5_AUTOMATIC_BID_SEED:
        raise GovernanceBlock(
            f"G5 automatic-bid champion {champion} is seeded {seed}; ruling "
            f"{R2_G5_AUTO_BID.convergence_id} fixes seed {G5_AUTOMATIC_BID_SEED} exactly."
        )
    if seed in PLAY_IN_SEEDS:
        raise GovernanceBlock(f"G5 automatic-bid champion {champion} may not play in a play-in game")
    return {
        "ruling": R2_G5_AUTO_BID.convergence_id,
        "g5_conferences": list(G5_CONFERENCES),
        "automatic_bids": len(auto),
        "champion": champion,
        "seed": seed,
        "conference": g5_conference_key(conference_of.get(champion, "")),
        "in_play_in": False,
        "supersedes": list(R2_G5_AUTO_BID.supersedes),
    }


def governed_bracket_edges(selection: CFPSelection) -> dict[str, object]:
    """Bind every bracket edge the official artifacts actually state.

    Quarterfinal *hosts* are stated. Quarterfinal *opponents* are not, so they
    are absent from the result rather than filled in.
    """
    s = selection.seeds
    edges: dict[str, object] = {}
    for seed in BYE_SEEDS:
        edges[f"BYE_{seed}"] = s[seed]
    for slot, (a, b) in sorted(GOVERNED_PLAY_IN_EDGES.items()):
        edges[slot] = (s[a], s[b])
    for slot, (a, b) in sorted(GOVERNED_ROUND_1_EDGES.items()):
        edges[slot] = (s[a], s[b])
    for slot, seed in sorted(GOVERNED_QUARTERFINAL_HOSTS.items()):
        edges[slot] = s[seed]
    for slot, pair in sorted(GOVERNED_SEMIFINAL_EDGES.items()):
        edges[slot] = pair
    edges["CHAMPIONSHIP"] = ("SEMI_A", "SEMI_B")
    edges["reseeding_permitted"] = RESEEDING_PERMITTED
    edges["quarterfinal_r1_winner_slot_edges"] = None
    return edges


def require_no_reseeding(reseeding_requested: bool) -> None:
    if reseeding_requested:
        raise GovernanceBlock(
            f"Reseeding between rounds is forbidden by ruling {R2_NO_RESEEDING.convergence_id}; "
            "the official 2026 Playoff Calendar bracket topology is fixed."
        )


def require_governed_quarterfinal_slot_edges(
    slot_edges: Mapping[str, str] | None,
) -> Mapping[str, str]:
    """Fail closed on the one bracket edge the official artifact never states.

    Ruling R2-NO-RESEED removed reseeding from the candidate set, which narrows
    the question but does not answer it: ``Bracket_Flow`` fixes "E = 1 v W(R1)"
    and never says which first-round winner that is. Binding an edge here would
    invent bracket topology, which the ruling forbids in the same breath.
    """
    if slot_edges is None:
        raise GovernanceBlock(
            f"{QUARTERFINAL_MAPPING_BLOCKER}: the official 2026 Playoff Calendar "
            "Bracket_Flow sheet states quarterfinal slots as 'E = 1 v W(R1)' and never "
            "states which first-round winner fills E, F, G or H. Ruling "
            f"{R2_NO_RESEEDING.convergence_id} rules out reseeding and binds every edge the "
            "artifact does state, but the slot edges themselves remain unstated. Supply them "
            "from the artifact; do not invent them."
        )
    missing = sorted(set(GOVERNED_QUARTERFINAL_HOSTS) - set(slot_edges))
    if missing:
        raise GovernanceBlock(f"Quarterfinal slot edges are incomplete: missing {missing}")
    unknown = sorted(set(slot_edges) - set(GOVERNED_QUARTERFINAL_HOSTS))
    if unknown:
        raise GovernanceBlock(f"Unknown quarterfinal slots: {unknown}")
    r1_slots = set(GOVERNED_ROUND_1_EDGES)
    bad = sorted(v for v in slot_edges.values() if v not in r1_slots)
    if bad:
        raise GovernanceBlock(f"Quarterfinal slot edges reference unknown first-round games: {bad}")
    if len(set(slot_edges.values())) != len(GOVERNED_QUARTERFINAL_HOSTS):
        raise GovernanceBlock("Quarterfinal slot edges must be a bijection onto the four R1 games")
    return slot_edges


def topology_as_dict() -> dict[str, object]:
    return {
        "rulings": [R2_G5_AUTO_BID.convergence_id, R2_NO_RESEEDING.convergence_id],
        "reseeding_permitted": RESEEDING_PERMITTED,
        "bye_seeds": list(BYE_SEEDS),
        "play_in_seeds": list(PLAY_IN_SEEDS),
        "play_in_edges": {k: list(v) for k, v in sorted(GOVERNED_PLAY_IN_EDGES.items())},
        "round_1_edges": {k: list(v) for k, v in sorted(GOVERNED_ROUND_1_EDGES.items())},
        "quarterfinal_hosts": dict(sorted(GOVERNED_QUARTERFINAL_HOSTS.items())),
        "semifinal_edges": {k: list(v) for k, v in sorted(GOVERNED_SEMIFINAL_EDGES.items())},
        "g5_automatic_bid_seed": G5_AUTOMATIC_BID_SEED,
        "g5_automatic_bid_count": G5_AUTOMATIC_BID_COUNT,
        "quarterfinal_slot_edges_stated_in_artifact": QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT,
        "quarterfinal_mapping_blocker": QUARTERFINAL_MAPPING_BLOCKER,
    }
