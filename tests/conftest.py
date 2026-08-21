from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ncaaf_engine.domain import Game, MarketObservation, Team
from ncaaf_engine.enums import IdentityStatus, MarketType


@pytest.fixture
def now():
    return datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def verified_teams(now):
    unc = Team(
        school_name="North Carolina",
        nickname="Tar Heels",
        abbreviations=("UNC",),
        covers_team_slug="north-carolina-tar-heels",
        identity_status=IdentityStatus.VERIFIED,
        created_at=now,
        updated_at=now,
    )
    tcu = Team(
        school_name="TCU",
        nickname="Horned Frogs",
        abbreviations=("TCU",),
        covers_team_slug="tcu-horned-frogs",
        identity_status=IdentityStatus.VERIFIED,
        created_at=now,
        updated_at=now,
    )
    return unc, tcu


@pytest.fixture
def unc_tcu_game(now, verified_teams):
    unc, tcu = verified_teams
    return Game(
        covers_game_id="377582",
        season=2026,
        week=1,
        away_team_id=unc.team_id,
        home_team_id=tcu.team_id,
        neutral_site=True,
        scheduled_start=datetime(2026, 8, 29, 16, 0, tzinfo=timezone.utc),
        timezone="America/New_York",
        observed_at=now,
        recorded_at=now,
    )


@pytest.fixture
def tcu_side_observation(now, verified_teams, unc_tcu_game):
    _, tcu = verified_teams
    return MarketObservation(
        game_id=unc_tcu_game.game_id,
        source="Covers",
        market_type=MarketType.SIDE,
        side_team_id=tcu.team_id,
        side_points=Decimal("-6.5"),
        source_game_id="377582",
        observed_at=now,
        recorded_at=now,
        raw_evidence_artifact_id=uuid4(),
    )


@pytest.fixture
def total_observation(now, unc_tcu_game):
    return MarketObservation(
        game_id=unc_tcu_game.game_id,
        source="Covers",
        market_type=MarketType.TOTAL,
        total_points=Decimal("49.5"),
        source_game_id="377582",
        observed_at=now,
        recorded_at=now,
        raw_evidence_artifact_id=uuid4(),
    )
