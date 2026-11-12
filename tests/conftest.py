import fakeredis
import mongomock
import pytest

from src.observability import OpLog


@pytest.fixture
def db():
    return mongomock.MongoClient().techstore


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def oplog():
    return OpLog()
