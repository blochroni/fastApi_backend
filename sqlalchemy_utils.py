from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

_is_init = False
engine = None


def is_init():
    return _is_init


def init(pg_conn_string):
    global engine, _is_init
    engine = create_engine(pg_conn_string)
    _is_init = True


def get_engine():
    assert is_init(), "please init the module before using this function"
    return engine


def get_session_maker():
    assert is_init(), "please init the module before using this function"
    return sessionmaker(bind=engine)

