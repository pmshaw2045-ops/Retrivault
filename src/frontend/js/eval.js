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
  } catch(e) {}
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
  var configInfo = document.getElementById('eval-config-info');
  var badcase = document.getElementById('eval-badcase');

  empty.style.display = 'none';
  result.style.display = 'block';

  // 评测时间
  if (data.run_at) lastTime.textContent = '上次: ' + data.run_at;

  // 配置信息
  var cfg = data.config || {};
  configInfo.textContent = cfg.mode ? '模式=' + cfg.mode + ' · K=' + cfg.top_k + ' · 阈值=' + cfg.threshold : '';

  // Metric cards with delta
  var m = data.metrics || {};
  var d = data.deltas || {};
  metrics.innerHTML = [
    { key: 'hit_rate', label: 'Hit Rate', fmt: function(v) { return (v * 100).toFixed(0) + '%'; } },
    { key: 'mrr', label: 'MRR', fmt: function(v) { return v.toFixed(2); } },
    { key: 'precision@5', label: 'Precision@5', fmt: function(v) { return (v * 100).toFixed(0) + '%'; } },
    { key: 'recall@5', label: 'Recall@5', fmt: function(v) { return (v * 100).toFixed(0) + '%'; } },
    { key: 'ndcg@5', label: 'NDCG@5', fmt: function(v) { return v.toFixed(2); } },
  ].map(function(item) {
    var val = (m[item.key] || 0);
    var delta = d[item.key];
    var deltaHtml = '';
    if (delta !== null && delta !== undefined) {
      if (delta === 0) {
        deltaHtml = '<div class="eval-delta" style="color:var(--text-tertiary);">持平</div>';
      } else {
        var cls = delta > 0 ? 'eval-delta-up' : 'eval-delta-down';
        var sign = delta > 0 ? '+' : '';
        var isPct = ['hit_rate','precision@5','recall@5'].indexOf(item.key) >= 0;
        deltaHtml = '<div class="eval-delta ' + cls + '">' + sign + (isPct ? (delta * 100).toFixed(1) + '%' : delta.toFixed(2)) + '</div>';
      }
    }
    return '<div class="eval-card">' +
      '<div class="eval-value">' + item.fmt(val) + '</div>' +
      '<div class="eval-label">' + item.label + '</div>' +
      deltaHtml +
      '</div>';
  }).join('');

  // Bad case 聚合
  var details = data.details || [];
  var misses = details.filter(function(d) { return !d.hit; });
  var lowMrr = details.filter(function(d) { return d.hit && d.mrr < 0.5; });
  if (misses.length > 0 || lowMrr.length > 0) {
    badcase.style.display = 'block';
    var html = '<div class="eval-badcase-title">⚠️ 需要关注的查询</div>';
    misses.forEach(function(d) {
      html += '<div class="eval-badcase-item"><span class="bci-tag miss">未命中</span>' + esc(d.query) + '</div>';
    });
    lowMrr.forEach(function(d) {
      html += '<div class="eval-badcase-item"><span class="bci-tag low">低排序</span> ' + esc(d.query) + ' <span style="color:var(--text-tertiary);font-size:12px;">MRR=' + d.mrr.toFixed(2) + '</span></div>';
    });
    badcase.innerHTML = html;
  } else {
    badcase.style.display = 'none';
  }

  // Detail table
  tableBody.innerHTML = details.map(function(d) {
    var hitClass = d.hit ? 'eval-hit' : 'eval-miss';
    var hitIcon = d.hit ? '✓' : '✗';
    return '<tr>' +
      '<td>' + esc(d.query) + '</td>' +
      '<td style="text-align:center;"><span class="' + hitClass + '">' + hitIcon + '</span></td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + (d.mrr || 0).toFixed(2) + '</td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + ((d['precision@5'] || 0) * 100).toFixed(0) + '%</td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + ((d['recall@5'] || 0) * 100).toFixed(0) + '%</td>' +
      '<td style="text-align:center;font-family:var(--font-mono);">' + (d['ndcg@5'] || 0).toFixed(2) + '</td>' +
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
