/* API 客户端 */

var API_BASE = '';

async function api(endpoint, opts) {
  opts = opts || {};
  var res = await fetch(API_BASE + endpoint, {
    headers: { 'Content-Type': 'application/json' },
    method: opts.method || 'GET',
    body: opts.body || undefined,
  });
  if (!res.ok) {
    var errText = '';
    try { var err = await res.json(); errText = err.detail || err.message || ''; } catch(e) {}
    throw new Error(res.status + ' ' + res.statusText + (errText ? ': ' + errText : ''));
  }
  return res.json();
}

/* ── Search ── */
function apiSearch(q, topK, mode, threshold, temp) {
  return api('/api/search', {
    method: 'POST',
    body: JSON.stringify({
      query: q, top_k: topK, mode: mode || 'vector',
      similarity_threshold: threshold || 0, temperature: temp || 0.3,
    }),
  });
}

/* ── Status ── */
function apiStatus() {
  return api('/api/status');
}

/* ── Index ── */
function apiIndex(action) {
  return api('/api/index', {
    method: 'POST',
    body: JSON.stringify({ action: action || 'full' }),
  });
}

function apiIndexProgress() {
  return api('/api/index/progress');
}

/* ── Eval ── */
function apiEval(mode, topK, threshold) {
  return api('/api/eval', {
    method: 'POST',
    body: JSON.stringify({
      mode: mode || 'vector',
      top_k: topK || 5,
      similarity_threshold: threshold || 0,
      golden_path: 'tests/fixtures/golden_dataset.yaml',
    }),
  });
}

function apiEvalLast() {
  return api('/api/eval/last');
}

function apiEvalCompare() {
  return api('/api/eval/compare', {
    method: 'POST',
    body: JSON.stringify({
      configs: [
        { mode: 'vector', top_k: 5, similarity_threshold: 0, config_name: 'vector' },
        { mode: 'hybrid', top_k: 5, similarity_threshold: 0, config_name: 'hybrid' },
      ],
      golden_path: 'tests/fixtures/golden_dataset.yaml',
    }),
  });
}
