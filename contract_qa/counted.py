"""Exact Responses input counting before a bounded, non-reasoning generation."""

import json

from .budget import BudgetError, ConfigurationError


def prepare(messages, model, rates, client):
    """Count identical serialized input; never infer Chat Completions overhead."""
    limit = rates.get("request_input_limit")
    if (type(limit) is not int or not 0 < limit <= rates["max_input_tokens"]
            or rates.get("reasoning_effort") != "none"):
        raise ConfigurationError("Responses needs a verified input limit and reasoning none.")
    payload = {"model": model, "input": messages,
               "reasoning": {"effort": "none"},
               "text": {"format": {"type": "json_object"}},
               "truncation": "disabled"}
    # Freeze before counting so caller/client mutations cannot change generation.
    frozen = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    count = client.responses.input_tokens.count(**json.loads(frozen))
    n = getattr(count, "input_tokens", None)
    if (getattr(count, "object", None) != "response.input_tokens"
            or type(n) is not int or not 0 < n <= limit):
        raise BudgetError("Exact input count is invalid or exceeds the priced request limit.")
    return frozen, n


def generate(messages, model, rates, client, budget, max_output_tokens):
    frozen, n = prepare(messages, model, rates, client)
    return budget.run(
        model, n, max_output_tokens,
        lambda: client.responses.create(
            **json.loads(frozen), temperature=0, max_output_tokens=max_output_tokens,
            service_tier="default", store=False,
        ),
    )
