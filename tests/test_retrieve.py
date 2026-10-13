import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from contract_qa.budget import Budget
from contract_qa.retrieve import EMBEDDING_MODEL, Retriever, cosine_scores, rank_chunks


def chunks(n=3):
    return [{"chunk_id": f"c{i}", "contract_id": "a" if i % 2 == 0 else "b",
             "text": f"This is clause {i}.", "char_start": 0, "char_end": 17}
            for i in range(n)]


class FakeClient:
    def __init__(self):
        self.calls = []
        self.retry_settings = []
        self.embeddings = NS(create=self.create)

    def with_options(self, **options):
        self.retry_settings.append(options)
        return self

    def create(self, *, model, input):
        self.calls.append(input)
        return NS(data=[NS(index=i, embedding=[len(text), i + 1])
                        for i, text in enumerate(input)],
                  usage=NS(prompt_tokens=len(input)))


def setup(tmp_path):
    (tmp_path / "pricing.json").write_text(json.dumps({
        "verified_at": "2026-10-13", "source": "https://openai.com/api/pricing/",
        "models": {EMBEDDING_MODEL: {"input_per_million": 1,
            "output_per_million": 0, "max_input_tokens": 8192}},
    }))
    return FakeClient(), Budget(tmp_path)


def test_exact_cosine_and_zero_vectors():
    scores = cosine_scores([[3, 0], [0, 4], [-2, 0], [0, 0]], [2, 0])
    np.testing.assert_allclose(scores, [1, 0, -1, 0])
    np.testing.assert_allclose(cosine_scores([[1, 2]], [0, 0]), [0])


@pytest.mark.parametrize("matrix,query", [([[1]], [1, 2]), ([[float("nan")]], [1]),
                                         ([[1]], [float("inf")]), ([1, 2], [1])])
def test_invalid_vectors(matrix, query):
    with pytest.raises(ValueError):
        cosine_scores(matrix, query)


def test_top_k_scope_filter_before_ranking_and_ties():
    result = rank_chunks(chunks(), [[1, 1], [1, 0], [1, 1]], [1, 0], k=2, contract_id="a")
    assert [c["chunk_id"] for c in result] == ["c0", "c2"]
    assert result[0]["score"] == pytest.approx(1 / np.sqrt(2))
    assert result[0]["text"] == "This is clause 0."
    assert rank_chunks(chunks(), [[1, 1]] * 3, [1, 0], contract_id="absent") == []
    assert rank_chunks(chunks(), [[1, 1]] * 3, [1, 0], k=0) == []
    assert len(rank_chunks(chunks(), [[1, 1]] * 3, [1, 0], k=100)) == 3


@pytest.mark.parametrize("k", [-1, 1.5, True])
def test_bad_k(k):
    with pytest.raises(ValueError):
        rank_chunks(chunks(), [[1, 1]] * 3, [1, 0], k=k)


def test_batches_of_100_persisted_and_reused(tmp_path):
    client, budget = setup(tmp_path)
    retriever = Retriever(tmp_path, client=client, budget=budget)
    matrix = retriever.build_index(chunks(205))
    assert [len(call) for call in client.calls] == [100, 100, 5]
    assert matrix.shape == (205, 2)
    np.testing.assert_array_equal(np.load(tmp_path / "embeddings.npy"), matrix)
    assert json.loads((tmp_path / "ids.json").read_text()) == [f"c{i}" for i in range(205)]
    before = budget.spent_usd
    Retriever(tmp_path, client=client, budget=budget).build_index(chunks(205))
    assert len(client.calls) == 3
    assert budget.spent_usd == before
    assert all(option == {"max_retries": 0} for option in client.retry_settings)


def test_cache_by_content_not_id_and_only_changed_text_reembedded(tmp_path):
    client, budget = setup(tmp_path)
    retriever = Retriever(tmp_path, client=client, budget=budget)
    data = chunks()
    retriever.build_index(data)
    data[0] = {**data[0], "chunk_id": "new-id"}
    data[1] = {**data[1], "text": "Changed clause text"}
    retriever.build_index(data)
    assert client.calls[1] == ["Changed clause text"]
    assert len(client.calls) == 2
    assert json.loads((tmp_path / "ids.json").read_text())[0] == "new-id"


def test_identical_text_deduplicated(tmp_path):
    client, budget = setup(tmp_path)
    data = chunks()
    for chunk in data:
        chunk["text"] = "Identical clause"
    matrix = Retriever(tmp_path, client=client, budget=budget).build_index(data)
    assert client.calls == [["Identical clause"]]
    np.testing.assert_array_equal(matrix[0], matrix[1])


def test_question_cached_and_unknown_contract_costs_nothing(tmp_path):
    client, budget = setup(tmp_path)
    retriever = Retriever(tmp_path, client=client, budget=budget)
    retriever.build_index(chunks())
    assert retriever.search("Question?", contract_id="missing") == []
    assert len(client.calls) == 1
    result = retriever.search("Question?", contract_id="a")
    retriever.search("Question?", contract_id="b")
    assert len(client.calls) == 2
    assert all(chunk["contract_id"] == "a" for chunk in result)


def test_malformed_api_vectors_and_duplicate_ids(tmp_path):
    client, budget = setup(tmp_path)
    retriever = Retriever(tmp_path, client=client, budget=budget)
    with pytest.raises(ValueError, match="unique"):
        retriever.build_index([chunks()[0], chunks()[0]])
    client.embeddings.create = lambda **_: NS(data=[NS(index=1, embedding=[1, 0])],
                                              usage=NS(prompt_tokens=1))
    with pytest.raises(ValueError, match="indexes"):
        retriever.build_index(chunks(1))


def test_load_jsonl_and_fail_on_corrupt_cache(tmp_path):
    client, budget = setup(tmp_path)
    (tmp_path / "chunks.jsonl").write_text("\n".join(map(json.dumps, chunks())))
    retriever = Retriever(tmp_path, client=client, budget=budget)
    retriever.build_index()
    path = retriever._cache_path(chunks()[0]["text"])
    np.save(path, np.array([np.nan]))
    with pytest.raises(ValueError, match="cache"):
        retriever.build_index()
