from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from . import config

_kw = {"connect_args": {"check_same_thread": False}} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, **_kw)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
