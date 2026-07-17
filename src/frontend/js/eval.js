/* Eval Dashboard */

var _isRunning = false;

document.addEventListener('DOMContentLoaded', function() {
  loadLastEval();
});

async function loadLastEval() {
  try {
    var data = await apiEvalLast();
    if (data && data.has_data) {
      renderEvalResults(data);
    }
  } catch(e) {
    // 首次无数据，空状态已展示
  }
}

async function runEval() {
  if (_isRunning) return;
  _isRunning = true;

  var btn = document.getElementById('btn-run-eval');
  var btnText = document.getElementById('btn-eval-text');
  var loading = document.getElementById('eval-loading');
  var empty = document.getElementById('eval-empty');
  var result = document.getElementById('eval-result-area');

  btn.disabled = true;
  btnText.textContent = '评测中…';
  loading.style.display = 'block';
  empty.style.display = 'none';
  result.style.display = 'none';

  try {
    var data = await apiEval('hybrid', 5, 0.1);
    // 等待一下让后端保存 last
    await sleep(500);
    var last = await apiEvalLast();
    if (last && last.has_data) {
      renderEvalResults(last);
    }
  } catch(e) {
    empty.style.display = 'block';
    empty.innerHTML = '<div class="eval-empty"><p>❌ 评测失败: ' + e.message + '</p></div>';
  } finally {
    _isRunning = false;
    btn.disabled = false;
    btnText.textContent = '运行评测';
    loading.style.display = 'none';
  }
}

function renderEvalResults(data) {
  var empty = document.getElementById('eval-empty');
  var result = document.getElementById('eval-result-area');
  var metrics = document.getElementById('eval-metrics');
  var tableBody = document.getElementById('eval-table-body');
  var lastTime = document.getElementById('eval-last-time');

  // 隐藏空状态，显示结果
  empty.style.display = 'none';
  result.style.display = 'block';

  // 上次评测时间
  if (data.run_at) {
    lastTime.textContent = '上次: ' + data.run_at;
  }

  // Metric cards
  var m = data.metrics || {};
  metrics.innerHTML = [
    { label: 'Hit Rate', value: ((m.hit_rate || 0) * 100).toFixed(0) + '%' },
    { label: 'MRR', value: (m.mrr || 0).toFixed(2) },
    { label: 'Precision@5', value: ((m['precision@5'] || 0) * 100).toFixed(0) + '%' },
    { label: 'Recall@5', value: ((m['recall@5'] || 0) * 100).toFixed(0) + '%' },
    { label: 'NDCG@5', value: (m['ndcg@5'] || 0).toFixed(2) },
  ].map(function(item) {
    return '<div class="eval-card"><div class="eval-value">' + item.value + '</div><div class="eval-label">' + item.label + '</div></div>';
  }).join('');

  // Detail table
  var details = data.details || [];
  tableBody.innerHTML = details.map(function(d) {
    var hitClass = d.hit ? 'eval-hit' : 'eval-miss';
    var hitIcon = d.hit ? '✓' : '✗';
    return '<tr>' +
      '<td>' + esc(d.query) + '</td>' +
      '<td style="text-align:center;"><span class="' + hitClass + '">' + hitIcon + '</span></td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + (d.mrr || 0).toFixed(2) + '</td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + ((d['recall@5'] || 0) * 100).toFixed(0) + '%</td>' +
      '<td style="text-align:center;font-family:var(--font-mono);color:var(--text-tertiary);">' + (d.latency_ms || 0).toFixed(0) + 'ms</td>' +
      '</tr>';
  }).join('');
}

function sleep(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
