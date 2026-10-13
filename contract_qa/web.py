"""A localhost-only contract QA interface using Python's standard library."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv

from .answer import answer_from_chunks
from .budget import Budget, BudgetError, ConfigurationError, Pricing, get_client
from .retrieve import Retriever

MAX_BODY = 64 * 1024
MAX_QUESTION = 4000
STATIC_DIR = Path(__file__).parent / "static"


class RequestError(ValueError):
    pass


class Application:
    """One retriever, client and ledger shared by serialized API work."""

    def __init__(self, data_dir: str | Path = "data"):
        load_dotenv()
        self.data_dir = Path(data_dir)
        self.lock = threading.Lock()
        self.budget = Budget(self.data_dir)
        self.client = None
        self.retriever = None
        path = self.data_dir / "chunks.jsonl"
        self.chunks = [json.loads(line) for line in path.read_text().splitlines()
                       if line.strip()] if path.exists() else []
        self.contract_ids = {chunk["contract_id"] for chunk in self.chunks}

    def status(self) -> dict:
        models = []
        error = None
        try:
            pricing = Pricing(self.data_dir / "pricing.json")
            for tier, label in (("cheap", "Lower cost"), ("strong", "Higher capability")):
                name = pricing.selected(tier)
                if pricing.model(name).get("temperature_zero") is not True:
                    raise ConfigurationError("Model capability is unverified")
                models.append({"id": name, "label": label})
            if len({model["id"] for model in models}) != 2:
                raise ConfigurationError("Two different models are required")
        except ConfigurationError:
            models = []
            error = "Verified model pricing and selections are not configured."
        if not os.getenv("OPENAI_API_KEY"):
            error = "OPENAI_API_KEY is missing. Add it to the environment to enable answers."
        elif not self.chunks:
            error = "Contract data is missing. Run ingestion before asking questions."
        return {"configured": error is None, "models": models, **({"error": error} if error else {})}

    def contracts(self) -> dict:
        counts = Counter(chunk["contract_id"] for chunk in self.chunks)
        return {"contracts": [{"id": name, "title": name.replace("_", " "), "chunk_count": counts[name]}
                              for name in sorted(counts)]}

    def ask(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"question", "contract_id", "model"}:
            raise RequestError("Expected question, contract_id and model fields only.")
        question = payload.get("question")
        contract_id = payload.get("contract_id")
        model = payload.get("model")
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
            raise RequestError(f"Question must contain 1–{MAX_QUESTION} characters.")
        if contract_id is not None and (not isinstance(contract_id, str) or contract_id not in self.contract_ids):
            raise RequestError("Unknown contract ID.")
        if model is not None and not isinstance(model, str):
            raise RequestError("Model must be a configured model ID.")
        status = self.status()
        if not status["configured"]:
            raise ConfigurationError(status["error"])
        allowed = [item["id"] for item in status["models"]]
        if model is not None and model not in allowed:
            raise RequestError("Unknown model ID.")
        model = model or allowed[0]
        with self.lock:
            if self.client is None:
                self.client = get_client()
                self.retriever = Retriever(self.data_dir, client=self.client, budget=self.budget)
            chunks = self.retriever.search(question.strip(), k=5, contract_id=contract_id)
            result = answer_from_chunks(question.strip(), chunks, model,
                                        client=self.client, budget=self.budget)
        sources = [{key: chunk[key] for key in ("chunk_id", "contract_id", "text", "score")}
                   for chunk in chunks]
        return {"response": result, "sources": sources}


def make_server(app: Application, host: str = "127.0.0.1", port: int = 8765,
                static_dir: str | Path = STATIC_DIR) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Bind only to localhost or 127.0.0.1; this server has no remote authentication.")
    static_dir = Path(static_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not log questions, contract clauses or request headers.

        def _trusted_origin(self, require_origin=False):
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host_headers = self.headers.get_all("Host", [])
            if len(host_headers) != 1 or host_headers[0] not in hosts:
                return False
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (require_origin and not origins):
                return False
            return not origins or origins[0] == f"http://{host_headers[0]}"

        def _send(self, status, body: bytes, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode())

        def do_GET(self):
            if not self._trusted_origin():
                return self._json(403, {"error": "Only same-origin localhost requests are allowed."})
            path = urlsplit(self.path).path
            if path == "/api/status":
                return self._json(200, app.status())
            if path == "/api/contracts":
                return self._json(200, app.contracts())
            if path.startswith("/api/"):
                return self._json(404, {"error": "Unknown endpoint."})
            file = (static_dir / unquote(path).lstrip("/")).resolve()
            if path == "/":
                file = static_dir / "index.html"
            if not file.is_relative_to(static_dir) or not file.is_file():
                return self._json(404, {"error": "File not found."})
            if file.suffix not in {".html", ".css", ".js", ".svg", ".png", ".ico"}:
                return self._json(404, {"error": "File not found."})
            self._send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")

        def do_POST(self):
            if not self._trusted_origin(require_origin=True):
                return self._json(403, {"error": "Only same-origin localhost requests are allowed."})
            if urlsplit(self.path).path != "/api/answer":
                return self._json(404, {"error": "Unknown endpoint."})
            if len(self.headers.get_all("Content-Type", [])) != 1 or self.headers.get_content_type() != "application/json":
                return self._json(415, {"error": "Content-Type must be application/json."})
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
                return self._json(400, {"error": "A single Content-Length header is required."})
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"error": "Request body must be 1–65536 bytes."})
            try:
                self.connection.settimeout(10)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = app.ask(payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json(400, {"error": "Request body must be valid UTF-8 JSON."})
            except RequestError as exc:
                return self._json(400, {"error": str(exc)})
            except ConfigurationError:
                return self._json(503, {"error": "API key, verified pricing or contract data is not configured."})
            except BudgetError:
                return self._json(503, {"error": "API budget is unavailable. Check the spending ledger before continuing."})
            except Exception:
                return self._json(502, {"error": "The API request could not be completed. Any pending budget reservation is retained."})
            self._json(200, result)

        def do_OPTIONS(self):
            self._json(405, {"error": "Cross-origin API access is disabled."})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        server = make_server(Application(args.data_dir), args.host, args.port)
        print(f"Contract QA: http://{args.host}:{server.server_address[1]}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError):
        parser.exit(2, "Could not start the local server. Check data files and whether the port is in use.\n")


if __name__ == "__main__":
    main()
