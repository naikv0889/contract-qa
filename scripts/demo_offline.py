"""Demonstrate deterministic verification with a real annotated CUAD clause.

This is NOT a generated model answer or a retrieval benchmark. The gold
annotation is supplied directly to isolate code-level evidence validation.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contract_qa.answer import verify_response, normalize_quote


def main():
    items = [json.loads(line) for line in (ROOT / 'data/eval.jsonl').read_text().splitlines()]
    chunks = [json.loads(line) for line in (ROOT / 'data/chunks.jsonl').read_text().splitlines()]
    for item in items:
        for quote in item['annotated_answers']:
            for chunk in chunks:
                if chunk['contract_id'] == item['contract_id'] and normalize_quote(quote) in normalize_quote(chunk['text']):
                    valid = {'answer': 'Annotated source clause (offline demonstration).',
                             'citations': [{'chunk_id': chunk['chunk_id'], 'quote': quote}]}
                    print('Offline verification demo; no model or retrieval API was called.')
                    print(json.dumps(verify_response(valid, [chunk]), indent=2))
                    fabricated = {'answer': 'Unsupported answer.', 'citations': [
                        {'chunk_id': chunk['chunk_id'], 'quote': 'A purple spaceship governs this agreement.'}]}
                    print(json.dumps(verify_response(fabricated, [chunk]), indent=2))
                    return
    raise SystemExit('No real annotated clause available for the demonstration.')


if __name__ == '__main__':
    main()
