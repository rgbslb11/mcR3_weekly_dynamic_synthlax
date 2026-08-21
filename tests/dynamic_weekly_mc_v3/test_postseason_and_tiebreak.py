import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.committee import require_v3_strength_tiebreak_policy
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.postseason import bracket_games_from_seeds, select_governed_14_team_cfp


def test_committee_strength_tiebreak_requires_explicit_governance():
    with pytest.raises(GovernanceBlock):
        require_v3_strength_tiebreak_policy(None)
    assert require_v3_strength_tiebreak_policy("PRESEASON_STRENGTH") == "PRESEASON_STRENGTH"
    assert require_v3_strength_tiebreak_policy("FINAL_WEEKLY_FOOTBALL_STRENGTH") == "FINAL_WEEKLY_FOOTBALL_STRENGTH"


def test_cfp_uses_cg8_g5_champion_not_highest_ranked_nonchampion():
    order = [
        "SEC_C", "B10_C", "B12_C", "ACC_C", "G5_NONCHAMP", "ND", "P12_C", "X1", "X2", "X3",
        "X4", "X5", "X6", "X7", "X8", "X9", "MW_C", "AAC_C", "A8_C", "ECL_C",
    ]
    champions = {
        "SEC": "SEC_C", "Big Ten": "B10_C", "Big 12": "B12_C", "ACC": "ACC_C",
        "Pac-12": "P12_C", "Mountain West": "MW_C", "American": "AAC_C", "Atlantic-8": "A8_C", "ECL": "ECL_C",
    }
    conf = {t: "Other" for t in order}
    selection = select_governed_14_team_cfp(order, conf, champions)
    assert "P12_C" in selection.seeds.values()
    assert "G5_NONCHAMP" in selection.seeds.values()  # may still make at-large
    assert selection.bid_types["P12_C"] == "AUTO_HIGHEST_RANKED_G5_CHAMPION"
    assert selection.bid_types["G5_NONCHAMP"] == "AT_LARGE"
    assert selection.bid_types["ND"] == "AUTO_NOTRE_DAME_TOP14"
    bracket = bracket_games_from_seeds(selection)
    assert bracket["BYE_1"] == selection.seeds[1]
    assert bracket["PLAYIN_11_14"] == (selection.seeds[11], selection.seeds[14])
