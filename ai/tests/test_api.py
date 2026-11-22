from __future__ import annotations

from fastapi.testclient import TestClient

from investwatch_ai.config import Settings, get_settings
from investwatch_ai.main import app
from investwatch_ai.schemas import Post


def _client() -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_mode="mock")
    return TestClient(app)


def test_health() -> None:
    body = _client().get("/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["rules"] == 19
    assert body["ollama"] == "disabled"


def test_embed_mock_is_deterministic_and_normalised() -> None:
    client = _client()
    a = client.post("/embed", json={"texts": ["Zysk 100%", "Inny tekst"]}).json()
    b = client.post("/embed", json={"texts": ["Zysk 100%"]}).json()
    assert a["dim"] == 1024
    assert a["embeddings"][0] == b["embeddings"][0]
    assert abs(sum(x * x for x in a["embeddings"][1]) - 1.0) < 1e-6


def test_analyze_endpoint(posts: dict[str, Post]) -> None:
    resp = _client().post("/analyze", json={"post": posts["03"].model_dump(mode="json")})
    assert resp.status_code == 200
    body = resp.json()
    assert {"findings", "embedding", "lang", "timings_ms"} <= body.keys()
    assert body["findings"][0]["module"] == "m2_risk_disclosure"


def test_analyze_rejects_unknown_fields(posts: dict[str, Post]) -> None:
    resp = _client().post(
        "/analyze", json={"post": posts["03"].model_dump(mode="json"), "bogus": 1}
    )
    assert resp.status_code == 422


def test_lite_mode_never_touches_ollama(posts: dict[str, Post]) -> None:
    """AI_MODE=rules + EMBED_ENABLED=false (docker-compose.lite.yml): no Ollama, honest state."""
    lite = Settings(ai_mode="rules", embed_enabled=False, ollama_url="http://127.0.0.1:9")
    app.dependency_overrides[get_settings] = lambda: lite
    client = TestClient(app)
    assert client.get("/health").json()["ollama"] == "disabled"
    assert client.post("/embed", json={"texts": ["x"]}).status_code == 503
    body = client.post(
        "/analyze", json={"post": posts["03"].model_dump(mode="json"), "mode": "rules"}
    ).json()
    assert body["embedding"] is None
    assert body["findings"]
    assert all(f["llm_review"] in ("none", "unavailable") for f in body["findings"])
    assert not any(f["used_llm"] for f in body["findings"])
