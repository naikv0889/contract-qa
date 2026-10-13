import json
from types import SimpleNamespace as NS

import pytest

from contract_qa.answer import answer_from_chunks
from contract_qa.budget import BudgetError
from contract_qa.counted import prepare
from test_answer import CHUNKS, VALID, setup

RATES = {'api':'responses', 'request_input_limit':10000, 'reasoning_effort':'none'}


class Client:
    def __init__(self, count=100, status='completed'):
        self.n, self.status = count, status
        self.counted, self.generated = [], []
        self.responses = NS(input_tokens=NS(count=self.count), create=self.create)

    def with_options(self, **options):
        assert options == {'max_retries':0}
        return self

    def count(self, **payload):
        self.counted.append(json.loads(json.dumps(payload)))
        payload['input'][0]['content']='mutated by fake client'
        return NS(object='response.input_tokens',input_tokens=self.n)

    def create(self, **payload):
        self.generated.append(payload)
        return NS(status=self.status,output_text=json.dumps(VALID),
                  usage=NS(input_tokens=100,output_tokens=10))


def test_counted_input_is_generated_unchanged_with_fixed_options(tmp_path):
    client=Client()
    budget=setup(tmp_path,**RATES)
    assert answer_from_chunks('Which law?',CHUNKS,'fake-chat',client=client,budget=budget)==VALID
    sent=client.generated[0]
    for key,value in client.counted[0].items():
        assert sent[key]==value
    assert sent['temperature']==0
    assert sent['reasoning']=={'effort':'none'}
    assert sent['max_output_tokens']==1024
    assert sent['text']=={'format':{'type':'json_object'}}
    assert sent['truncation']=='disabled'
    assert sent['service_tier']=='default'
    assert sent['store'] is False
    assert budget.spent_usd==pytest.approx(.00012)


@pytest.mark.parametrize('n',[None, True, 0, -1, 1.5, '100', 10001])
def test_invalid_or_oversized_counts_never_generate_or_reserve(tmp_path,n):
    client=Client(n);budget=setup(tmp_path,**RATES)
    with pytest.raises(BudgetError):
        answer_from_chunks('Which law?',CHUNKS,'fake-chat',client=client,budget=budget)
    assert not client.generated
    assert budget.spent_usd==0


def test_count_timeout_never_generates(tmp_path):
    client=Client()
    def timeout(**kw):raise TimeoutError
    client.responses.input_tokens.count=timeout
    budget=setup(tmp_path,**RATES)
    with pytest.raises(TimeoutError):
        answer_from_chunks('Which law?',CHUNKS,'fake-chat',client=client,budget=budget)
    assert not client.generated
    assert budget.spent_usd==0


def test_insufficient_budget_blocks_generation_after_count(tmp_path):
    client=Client();budget=setup(tmp_path,**RATES)
    budget.cap=1
    with pytest.raises(BudgetError):
        answer_from_chunks('Which law?',CHUNKS,'fake-chat',client=client,budget=budget)
    assert not client.generated
    assert budget.spent_usd==0


@pytest.mark.parametrize('status',['incomplete','failed','cancelled'])
def test_incomplete_response_is_refused(tmp_path,status):
    result=answer_from_chunks('Which law?',CHUNKS,'fake-chat',client=Client(status=status),
                              budget=setup(tmp_path,**RATES))
    assert 'refusal' in result
