import json
from types import SimpleNamespace as NS

import pytest

from contract_qa.answer import answer, answer_from_chunks, normalize_quote, verify_response
from contract_qa.budget import Budget, ConfigurationError

CHUNKS = [{"chunk_id": "contract-1:law", "contract_id": "contract-1",
           "text": "This Agreement is governed by the laws of New York.\nNo jury trial."}]
VALID = {"answer": "New York law governs.", "citations": [
    {"chunk_id": "contract-1:law", "quote": "governed by the laws of New York."}]}


def test_exact_match_and_normalized_quote():
    assert verify_response(json.dumps(VALID), CHUNKS) == VALID
    value = {**VALID, "citations": [{"chunk_id": "contract-1:law",
                                    "quote": "governed BY\n the    laws of new York."}]}
    assert verify_response(value, CHUNKS) == value
    assert normalize_quote(" A\n\tB  ") == "a b"


@pytest.mark.parametrize("value", [
    "not json", "```json\n{}\n```", "[]", "null", "{", None, {},
    {"answer": "yes"}, {"refusal": ""}, {"refusal": " \n"}, {"refusal": 1},
    {"answer": "", "citations": VALID["citations"]},
    {"answer": " \t", "citations": VALID["citations"]},
    {"answer": 1, "citations": VALID["citations"]},
    {"answer": "yes", "citations": []},
    {"answer": "yes", "citations": None},
    {"answer": "yes", "citations": [None]},
    {**VALID, "refusal": "also refusing"}, {**VALID, "extra": "not allowed"},
    '{"answer":"yes","answer":"no","citations":[]}',
    '{"answer":NaN,"citations":[]}',
])
def test_malformed_responses_refuse(value):
    assert "refusal" in verify_response(value, CHUNKS)


@pytest.mark.parametrize("citation", [
    {"chunk_id": "contract-1:law", "quote": "governed by California law"},
    {"chunk_id": "another-contract:law", "quote": "New York"},
    {"chunk_id": "contract-1:law", "quote": ""},
    {"chunk_id": "contract-1:law", "quote": " \n"},
    {"chunk_id": "contract-1:law", "quote": None},
    {"chunk_id": ["contract-1:law"], "quote": "New York"},
    {"chunk_id": "contract-1:law", "quote": "New York", "extra": "ignored?"},
    {"chunk_id": "contract-1:law"},
])
def test_any_invalid_citation_refuses_whole_response(citation):
    value = {**VALID, "citations": VALID["citations"] + [citation]}
    assert "refusal" in verify_response(value, CHUNKS)


def test_refusal_preserved_and_duplicate_source_ids_rejected():
    refusal = {"refusal": "The provided clauses do not address exclusivity."}
    assert verify_response(refusal, CHUNKS) == refusal
    assert "refusal" in verify_response(VALID, CHUNKS * 2)


class FakeClient:
    def __init__(self, content=VALID, finish_reason="stop"):
        self.calls = []
        self.retry_settings = []
        self.content = content
        self.finish_reason = finish_reason
        self.chat = NS(completions=NS(create=self.create))

    def with_options(self, **options):
        self.retry_settings.append(options)
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return NS(usage=NS(prompt_tokens=42, completion_tokens=10), choices=[
            NS(finish_reason=self.finish_reason, message=NS(content=json.dumps(self.content)))])


def setup(tmp_path, **rates):
    (tmp_path / "pricing.json").write_text(json.dumps({
        "verified_at": "2026-10-13", "source": "https://openai.com/api/pricing/",
        "models": {"fake-chat": {"input_per_million": 1, "output_per_million": 2,
                                 "max_input_tokens": 10000, "temperature_zero": True, **rates}},
        "selected_models": {"cheap": "fake-chat"},
    }))
    return Budget(tmp_path)


def test_api_request_fixed_temperature_json_and_chunks(tmp_path):
    budget = setup(tmp_path)
    client = FakeClient()
    result = answer_from_chunks("Which law?", CHUNKS, "fake-chat", client=client, budget=budget)
    assert result == VALID
    request = client.calls[0]
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}
    assert request["max_completion_tokens"] == 1024
    assert request["model"] == "fake-chat"
    prompt = json.loads(request["messages"][1]["content"])
    assert prompt["clauses"] == [{"chunk_id": c["chunk_id"], "text": c["text"]} for c in CHUNKS]
    assert client.retry_settings == [{"max_retries": 0}]
    assert budget.spent_usd == pytest.approx(.000062)


def test_search_exactly_top_five_and_scoped(tmp_path):
    budget = setup(tmp_path)
    calls = []
    retriever = NS(budget=budget, search=lambda question, **kw: calls.append((question, kw)) or CHUNKS)
    assert answer("Which law?", "contract-1", retriever=retriever, client=FakeClient()) == VALID
    assert calls == [("Which law?", {"k": 5, "contract_id": "contract-1"})]


@pytest.mark.parametrize("finish_reason", ["length", "content_filter", "tool_calls"])
def test_incomplete_or_filtered_response_refuses(tmp_path, finish_reason):
    result = answer_from_chunks("Which law?", CHUNKS, "fake-chat",
                                client=FakeClient(finish_reason=finish_reason), budget=setup(tmp_path))
    assert "refusal" in result


def test_empty_retrieval_is_free_and_refuses(tmp_path):
    budget = setup(tmp_path)
    client = FakeClient()
    assert "refusal" in answer_from_chunks("Question?", [], None, client=client, budget=budget)
    assert client.calls == []
    assert budget.spent_usd == 0


def test_unsupported_temperature_never_sent(tmp_path):
    client = FakeClient()
    with pytest.raises(ConfigurationError, match="temperature=0"):
        answer_from_chunks("Question?", CHUNKS, "fake-chat", client=client,
                           budget=setup(tmp_path, temperature_zero=False))
    assert client.calls == []


def test_more_than_five_chunks_rejected(tmp_path):
    with pytest.raises(ValueError, match="top five"):
        answer_from_chunks("Question?", CHUNKS * 6, "fake-chat",
                           client=FakeClient(), budget=setup(tmp_path))


def test_bad_model_fails_before_retrieval(tmp_path):
    budget = setup(tmp_path)
    calls = []
    retriever = NS(budget=budget, search=lambda *a, **kw: calls.append(True))
    with pytest.raises(ConfigurationError, match="No verified pricing"):
        answer("Which law?", model="typo", retriever=retriever, client=FakeClient())
    assert calls == []
    assert budget.spent_usd == 0
