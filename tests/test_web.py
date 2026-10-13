import http.client
import json
import threading
from types import SimpleNamespace as NS

import pytest

from contract_qa.budget import ConfigurationError
from contract_qa.web import Application, MAX_BODY, RequestError, make_server


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("contract_qa.web.load_dotenv", lambda: None)
    (tmp_path / "chunks.jsonl").write_text(json.dumps({
        "chunk_id": "a::1", "contract_id": "a", "text": "New York law applies.",
        "char_start": 0, "char_end": 21,
    }) + "\n")
    return Application(tmp_path)


@pytest.fixture
def server(app, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Contract QA</title>")
    (static / "app.js").write_text("console.log('test');")
    (tmp_path / "private.html").write_text("private outside static")
    server = make_server(app, port=0, static_dir=static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, method, path, payload=None, **headers):
    port = server.server_address[1]
    defaults = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
    defaults.update(headers)
    defaults = {key: value for key, value in defaults.items() if value is not None}
    body = json.dumps(payload) if payload is not None else None
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=defaults)
    response = connection.getresponse()
    status, body, response_headers = response.status, response.read().decode(), dict(response.getheaders())
    connection.close()
    return status, body, response_headers


def configure(app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret-never-print")
    (app.data_dir / "pricing.json").write_text(json.dumps({
        "verified_at": "2026-10-13", "source": "https://openai.com/api/pricing/",
        "models": {name: {"input_per_million": 1, "output_per_million": 2,
                          "max_input_tokens": 10000, "temperature_zero": True}
                   for name in ("fake-cheap", "fake-strong")},
        "selected_models": {"cheap": "fake-cheap", "strong": "fake-strong"},
    }))


def test_status_missing_key_and_contracts_still_browsable(server):
    status, body, _ = request(server, "GET", "/api/status")
    assert status == 200
    assert json.loads(body)["configured"] is False
    assert "OPENAI_API_KEY is missing" in body
    status, body, _ = request(server, "GET", "/api/contracts")
    assert status == 200
    assert json.loads(body) == {"contracts": [{"id": "a", "title": "a", "chunk_count": 1}]}


def test_configured_status_contains_only_model_metadata(server, app, monkeypatch):
    configure(app, monkeypatch)
    status, body, _ = request(server, "GET", "/api/status")
    result = json.loads(body)
    assert status == 200
    assert result["configured"] is True
    assert [model["id"] for model in result["models"]] == ["fake-cheap", "fake-strong"]
    assert "sentinel-secret" not in body


def test_missing_api_is_error_never_refusal(server):
    status, body, _ = request(server, "POST", "/api/answer", {"question": "Which law?"})
    assert status == 503
    assert set(json.loads(body)) == {"error"}
    assert "refusal" not in body


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Origin": None},
    {"Host": "evil.example"}, {"Host": "127.0.0.1:1"},
])
def test_cross_origin_and_dns_rebinding_rejected(server, headers):
    status, _, _ = request(server, "POST", "/api/answer", {"question": "Which law?"}, **headers)
    assert status == 403


def test_json_content_type_and_body_limit(server):
    status, _, _ = request(server, "POST", "/api/answer", {"question": "Hi"},
                           **{"Content-Type": "text/plain"})
    assert status == 415
    status, _, _ = request(server, "POST", "/api/answer", {"question": "x" * MAX_BODY})
    assert status == 413


def test_static_path_traversal_and_security_headers(server):
    status, body, headers = request(server, "GET", "/")
    assert status == 200 and "Contract QA" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in headers
    assert request(server, "GET", "/../private.html")[0] == 404
    assert request(server, "GET", "/%2e%2e/private.html")[0] == 404
    assert request(server, "GET", "/api/unknown")[0] == 404
    assert request(server, "OPTIONS", "/api/answer")[0] == 405


@pytest.mark.parametrize("payload", [[], {"question": ""}, {"question": "x" * 4001},
                                     {"question": "Hi", "contract_id": "not-found"},
                                     {"question": "Hi", "contract_id": ["a"]},
                                     {"question": "Hi", "model": 1},
                                     {"question": "Hi", "extra": True}])
def test_invalid_payload_is_400(server, payload):
    status, body, _ = request(server, "POST", "/api/answer", payload)
    assert status == 400
    assert "error" in json.loads(body)


def test_answer_only_uses_retrieved_sources(app, monkeypatch):
    configure(app, monkeypatch)
    calls = []
    returned_chunks = [{**app.chunks[0], "score": .75}]
    app.client = object()
    app.retriever = NS(search=lambda question, **kwargs: calls.append((question, kwargs)) or returned_chunks)
    response = {"answer": "New York.", "citations": [{"chunk_id": "a::1", "quote": "New York"}]}
    monkeypatch.setattr("contract_qa.web.answer_from_chunks", lambda *args, **kwargs: response)
    result = app.ask({"question": " Which law? ", "contract_id": "a", "model": "fake-strong"})
    assert result["response"] == response
    assert result["sources"] == [{"chunk_id": "a::1", "contract_id": "a",
                                   "text": "New York law applies.", "score": .75}]
    assert calls == [("Which law?", {"k": 5, "contract_id": "a"})]
    with pytest.raises(RequestError, match="Unknown model"):
        app.ask({"question": "Which law?", "model": "unapproved-model"})


def test_internal_errors_do_not_leak_keys(server, app, monkeypatch):
    def fail(_):
        raise RuntimeError("sentinel-secret-never-print private-key")
    monkeypatch.setattr(app, "ask", fail)
    status, body, _ = request(server, "POST", "/api/answer", {"question": "Which law?"})
    assert status == 502
    assert "sentinel-secret" not in body and "private-key" not in body


def test_network_binding_is_localhost_only(app):
    with pytest.raises(ValueError, match="localhost"):
        make_server(app, host="0.0.0.0")


def test_api_work_is_serialized_with_shared_budget(app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    configure(app, monkeypatch)
    state = {"active": 0, "maximum": 0}
    def search(*args, **kwargs):
        state["active"] += 1
        state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(.01)
        return [{**app.chunks[0], "score": 1}]
    def answer(*args, **kwargs):
        assert kwargs["budget"] is app.budget
        state["active"] -= 1
        return {"refusal": "No matching provision."}
    app.client = object()
    app.retriever = NS(search=search)
    monkeypatch.setattr("contract_qa.web.answer_from_chunks", answer)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: app.ask({"question": "Question?"}), range(3)))
    assert len(results) == 3
    assert state == {"active": 0, "maximum": 1}
