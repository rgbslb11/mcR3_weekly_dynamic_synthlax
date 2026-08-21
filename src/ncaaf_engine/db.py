from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str = "sqlite+pysqlite:///:memory:"):
    return create_engine(url, future=True)


def make_session_factory(url: str = "sqlite+pysqlite:///:memory:"):
    engine = make_engine(url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)
