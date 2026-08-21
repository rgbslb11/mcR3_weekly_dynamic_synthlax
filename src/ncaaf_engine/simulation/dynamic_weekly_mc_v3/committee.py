from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock


@dataclass(frozen=True)
class CommitteeInputs:
    wins: int
    losses: int
    opponent_win_pct: float
    conference_champion: bool
    strength_tiebreak: float

    @property
    def win_pct(self) -> float:
        n = self.wins + self.losses
        return self.wins / n if n else 0.0


def rank_committee_results_first(
    inputs: dict[str, CommitteeInputs],
    head_to_head_winner: dict[frozenset[str], str],
) -> list[str]:
    """Deterministic V2.1-style results-first board scaffold.

    Pairwise H2H is applied only after win%, OWP, and champion status are tied.
    The caller controls the final strength_tiebreak source so V3 cannot silently
    switch from preseason strength to evolving football strength.
    """
    def base_key(team: str) -> tuple[float, float, int, float, str]:
        x = inputs[team]
        return (-x.win_pct, -x.opponent_win_pct, -int(x.conference_champion), -x.strength_tiebreak, team)

    ordered = sorted(inputs, key=base_key)
    # Stable adjacent H2H correction only when all preceding criteria tie exactly.
    changed = True
    while changed:
        changed = False
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            xa, xb = inputs[a], inputs[b]
            prefix_a = (xa.win_pct, xa.opponent_win_pct, xa.conference_champion)
            prefix_b = (xb.win_pct, xb.opponent_win_pct, xb.conference_champion)
            if prefix_a != prefix_b:
                continue
            winner = head_to_head_winner.get(frozenset((a, b)))
            if winner == b:
                ordered[i], ordered[i + 1] = b, a
                changed = True
    return ordered


def require_v3_strength_tiebreak_policy(policy: str | None) -> str:
    """Retired by ruling R2-COMMITTEE-TB. Refuses every input, including the old ones.

    The question this asked — which hidden strength number breaks a committee
    tie — presumed a board that ranks on a number it never publishes. Both of
    its former answers are now refused by name so a caller cannot drift back to
    the retired framing, and the function is kept rather than deleted so that
    refusal is visible at the old call site.
    """
    from .committee_policy import COMMITTEE_TIEBREAK_POLICY, RETIRED_STRENGTH_SOURCE_VALUES

    if policy in RETIRED_STRENGTH_SOURCE_VALUES:
        raise GovernanceBlock(
            f"committee_tiebreak_strength_source={policy!r} is retired by ruling "
            f"R2-COMMITTEE-TB. Use the structured chain {COMMITTEE_TIEBREAK_POLICY} via "
            "committee_policy.require_committee_tiebreak_policy."
        )
    raise GovernanceBlock(
        "V3 committee final tiebreak strength source is a retired concept. Ruling "
        f"R2-COMMITTEE-TB replaces it with {COMMITTEE_TIEBREAK_POLICY}."
    )
