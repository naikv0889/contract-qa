"""Explicit pricing and a durable, process-safe $5 API spending ledger."""

from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Callable
from uuid import uuid4

CAP_USD = 5
NANODOLLARS = Decimal(1_000_000_000)


class BudgetError(RuntimeError):
    """A request cannot safely fit within the remaining API budget."""


class ConfigurationError(RuntimeError):
    """Live API work needs a key or explicitly verified model pricing."""


def get_client():
    """Do not let SDK retries create unreserved requests or expose key values."""
    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY is missing. Set it in this environment or .env before API work."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigurationError("Install requirements.txt before API work.") from exc
    return OpenAI(max_retries=0)


class Pricing:
    """Load verified USD-per-million rates; never guess current model prices.

    JSON needs verified_at (YYYY-MM-DD), source (official pricing URL), models
    (each with input_per_million, output_per_million, max_input_tokens), and
    optionally selected_models with cheap and strong model IDs.
    """

    def __init__(self, path: str | Path):
        try:
            self.data = json.loads(Path(path).read_text())
            date.fromisoformat(self.data["verified_at"])
            source = self.data["source"]
            if not source.startswith(("https://openai.com/", "https://platform.openai.com/", "https://developers.openai.com/")):
                raise ValueError("Use an official OpenAI pricing source")
            if not isinstance(self.data["models"], dict) or not self.data["models"]:
                raise ValueError("No models configured")
            for model, rates in self.data["models"].items():
                if not isinstance(model, str) or not model:
                    raise ValueError("Invalid model ID")
                for field in ("input_per_million", "output_per_million",
                              *[key for key in ("cached_input_per_million", "cache_write_per_million")
                                if key in rates]):
                    value = Decimal(str(rates[field]))
                    if not value.is_finite() or value < 0:
                        raise ValueError("Rates must be finite and nonnegative")
                limit = rates["max_input_tokens"]
                if type(limit) is not int or limit <= 0:
                    raise ValueError("max_input_tokens must be a positive integer")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as exc:
            raise ConfigurationError(
                f"Verified pricing is required at {path}; see README.md for its schema."
            ) from exc

    def model(self, name: str) -> dict:
        try:
            return self.data["models"][name]
        except KeyError as exc:
            raise ConfigurationError(f"No verified pricing configured for model {name!r}.") from exc

    def selected(self, tier: str = "cheap") -> str:
        name = self.data.get("selected_models", {}).get(tier)
        if not isinstance(name, str) or not name:
            raise ConfigurationError(f"Set selected_models.{tier} in pricing.json first.")
        self.model(name)
        return name

    def nanodollars(self, model: str, input_tokens: int, output_tokens: int = 0, *,
                    cached_tokens: int = 0, cache_write_tokens: int = 0,
                    reserve: bool = False) -> int:
        rates = self.model(model)
        for tokens in (input_tokens, output_tokens, cached_tokens, cache_write_tokens):
            if type(tokens) is not int or tokens < 0:
                raise ValueError("Token counts must be nonnegative integers")
        if cached_tokens + cache_write_tokens > input_tokens:
            raise ValueError("Cache token counts exceed total input")
        normal = Decimal(str(rates["input_per_million"]))
        cached = Decimal(str(rates.get("cached_input_per_million", normal)))
        written = Decimal(str(rates.get("cache_write_per_million", normal)))
        input_cost = (input_tokens * max(normal, cached, written) if reserve else
                      (input_tokens - cached_tokens - cache_write_tokens) * normal
                      + cached_tokens * cached + cache_write_tokens * written)
        usd = (input_cost + Decimal(output_tokens) *
               Decimal(str(rates["output_per_million"]))) / 1_000_000
        return int((usd * NANODOLLARS).to_integral_value(rounding=ROUND_CEILING))


class Budget:
    """Reserve before a call, replace the reservation with measured usage after.

    SQLite serializes competing reservations. Crashes, network errors and absent
    usage retain the entire reservation: they may have been billed. Never delete
    this ledger during the project. Set CONTRACT_QA_BUDGET_PATH to one absolute
    path shared by every clone when running the project from multiple checkouts.
    """

    def __init__(self, data_dir: str | Path = "data", *, pricing: Pricing | None = None,
                 cap_usd: float = CAP_USD):
        if not math.isfinite(cap_usd) or not 0 < cap_usd <= CAP_USD:
            raise ValueError("The project budget must be positive and at most $5")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(os.environ.get("CONTRACT_QA_BUDGET_PATH", self.data_dir / "budget.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pricing = pricing
        self.cap = int(Decimal(str(cap_usd)) * NANODOLLARS)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, model TEXT NOT NULL, cost INTEGER NOT NULL,
                status TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS cache_usage (
                request_id TEXT PRIMARY KEY, cached_tokens INTEGER NOT NULL,
                cache_write_tokens INTEGER NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    @property
    def pricing(self) -> Pricing:
        if self._pricing is None:
            self._pricing = Pricing(self.data_dir / "pricing.json")
        return self._pricing

    @property
    def spent_usd(self) -> float:
        with self._connect() as db:
            amount = db.execute("SELECT COALESCE(SUM(cost), 0) FROM requests").fetchone()[0]
        return amount / float(NANODOLLARS)

    def reserve(self, model: str, input_tokens: int, output_tokens: int = 0) -> str:
        cost = self.pricing.nanodollars(model, input_tokens, output_tokens, reserve=True)
        request_id = uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM requests WHERE status = 'underreserved' LIMIT 1").fetchone():
                raise BudgetError("Budget is blocked after an underestimated request; review pricing and ledger.")
            spent = db.execute("SELECT COALESCE(SUM(cost), 0) FROM requests").fetchone()[0]
            if spent + cost > self.cap:
                raise BudgetError(
                    f"Request exceeds the ${self.cap / float(NANODOLLARS):g} API cap; "
                    f"${spent / float(NANODOLLARS):.6f} is spent or reserved."
                )
            db.execute("INSERT INTO requests VALUES (?, ?, ?, 'reserved', NULL, NULL)",
                       (request_id, model, cost))
        return request_id

    def settle(self, request_id: str, input_tokens: int, output_tokens: int = 0, *,
               cached_tokens: int = 0, cache_write_tokens: int = 0):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT model, cost, status FROM requests WHERE id = ?",
                             (request_id,)).fetchone()
            if row is None or row[2] != "reserved":
                raise BudgetError("Reservation is missing or already settled")
            cost = self.pricing.nanodollars(row[0], input_tokens, output_tokens,
                                            cached_tokens=cached_tokens,
                                            cache_write_tokens=cache_write_tokens)
            db.execute("INSERT INTO cache_usage VALUES (?, ?, ?)",
                       (request_id, cached_tokens, cache_write_tokens))
            if cost > row[1]:
                # Retain the actual charge even if configuration was incorrect.
                db.execute("UPDATE requests SET cost = ?, status = 'underreserved', "
                           "input_tokens = ?, output_tokens = ? WHERE id = ?",
                           (cost, input_tokens, output_tokens, request_id))
                db.commit()
                raise BudgetError("API usage exceeded its configured upper bound; stop and verify pricing/limits.")
            db.execute("UPDATE requests SET cost = ?, status = 'settled', "
                       "input_tokens = ?, output_tokens = ? WHERE id = ?",
                       (cost, input_tokens, output_tokens, request_id))

    def run(self, model: str, input_upper: int, output_upper: int,
            call: Callable):
        """Make exactly one reserved request. Unknown usage stays fully charged."""
        request_id = self.reserve(model, input_upper, output_upper)
        response = call()  # On any exception, the durable reservation remains.
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", None))
        output_tokens = getattr(usage, "completion_tokens",
                                getattr(usage, "output_tokens", 0 if output_upper == 0 else None))
        if type(input_tokens) is not int or type(output_tokens) is not int:
            raise BudgetError("API did not report usage; full request reservation is retained.")
        rates = self.pricing.model(model)
        cached = written = 0
        if "cached_input_per_million" in rates or "cache_write_per_million" in rates:
            details = getattr(usage, "input_tokens_details", None)
            cached = getattr(details, "cached_tokens", None)
            written = getattr(details, "cache_write_tokens", None)
            if (type(cached) is not int or type(written) is not int or
                    min(cached, written) < 0 or cached + written > input_tokens):
                raise BudgetError("API cache usage is invalid; full reservation is retained.")
        self.settle(request_id, input_tokens, output_tokens,
                    cached_tokens=cached, cache_write_tokens=written)
        return response


def available_models(client=None) -> list[str]:
    """List key-visible models, without guessing which is strongest/current."""
    client = client or get_client()
    return sorted(model.id for model in client.models.list())


def validate_selection(pricing: Pricing, client=None) -> dict[str, str]:
    """Check explicitly chosen models against the key; do not infer capability."""
    available = set(available_models(client))
    selected = {tier: pricing.selected(tier) for tier in ("cheap", "strong")}
    if len(set(selected.values())) != 2:
        raise ConfigurationError("Choose two different chat models.")
    for name in selected.values():
        if name not in available:
            raise ConfigurationError(f"Selected model {name!r} is not available to this key.")
        if pricing.model(name).get("temperature_zero") is not True:
            raise ConfigurationError(f"Verify chat JSON mode and temperature=0 for {name!r}.")
    return selected


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--check-models", action="store_true")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    try:
        if args.list_models:
            print("\n".join(available_models()))
        elif args.check_models:
            print(json.dumps(validate_selection(Pricing(Path(args.data_dir) / "pricing.json")), indent=2))
        else:
            print(f"Spent or conservatively reserved: ${Budget(args.data_dir).spent_usd:.6f} / $5")
    except ConfigurationError as exc:
        parser.exit(2, f"{exc}\n")
    except Exception:
        parser.exit(2, "Model listing failed. Check API connectivity and key permissions.\n")
