from pathlib import Path

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.compare_v2 import load_v2_team_probabilities
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import sha256_file

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"


def test_v2_control_is_read_only_reference_with_121_teams():
    cfg = V3Config.from_json(CONFIG)
    before = sha256_file(cfg.inputs.v2_1_control_xlsx)
    rows = load_v2_team_probabilities(cfg.inputs.v2_1_control_xlsx)
    after = sha256_file(cfg.inputs.v2_1_control_xlsx)
    assert len(rows) == 121
    assert before == after
    assert abs(rows["MIA"]["cfp_pct"] - 0.9489) < 1e-12
