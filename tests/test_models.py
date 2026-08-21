from ncaaf_engine.db import Base, make_engine
import ncaaf_engine.models  # noqa: F401


def test_schema_creates_on_sqlite():
    engine = make_engine()
    Base.metadata.create_all(engine)
    assert "contracts" in Base.metadata.tables
    assert "fills" in Base.metadata.tables
    assert "ledger_entries" in Base.metadata.tables
    assert "outbox_events" in Base.metadata.tables
    Base.metadata.drop_all(engine)
