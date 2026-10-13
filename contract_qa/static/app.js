'use strict';
const $ = id => document.getElementById(id);
const form = $('question-form');
const question = $('question');
const contract = $('contract');
const region = $('result-region');
const button = $('ask-button');
let contracts = [];
let busy = false;
let configured = false;
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
async function request(path, options) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { throw new Error('The workspace returned an unreadable response. Please try again.'); }
  if (!response.ok) throw new Error(body.error || 'The request could not be completed.');
  return body;
}
function setTag(text, tone = 'neutral') {
  $('result-tag').textContent = text;
  $('result-tag').className = `pill ${tone}`;
}
function setBusy(value) {
  busy = value;
  button.disabled = value;
  question.disabled = value;
  contract.disabled = value;
  $('model').disabled = value;
  document.querySelectorAll('[data-question]').forEach(node => { node.disabled = value; });
  $('button-label').textContent = value ? 'Checking the clauses…' : 'Find an answer';
  $('button-icon').textContent = value ? '·' : '↗';
  document.querySelector('.findings').setAttribute('aria-busy', String(value));
}
function showError(message) {
  region.replaceChildren();
  const box = el('div', 'error-box');
  box.append(el('h3', '', 'Research is unavailable'), el('p', '', message));
  region.append(box, el('p', 'fine-print', 'This is a service or configuration issue. It does not mean your contracts lack an answer.'));
  setTag('Action needed', 'warning');
}
function renderResult(data, asked) {
  region.replaceChildren();
  region.append(el('p', 'question-label', 'YOUR QUESTION'), el('p', 'asked-question', asked));
  const response = data.response;
  if (response && typeof response.refusal === 'string') {
    const box = el('div', 'refusal-box');
    box.append(el('h3', '', 'Not enough verified evidence'), el('p', '', response.refusal));
    region.append(box, el('p', 'fine-print', 'No answer was accepted. Try a more specific question or change the agreement you are searching.'));
    setTag('Refused safely', 'warning');
    return;
  }
  if (!response || typeof response.answer !== 'string' || !Array.isArray(response.citations)) throw new Error('The workspace returned an invalid answer. Nothing has been accepted.');
  setTag('Quotes verified', '');
  region.append(el('h3', 'answer-heading', 'What the clauses say'), el('div', 'answer-text', response.answer));
  region.append(el('h3', 'evidence-heading', `SOURCE EVIDENCE · ${response.citations.length} ${response.citations.length === 1 ? 'CITATION' : 'CITATIONS'}`));
  const sources = new Map((data.sources || []).map(source => [source.chunk_id, source]));
  response.citations.forEach((citation, index) => {
    const card = el('article', 'evidence-card');
    const meta = el('div', 'evidence-meta');
    meta.append(el('span', 'cite-number', String(index + 1)), el('span', 'chunk-id', citation.chunk_id));
    card.append(meta, el('blockquote', '', citation.quote));
    const source = sources.get(citation.chunk_id);
    if (source && typeof source.text === 'string') {
      const details = el('details');
      details.append(el('summary', '', 'Read the full source clause'), el('div', 'source-text', source.text));
      card.append(details);
    }
    region.append(card);
  });
  region.append(el('p', 'fine-print', 'Each quotation was matched against its retrieved source. A matching quotation does not establish legal correctness; read the full agreement before relying on an interpretation.'));
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !question.value.trim()) { question.focus(); return; }
  if (!configured) {
    showError('The OpenAI connection is not configured. Add OPENAI_API_KEY and verified model pricing on the server, then reload this page. Your key never belongs in this browser.');
    return;
  }
  const asked = question.value.trim();
  setBusy(true);
  setTag('Reading & verifying', 'neutral');
  const loading = el('div', 'loading');
  loading.append(el('div', 'spinner'), el('h3', '', 'Following the evidence…'), el('p', '', 'Retrieving five clauses, drafting an answer, and checking every quote.'));
  region.replaceChildren(loading);
  try {
    const data = await request('/api/answer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question: asked, contract_id: contract.value || null, model: $('model').value || null})});
    renderResult(data, asked);
  } catch (error) { showError(error.message); }
  finally { setBusy(false); }
});
question.addEventListener('input', () => { $('character-count').textContent = `${question.value.length.toLocaleString()} / 3,000`; });
question.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll('[data-question]').forEach(node => node.addEventListener('click', () => {
  question.value = node.dataset.question;
  question.dispatchEvent(new Event('input'));
  question.focus();
}));
contract.addEventListener('change', () => {
  const selected = contracts.find(item => item.id === contract.value);
  $('scope-note').textContent = selected ? `${selected.title}${selected.chunk_count !== undefined ? ` · ${selected.chunk_count} source clauses` : ''}` : 'Search the complete collection, or narrow your question to one agreement.';
});
async function init() {
  try {
    const [status, collection] = await Promise.all([request('/api/status'), request('/api/contracts')]);
    contracts = collection.contracts;
    contracts.forEach(item => { const option = el('option', '', item.title || item.id); option.value = item.id; contract.append(option); });
    $('collection-count').textContent = `${contracts.length} agreements`;
    configured = status.configured;
    if (Array.isArray(status.models) && status.models.length) {
      status.models.forEach(item => { const option = el('option', '', typeof item === 'string' ? item : item.label || item.id); option.value = typeof item === 'string' ? item : item.id; $('model').append(option); });
      $('model-field').hidden = false;
    }
    if (!configured) {
      $('service-notice').hidden = false;
      $('service-notice').textContent = status.error || 'Your collection is ready. Live answers need an OpenAI key and verified model pricing configured on the server. No model evaluation has run yet.';
    }
  } catch (error) {
    $('collection-count').textContent = 'Connection issue';
    $('service-notice').hidden = false;
    $('service-notice').textContent = error.message;
  }
}
init();
