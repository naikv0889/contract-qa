import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS

import pytest

from contract_qa.budget import Budget, BudgetError, ConfigurationError, Pricing, available_models, get_client


def make_pricing(tmp_path, **rates):
    value = {"verified_at": "2026-10-13", "source": "https://openai.com/api/pricing/",
             "models": {"test": {"input_per_million": 1, "output_per_million": 2,
                                   "max_input_tokens": 10000, **rates}},
             "selected_models": {"cheap": "test"}}
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(value))
    return Pricing(path)


def test_reserve_settle_and_reopen(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path))
    token = budget.reserve("test", 1000, 100)
    assert budget.spent_usd == pytest.approx(.0012)
    budget.settle(token, 10, 4)
    assert Budget(tmp_path).spent_usd == pytest.approx(.000018)
    with pytest.raises(BudgetError, match="already settled"):
        budget.settle(token, 10, 4)


def test_cap_prevents_request(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path), cap_usd=.001)
    called = []
    with pytest.raises(BudgetError, match="exceeds"):
        budget.run("test", 1001, 0, lambda: called.append(True))
    assert called == []
    assert budget.spent_usd == 0
    budget.reserve("test", 1000)
    with pytest.raises(BudgetError):
        Budget(tmp_path, cap_usd=.001).reserve("test", 1)


def test_errors_and_missing_usage_retain_reservation(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path))
    def timeout():
        raise TimeoutError("Unknown whether API billed")
    with pytest.raises(TimeoutError):
        budget.run("test", 1000, 10, timeout)
    with pytest.raises(BudgetError, match="did not report usage"):
        budget.run("test", 1000, 10, lambda: NS())
    assert budget.spent_usd == pytest.approx(.00204)


def test_usage_actual_counts(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path))
    response = NS(usage=NS(prompt_tokens=4, completion_tokens=2))
    assert budget.run("test", 100, 50, lambda: response) is response
    assert budget.spent_usd == pytest.approx(.000008)


def test_underreservation_persists_and_blocks_future_calls(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path))
    token = budget.reserve("test", 1)
    with pytest.raises(BudgetError, match="exceeded"):
        budget.settle(token, 10)
    assert Budget(tmp_path).spent_usd == pytest.approx(.00001)
    with pytest.raises(BudgetError, match="blocked"):
        Budget(tmp_path).reserve("test", 1)


def test_concurrent_reservations_share_cap(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path), cap_usd=.01)
    def reserve(_):
        try:
            Budget(tmp_path, cap_usd=.01).reserve("test", 6000)
            return True
        except BudgetError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(4))) == 1
    assert budget.spent_usd == pytest.approx(.006)


@pytest.mark.parametrize("rate", [-1, "NaN", "Infinity", "not a number", None])
def test_bad_rates_fail_closed(tmp_path, rate):
    with pytest.raises(ConfigurationError):
        make_pricing(tmp_path, input_per_million=rate)


@pytest.mark.parametrize("cap", [0, -1, 5.01, 10, float("nan"), float("inf")])
def test_cannot_raise_budget_above_five(tmp_path, cap):
    with pytest.raises(ValueError):
        Budget(tmp_path, cap_usd=cap)


def test_explicit_configuration_required(tmp_path):
    budget = Budget(tmp_path)
    with pytest.raises(ConfigurationError, match="Verified pricing"):
        budget.reserve("anything", 1)
    pricing = make_pricing(tmp_path)
    assert pricing.selected() == "test"
    with pytest.raises(ConfigurationError):
        pricing.selected("strong")
    with pytest.raises(ConfigurationError):
        pricing.model("unknown")


def test_missing_key_has_clear_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is missing"):
        get_client()


def test_list_only_available_models():
    client = NS(models=NS(list=lambda: [NS(id="b"), NS(id="a")]))
    assert available_models(client) == ["a", "b"]


def test_rounds_up_small_costs(tmp_path):
    pricing = make_pricing(tmp_path, input_per_million="0.00001")
    assert pricing.nanodollars("test", 1) == 1


def test_explicit_shared_ledger_across_data_directories(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("CONTRACT_QA_BUDGET_PATH", str(tmp_path / "shared.sqlite3"))
    Budget(first, pricing=make_pricing(first)).reserve("test", 1000)
    assert Budget(second).spent_usd == pytest.approx(.001)


def test_selection_is_explicit_and_key_visible(tmp_path):
    from contract_qa.budget import validate_selection
    pricing = make_pricing(tmp_path, temperature_zero=True)
    pricing.data["models"]["strong"] = pricing.model("test").copy()
    pricing.data["selected_models"]["strong"] = "strong"
    client = NS(models=NS(list=lambda: [NS(id="test"), NS(id="strong")]))
    assert validate_selection(pricing, client) == {"cheap": "test", "strong": "strong"}
    pricing.data["selected_models"]["strong"] = "absent"
    pricing.data["models"]["absent"] = pricing.model("test").copy()
    with pytest.raises(ConfigurationError, match="not available"):
        validate_selection(pricing, client)


def test_chat_missing_output_usage_retains_full_reservation(tmp_path):
    budget = Budget(tmp_path, pricing=make_pricing(tmp_path))
    with pytest.raises(BudgetError, match="did not report usage"):
        budget.run("test", 100, 50, lambda: NS(usage=NS(prompt_tokens=4)))
    assert budget.spent_usd == pytest.approx(.0002)


def test_default_cap_is_five_and_preserves_existing_ledger(tmp_path):
    pricing = make_pricing(tmp_path)
    budget = Budget(tmp_path, pricing=pricing)
    budget.reserve("test", 4_000_000)
    reopened = Budget(tmp_path, pricing=pricing)
    assert reopened.spent_usd == 4
    reopened.reserve("test", 1_000_000)
    with pytest.raises(BudgetError, match=r"\$5 API cap"):
        reopened.reserve("test", 1)
    assert reopened.spent_usd == 5


def test_cache_write_upper_bound_and_actual_cache_accounting(tmp_path):
    pricing=make_pricing(tmp_path,input_per_million=2,output_per_million=10,
                         cached_input_per_million=.2,cache_write_per_million=2.5)
    budget=Budget(tmp_path,pricing=pricing)
    response=NS(usage=NS(input_tokens=1000,output_tokens=100,
                        input_tokens_details=NS(cached_tokens=600,cache_write_tokens=300)))
    assert budget.run('test',1000,100,lambda:response) is response
    assert pricing.nanodollars('test',1000,100,reserve=True)==3_500_000
    assert budget.spent_usd==pytest.approx(.00207)
    with sqlite3.connect(budget.path) as db:
        assert db.execute('SELECT cached_tokens,cache_write_tokens FROM cache_usage').fetchone()==(600,300)


@pytest.mark.parametrize('details',[None,NS(cached_tokens=-1,cache_write_tokens=0),
    NS(cached_tokens=500,cache_write_tokens=501),NS(cached_tokens=True,cache_write_tokens=0)])
def test_invalid_cache_usage_keeps_reservation(tmp_path,details):
    pricing=make_pricing(tmp_path,input_per_million=2,output_per_million=10,
                         cached_input_per_million=.2,cache_write_per_million=2.5)
    budget=Budget(tmp_path,pricing=pricing)
    with pytest.raises(BudgetError,match='cache usage'):
        budget.run('test',1000,100,lambda:NS(usage=NS(input_tokens=1000,output_tokens=10,
                                                   input_tokens_details=details)))
    assert budget.spent_usd==pytest.approx(.0035)
