"""Offline fixtures exercise every metric without an API key or provider calls."""

import json
from pathlib import Path

import pytest

from scripts.build_eval import QUESTIONS, build_items
from scripts.run_eval import (
    citations_verified,
    contains_annotation,
    evaluate_items,
    model_filename,
    normalize_text,
    score_item,
    summarize,
    write_result,
    write_summary,
)


def fixture_source():
    qas = [
        {
            "id": f"original-title__{category}",
            "question": "This source wording must not replace the fixed question.",
            "answers": [{"text": "New York", "answer_start": 999_999}] if index == 0 else [],
        }
        for index, category in enumerate(QUESTIONS)
    ]
    source = {"data": [{"title": "original-title", "paragraphs": [{"context": "New York", "qas": qas}]}]}
    manifest = [{"contract_id": "cuad-001", "cuad_title": "original-title"}]
    return source, manifest


def item(answerable=True):
    return {
        "id": "cuad-001__Governing Law",
        "contract_id": "cuad-001",
        "category": "Governing Law",
        "question": QUESTIONS["Governing Law"],
        "annotated_answers": ["NEW\n YORK"] if answerable else [],
        "expect_refusal": not answerable,
    }


def chunk(chunk_id="cuad-001:1", text="The law of New York governs."):
    return {"chunk_id": chunk_id, "contract_id": "cuad-001", "text": text, "score": 0.9}


def response(chunk_id="cuad-001:1", quote="law of new\t York"):
    return {"answer": "New York.", "citations": [{"chunk_id": chunk_id, "quote": quote}]}


def test_build_fixed_named_questions_and_preserve_annotation_text():
    source, manifest = fixture_source()
    rows = build_items(source, manifest)
    assert [row["category"] for row in rows] == list(QUESTIONS)
    assert [row["question"] for row in rows] == list(QUESTIONS.values())
    assert all(row["contract_id"] == "cuad-001" for row in rows)
    assert rows[0]["annotated_answers"] == ["New York"]
    assert rows[0]["expect_refusal"] is False
    assert all(row["expect_refusal"] for row in rows[1:])
    assert "answer_start" not in json.dumps(rows)
    assert rows == build_items(source, manifest)


def test_build_joins_manifest_not_source_or_title_sort_order():
    source, manifest = fixture_source()
    source["data"].insert(0, {"title": "Unselected"})
    assert len(build_items(source, manifest)) == 5


@pytest.mark.parametrize("problem", ["title", "missing", "duplicate_category", "duplicate_contract", "blank_annotation"])
def test_invalid_source_never_becomes_refusal_ground_truth(problem):
    source, manifest = fixture_source()
    qas = source["data"][0]["paragraphs"][0]["qas"]
    if problem == "title":
        manifest[0]["cuad_title"] = "Wrong title"
    elif problem == "missing":
        qas.pop()
    elif problem == "duplicate_category":
        qas.append(qas[0])
    elif problem == "duplicate_contract":
        manifest.append(manifest[0])
    else:
        qas[0]["answers"] = [{"text": " \n "}]
    with pytest.raises(ValueError):
        build_items(source, manifest)


def test_text_matching_ignores_case_and_whitespace_not_punctuation():
    assert normalize_text("  NEW\tYork\n law  ") == "new york law"
    assert contains_annotation(chunk(), ["Wrong answer", "NEW\n YORK"])
    assert not contains_annotation(chunk(), ["", " ", "New-York"])


def test_retrieval_hit_can_be_in_fifth_chunk():
    chunks = [chunk(f"cuad-001:{i}", "No law here.") for i in range(4)] + [chunk()]
    scored = score_item(item(), chunks, {"refusal": "Unsupported."})
    assert scored["retrieval_hit"] is True
    assert scored["refused"] is True
    assert scored["grounded"] is False


def test_grounding_requires_gold_containing_cited_chunk():
    gold = chunk()
    irrelevant = chunk("cuad-001:2", "Notices shall be sent by mail.")
    scored = score_item(item(), [gold, irrelevant], response("cuad-001:2", "sent by mail"))
    assert scored["retrieval_hit"] is True
    assert scored["citations_verified"] is True
    assert scored["grounded"] is False
    scored = score_item(item(), [gold, irrelevant], response())
    assert scored["grounded"] is True


def test_grounding_uses_any_annotation_and_any_valid_citation():
    expected = item()
    expected["annotated_answers"] = ["California", "New York"]
    unrelated = chunk("cuad-001:2", "Notices by mail.")
    answer = response()
    answer["citations"].insert(0, {"chunk_id": "cuad-001:2", "quote": "Notices"})
    assert score_item(expected, [chunk(), unrelated], answer)["grounded"] is True


@pytest.mark.parametrize("bad_response", [
    response(quote="Fabricated text"),
    response(chunk_id="not-retrieved"),
    response(quote=" "),
    {"answer": "New York.", "citations": []},
    {"answer": "New York.", "citations": "invalid"},
    {"answer": " ", "citations": response()["citations"]},
    {"answer": "New York.", "citations": [{"chunk_id": [], "quote": "law"}]},
    {"answer": "New York.", "citations": [{"chunk_id": "cuad-001:1", "quote": 1}]},
    {"answer": "New York.", "citations": [None]},
    {**response(), "extra": "Invalid schema"},
    {"refusal": "No evidence."},
    "malformed json",
])
def test_invalid_citation_or_schema_cannot_be_grounded(bad_response):
    assert citations_verified(bad_response, [chunk()]) is False
    assert score_item(item(), [chunk()], bad_response)["grounded"] is False


def test_one_bad_quote_invalidates_all_citations():
    answer = response()
    answer["citations"].append({"chunk_id": "cuad-001:1", "quote": "Fabricated"})
    assert not citations_verified(answer, [chunk()])
    assert not score_item(item(), [chunk()], answer)["grounded"]


def test_duplicate_chunk_ids_do_not_verify():
    assert not citations_verified(response(), [chunk(), chunk()])


def test_all_metric_denominators_and_cost():
    records = [
        score_item(item(), [chunk()], response()),
        score_item(item(), [chunk()], {"refusal": "Unsupported."}),
        score_item(item(), [chunk(text="Unrelated clause.")], response(quote="Unrelated")),
        score_item(item(False), [chunk()], {"refusal": "No clause."}),
        score_item(item(False), [chunk()], response()),
    ]
    summary = summarize(records, 0.12345)
    assert summary == {
        "evaluated_items": 5,
        "answerable_items": 3,
        "expect_refusal_items": 2,
        "recall_at_5": 2 / 3,
        "refusal_accuracy": 1 / 2,
        "grounded_answer_rate": 1 / 3,
        "false_refusal_rate": 1 / 3,
        "cost_usd": 0.12345,
    }


def test_missing_denominators_are_none_not_zero():
    empty = summarize([], 0.0)
    assert all(empty[key] is None for key in (
        "recall_at_5", "refusal_accuracy", "grounded_answer_rate", "false_refusal_rate"
    ))
    only_answerable = summarize([score_item(item(), [chunk()], response())], 0.0)
    assert only_answerable["refusal_accuracy"] is None
    only_absent = summarize([score_item(item(False), [], {"refusal": "Absent."})], 0.0)
    assert only_absent["recall_at_5"] is None
    assert only_absent["false_refusal_rate"] is None
    assert only_absent["grounded_answer_rate"] is None
    assert only_absent["refusal_accuracy"] == 1.0


def test_inconsistent_labels_rejected():
    bad = item()
    bad["expect_refusal"] = True
    with pytest.raises(ValueError, match="expect_refusal"):
        score_item(bad, [], {"refusal": "Absent."})


def test_evaluation_scopes_retrieval_and_reuses_exact_chunks():
    chunks = [chunk()]
    calls = []

    def search(question, k, contract_id):
        calls.append((question, k, contract_id))
        return chunks

    def answer(question, retrieved, model):
        assert retrieved is chunks
        assert model == "fixture-model"
        return response()

    records = list(evaluate_items([item()], "fixture-model", search, answer))
    assert calls == [(item()["question"], 5, "cuad-001")]
    assert records[0]["grounded"]


@pytest.mark.parametrize("chunks", [
    [{**chunk(), "contract_id": "different-contract"}],
    [chunk() for _ in range(6)],
])
def test_evaluation_rejects_unscoped_or_excess_retrieval(chunks):
    def answer(*args, **kwargs):
        pytest.fail("Answer must not receive invalid retrieval")

    with pytest.raises(ValueError, match="Retrieval"):
        list(evaluate_items([item()], "fixture", lambda *args, **kwargs: chunks, answer))


def test_provider_error_is_not_scored_as_a_refusal():
    def unavailable(*args, **kwargs):
        raise RuntimeError("Provider unavailable")

    with pytest.raises(RuntimeError, match="Provider unavailable"):
        list(evaluate_items([item()], "fixture", lambda *args, **kwargs: [chunk()], unavailable))


def test_result_checkpoint_and_summary_are_honest(tmp_path):
    unrun = write_summary(tmp_path)
    assert unrun.count("selection pending") == 2
    assert "0.0%" not in unrun
    report = {
        "model": "fixture-model",
        "status": "completed",
        "expected_items": 1,
        "metrics": summarize([score_item(item(), [chunk()], response())], 0.001),
    }
    path = tmp_path / model_filename(report["model"])
    write_result(path, report)
    assert json.loads(path.read_text()) == report
    assert not list(tmp_path.glob("*.tmp"))
    text = write_summary(tmp_path, {"cheap": "fixture-model", "strong": "pending-model"})
    assert "fixture-model | Completed (1) | 100.0% | N/A | 100.0% | 0.0% | $0.001000" in text
    assert "pending-model | Not run | N/A" in text
    assert "selection pending" not in text
    report["status"] = "incomplete"
    report["expected_items"] = 125
    write_result(path, report)
    text = write_summary(tmp_path, {"cheap": "fixture-model", "strong": "pending-model"})
    assert "Incomplete (1/125) | N/A | N/A | N/A | N/A" in text
    assert "100.0%" not in text


@pytest.mark.parametrize("unsafe", ["../outside", "/tmp/model", "model/name", "", ".hidden", "a\nb"])
def test_result_filename_cannot_escape_results(unsafe):
    with pytest.raises(ValueError):
        model_filename(unsafe)


def test_real_eval_has_exactly_125_items_from_25_contracts():
    path = Path(__file__).resolve().parents[1] / "data/eval.jsonl"
    if not path.exists():
        pytest.skip("Run scripts/build_eval.py to build the committed benchmark")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len({row["id"] for row in rows}) == 125
    contracts = {row["contract_id"] for row in rows}
    assert len(contracts) == 25
    manifest = json.loads((path.parent / "contracts/manifest.json").read_text(encoding="utf-8"))
    assert contracts == {selected["contract_id"] for selected in manifest}
    for contract_id in contracts:
        assert {row["category"] for row in rows if row["contract_id"] == contract_id} == set(QUESTIONS)
    assert all(row["expect_refusal"] == (not row["annotated_answers"]) for row in rows)
    assert all(row["question"] == QUESTIONS[row["category"]] for row in rows)


@pytest.mark.parametrize("fail_after", [None, 1])
def test_cli_checkpoints_shared_cost_and_never_fabricates_completion(tmp_path, monkeypatch, capsys, fail_after):
    import sys
    from types import SimpleNamespace

    from scripts import run_eval

    rows = [{**item(), "id": f"fixture-{index}"} for index in range(125)]
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "eval.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (data_dir / "pricing.json").write_text(json.dumps({"selected_models": {"cheap": "fixture-model", "strong": "other-model"}}))
    results_dir = tmp_path / "results"
    calls = {"answers": 0}

    class Budget:
        def __init__(self, directory):
            assert directory == data_dir
            self.spent_usd = 2.0  # Historical spend must not enter this run's cost.

    class Retriever:
        def __init__(self, data_dir, budget):
            self.budget = budget

        def build_index(self):
            self.budget.spent_usd += 0.05

        def search(self, question, k, contract_id):
            assert k == 5 and contract_id == "cuad-001"
            self.budget.spent_usd += 0.01
            return [chunk()]

    def generate(question, chunks, model, budget):
        assert model == "fixture-model"
        budget.spent_usd += 0.02
        if calls["answers"] == fail_after:
            raise RuntimeError("Fixture outage, never a model refusal")
        calls["answers"] += 1
        return response()

    monkeypatch.setitem(sys.modules, "contract_qa.budget", SimpleNamespace(Budget=Budget))
    monkeypatch.setitem(sys.modules, "contract_qa.retrieve", SimpleNamespace(Retriever=Retriever))
    monkeypatch.setitem(sys.modules, "contract_qa.answer", SimpleNamespace(answer_from_chunks=generate))
    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--model", "fixture-model", "--data-dir", str(data_dir), "--results-dir", str(results_dir)])
    if fail_after is None:
        run_eval.main()
        expected_count, expected_cost, status = 125, 3.8, "completed"
    else:
        with pytest.raises(SystemExit) as stopped:
            run_eval.main()
        assert stopped.value.code == 1
        expected_count, expected_cost, status = 1, 0.11, "incomplete"
    report = json.loads((results_dir / "fixture-model.json").read_text())
    assert report["status"] == status
    assert len(report["items"]) == expected_count
    assert report["metrics"]["evaluated_items"] == expected_count
    assert report["metrics"]["cost_usd"] == pytest.approx(expected_cost)
    assert report["metrics"]["false_refusal_rate"] == 0.0
    assert report["metrics"]["refusal_accuracy"] is None
    assert "Fixture outage" not in json.dumps(report)
    assert "other-model | Not run" in (results_dir / "summary.md").read_text()
    if fail_after is not None:
        assert report["error_type"] == "RuntimeError"
        assert "Evaluation incomplete (RuntimeError)" in capsys.readouterr().err


def test_cli_prevents_accidental_paid_rerun(tmp_path, monkeypatch, capsys):
    import sys

    from scripts import run_eval

    existing = tmp_path / "fixture-model.json"
    existing.write_text('{"saved": true}')
    monkeypatch.setattr(sys, "argv", [
        "run_eval.py", "--model", "fixture-model", "--results-dir", str(tmp_path)
    ])
    with pytest.raises(SystemExit) as stopped:
        run_eval.main()
    assert stopped.value.code == 2
    assert "--overwrite" in capsys.readouterr().err
    assert json.loads(existing.read_text()) == {"saved": True}
