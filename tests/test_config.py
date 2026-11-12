from src.config import Settings


def test_from_env_reads_variables(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://x:1")
    monkeypatch.setenv("REDIS_PORT", "6390")
    monkeypatch.setenv("NEO4J_USERNAME", "u")
    s = Settings.from_env(dotenv_path=None)
    assert s.mongo_uri == "mongodb://x:1"
    assert s.redis_port == 6390
    assert s.neo4j_user == "u"


def test_defaults_match_docker_compose():
    s = Settings()
    assert s.mongo_db == "techstore"
    assert s.neo4j_password == "techstore123"
    assert s.session_ttl == 1800
    assert s.cache_ttl == 300
    assert s.cart_ttl == 604800
