from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ncaaf_engine.api.events import ContractCreated, domain_event_json_schema, validate_event


def contract_event(event_type: str = "contract.created"):
    now = datetime.now(timezone.utc)
    return {
        "event_type": event_type,
        "event_time": now,
        "observed_at": now,
        "recorded_at": now,
        "producer": "contract-service",
        "correlation_id": uuid4(),
        "payload": {
            "contract_id": "NCAAF-2026-W1-UNC-TCU-SIDE-TCU-M6.5",
            "game_id": uuid4(),
            "market_type": "SIDE",
            "source_observation_id": uuid4()
        },
    }


def test_discriminated_event_validation():
    event = validate_event(contract_event())
    assert isinstance(event, ContractCreated)


def test_unknown_event_type_rejected():
    with pytest.raises(ValidationError):
        validate_event(contract_event("unknown.event"))


def test_invalid_payload_rejected():
    data = contract_event()
    data["payload"].pop("source_observation_id")
    with pytest.raises(ValidationError):
        validate_event(data)


def test_event_json_schema_has_discriminator():
    schema = domain_event_json_schema()
    assert "discriminator" in schema
