/* 搜索 + SSE 管线 + DevTools 控制台 + Markdown 渲染 */

var _currentSSE = null;
var _lineId = 0;
var _tagColors = {
  rewrite:  { bg: '#2d1b69', fg: '#d2a8ff', border: '#8b5cf6' },
  embed:    { bg: '#0c2d6b', fg: '#79c0ff', border: '#58a6ff' },
  retrieve: { bg: '#0d3320', fg: '#7ee787', border: '#3fb950' },
  rerank:   { bg: '#3d2700', fg: '#d29922', border: '#d29922' },
  generate: { bg: '#490202', fg: '#f85149', border: '#f85149' },
};

/* ═══════════════════════════════════════════════════
   Markdown → HTML 渲染器
   ═══════════════════════════════════════════════════ */
function renderMarkdown(text) {
  if (!text) return '';
  var h = esc(text);
  // 代码块 ```...```
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function(m, lang, code) {
    return '<pre style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;overflow-x:auto;font-size:13px;line-height:1.5;">' + code.trim() + '</pre>';
  });
  // 行内代码 `code`
  h = h.replace(/`([^`]+)`/g, '<code style="background:#161b22;border:1px solid #30363d;border-radius:3px;padding:1px 5px;font-size:13px;color:#f97583;">$1</code>');
  // **bold**
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // ==highlight== (Obsidian style)
  h = h.replace(/==(.+?)==/g, '<mark style="background:#2d1b69;color:#d2a8ff;padding:0 4px;border-radius:2px;">$1</mark>');
  // ## headers
  h = h.replace(/^### (.+)$/gm, '<h4 style="font-size:14px;font-weight:600;margin:12px 0 4px 0;color:var(--text-primary);">$1</h4>');
  h = h.replace(/^## (.+)$/gm, '<h3 style="font-size:16px;font-weight:600;margin:14px 0 6px 0;color:var(--text-primary);">$1</h3>');
  // > blockquote
  h = h.replace(/^> (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);padding:4px 12px;margin:6px 0;color:var(--text-secondary);background:var(--bg-overlay);border-radius:0 4px 4px 0;">$1</blockquote>');
  // - list
  h = h.replace(/^- (.+)$/gm, '<li style="margin:2px 0 2px 16px;list-style:disc;">$1</li>');
  // numbered list
  h = h.replace(/^\d+\.\s(.+)$/gm, '<li style="margin:2px 0 2px 20px;list-style:decimal;">$1</li>');
  // --- horizontal rule
  h = h.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:12px 0;">');
  // ~~strikethrough~~
  h = h.replace(/~~(.+?)~~/g, '<del style="color:var(--text-tertiary);">$1</del>');
  // Tables: simple pipe-based
  h = h.replace(/^\|(.+)\|$/gm, function(m, row) {
    var cells = row.split('|').map(function(c) { return c.trim(); });
    // Detect if it's a separator row (|---|)
    if (cells.length > 0 && /^-+$/.test(cells[0].replace(/-+/g, '-'))) return '';
    return '<tr><td style="border:1px solid var(--border);padding:4px 8px;">' + cells.join('</td><td style="border:1px solid var(--border);padding:4px 8px;">') + '</td></tr>';
  });
  h = h.replace(/<tr>.*?<\/tr>/g, function(m) {
    if (h.indexOf('<table>') === -1) {
      h = h.replace(m, '<table style="border-collapse:collapse;margin:8px 0;width:100%;">' + m + '</table>');
    }
    return m;
  });
  // paragraphs (double newline)
  h = h.replace(/\n\n/g, '</p><p style="margin:8px 0;line-height:1.8;">');
  // single newline → space (within same paragraph)
  h = h.replace(/\n/g, ' ');
  // wrap in <p>
  if (h.indexOf('<p') !== 0) {
    h = '<p style="margin:8px 0;line-height:1.8;">' + h + '</p>';
  }
  return h;
}

/* ═══════════════════════════════════════════════════
   搜索入口
   ═══════════════════════════════════════════════════ */
function doSearch() {
  var q = document.getElementById('search-input').value.trim();
  if (!q) return;
  document.getElementById('rt-search-input').value = q;
  document.getElementById('page-home').style.display = 'none';
  document.getElementById('page-results').style.display = 'flex';
  startSearch(q);
}
function doSearchFromResults() {
  var q = document.getElementById('rt-search-input').value.trim();
  if (!q) {
    // 空搜索 → 返回主页
    if (_currentSSE) { _currentSSE.close(); _currentSSE = null; }
    document.getElementById('page-results').style.display = 'none';
    document.getElementById('page-home').style.display = 'flex';
    document.getElementById('search-input').value = '';
    document.getElementById('search-input').focus();
    return;
  }
  startSearch(q);
}

/* ═══════════════════════════════════════════════════
   SSE 核心
   ═══════════════════════════════════════════════════ */
function startSearch(q) {
  if (_currentSSE) { _currentSSE.close(); _currentSSE = null; }
  var p = getStoredParams();
  var params = new URLSearchParams({
    q: q, top_k: p.top_k, mode: p.mode,
    threshold: p.similarity_threshold, temp: p.temperature,
    rerank: p.rerank_enabled, rewrite: p.rewrite_enabled,
  });
  document.getElementById('search-results').innerHTML =
    '<div style="text-align:center;padding:48px 0;color:var(--text-tertiary);font-size:13px;">检索中…</div>';
  document.getElementById('console-lines').innerHTML =
    '<div class="cline ready"><span class="cms"></span><span class="ctag ready">READY</span><span class="csum">等待搜索…</span></div>';

  var hasResult = false;
  var es = new EventSource('/api/search/stream?' + params.toString());
  _currentSSE = es;
  es.addEventListener('rewrite',   function(e) { _addLine('rewrite', JSON.parse(e.data)); });
  es.addEventListener('embed',     function(e) { _addLine('embed', JSON.parse(e.data)); });
  es.addEventListener('retrieve',  function(e) { _addLine('retrieve', JSON.parse(e.data)); });
  es.addEventListener('rerank',    function(e) { _addLine('rerank', JSON.parse(e.data)); });
  es.addEventListener('generate',  function(e) { _addLine('generate', JSON.parse(e.data)); });
  es.addEventListener('result', function(e) {
    hasResult = true;
    renderSearchResults(JSON.parse(e.data));
    es.close(); _currentSSE = null;
  });
  es.addEventListener('error', function() {
    if (!hasResult) {
      document.getElementById('search-results').innerHTML =
        '<div style="text-align:center;padding:48px 0;color:var(--err);">检索失败，请重试</div>';
    }
    es.close(); _currentSSE = null;
  });
}

/* ═══════════════════════════════════════════════════
   控制台行（事件委托展开详情）
   ═══════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', function() {
  // Console detail toggle (event delegation)
  document.getElementById('console-lines').addEventListener('click', function(e) {
    var target = e.target;
    if (!target.classList.contains('cexp')) return;
    var id = target.getAttribute('data-id');
    if (!id) return;
    var panel = document.getElementById(id);
    if (!panel) return;
    var open = panel.style.display === 'block';
    panel.style.display = open ? 'none' : 'block';
    target.textContent = open ? '▸' : '▾';
  });

  // Console collapse toggle
  var consoleEl = document.getElementById('results-console');
  var toggleBtn = document.getElementById('console-collapse');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', function() {
      var collapsed = consoleEl.classList.toggle('collapsed');
      toggleBtn.textContent = collapsed ? '◀' : '▶';
      document.getElementById('console-expand').style.display = collapsed ? 'flex' : 'none';
    });
  }
});

/* ── Console 展开 ── */
function expandConsole() {
  var consoleEl = document.getElementById('results-console');
  var expandBtn = document.getElementById('console-expand');
  var collapseBtn = document.getElementById('console-collapse');
  consoleEl.classList.remove('collapsed');
  expandBtn.style.display = 'none';
  if (collapseBtn) collapseBtn.textContent = '▶';
}

function _addLine(step, data) {
  var lines = document.getElementById('console-lines');
  if (!lines) return;
  var isRunning = data.status === 'running';
  var c = _tagColors[step] || { bg: '#1c2a3a', fg: '#8b949e', border: '#484f58' };
  var ms = isRunning ? '···' : (data.duration_ms || 0).toFixed(0) + 'ms';
  var summary = isRunning ? _runText(step) : _sumText(step, data);
  var suffix = isRunning ? '…' : '';
  var id = 'cd-' + (++_lineId);

  var line = document.createElement('div');
  line.className = 'cline';
  line.innerHTML =
    '<span class="cms">' + ms + '</span>' +
    '<span class="ctag" style="background:' + c.bg + ';color:' + c.fg + ';border:1px solid ' + c.border + ';">' +
    step.toUpperCase() + suffix + '</span>' +
    '<span class="csum">' + summary + '</span>' +
    (!isRunning ? '<span class="cexp" data-id="' + id + '">▾</span>' : '');

  var detail = document.createElement('div');
  detail.className = 'cdetail';
  detail.id = id;
  if (!isRunning) detail.innerHTML = _detail(step, data);
  detail.style.display = 'block';

  lines.appendChild(line);
  lines.appendChild(detail);
  lines.scrollTop = lines.scrollHeight;
}

/* ── 摘要 ── */
function _runText(step) {
  return { rewrite: '改写中…', embed: '向量化中…', retrieve: '检索中…', rerank: '重排中…', generate: '生成中…' }[step] || '';
}
function _sumText(step, data) {
  if (data.status === 'skipped') return '跳过';
  switch (step) {
    case 'rewrite':   return data.skipped ? '无需改写' : '' + (data.input||'').slice(0,16) + ' → ' + (data.output||'').slice(0,20) + '';
    case 'embed':     return (data.dims||0) + 'd · ' + (data.model||'').split('/').pop();
    case 'retrieve':  return (data.chunks_found||0) + ' chunks · ' + (data.mode||'') + ' · thresh=' + (data.threshold||0);
    case 'rerank':    return data.applied ? '已重排 · ' + (data.before||[]).length + ' docs' : '跳过';
    case 'generate':  return (data.tokens_used||0) + ' tokens · ' + (data.model||'').split('/').pop();
    default: return '';
  }
}

/* ── 详情面板 ── */
function _detail(step, data) {
  var h = '';
  var tc = _tagColors[step] || _tagColors.rewrite;
  switch (step) {
    /* ── REWRITE ── */
    case 'rewrite':
      if (data.skipped) {
        h += '<div style="color:' + tc.fg + ';">query: ' + esc(data.input) + '</div>';
        h += '<div style="color:#6e7681;margin-top:4px;">跳过改写（查询过短或不含模糊词）</div>';
      } else {
        h += '<div style="color:' + tc.fg + ';">model: ' + esc(data.model||'—') + '</div>';
        h += '<div style="color:var(--console-dim);margin-top:6px;">system_prompt:</div>';
        h += '<pre>' + esc(data.system_prompt||'') + '</pre>';
        h += '<div style="color:var(--console-dim);margin-top:4px;">user_prompt: <span style="color:var(--console-text);">' + esc(data.user_prompt||data.input||'') + '</span></div>';
        h += '<div style="color:' + _tagColors.retrieve.fg + ';margin-top:4px;">→ <strong>' + esc(data.output||'') + '</strong></div>';
      }
      break;

    /* ── EMBED ── */
    case 'embed':
      h += '<div style="color:' + tc.fg + ';">model: ' + esc(data.model||'—') + '</div>';
      h += '<div style="color:var(--console-dim);">query: <span style="color:var(--console-text);">' + esc(data.query||'') + '</span></div>';
      h += '<div style="color:var(--console-dim);">dims: <span style="color:var(--console-text);">' + (data.dims||0) + '</span></div>';
      break;

    /* ── RETRIEVE ── */
    case 'retrieve':
      h += '<div style="color:' + tc.fg + ';">mode: ' + esc(data.mode||'vector') + ' · top_k: ' + (data.top_k||5) + ' · threshold: ' + (data.threshold||0) + '</div>';
      h += '<div style="color:var(--console-dim);margin:8px 0 4px 0;font-weight:500;">检索结果(' + (data.chunks_found||0) + '):</div>';
      (data.results||[]).forEach(function(r, i) {
        var sc = r.score > 0.6 ? '#7ee787' : (r.score > 0.3 ? '#d29922' : '#f85149');
        h += '<div style="margin:4px 0;border-left:3px solid ' + sc + ';padding:4px 0 4px 10px;background:rgba(255,255,255,.02);border-radius:0 4px 4px 0;">';
        h += '<div><span style="color:' + sc + ';font-weight:600;">#' + (i+1) + ' ' + r.score.toFixed(3) + '</span> <span style="color:var(--console-dim);font-size:10px;">' + esc((r.source_file||'').split('/').pop()) + '</span></div>';
        if (r.heading_path) h += '<div style="color:#6e7681;font-size:10px;margin:1px 0;">' + esc(r.heading_path.slice(0,100)) + '</div>';
        h += '<div style="color:var(--console-text);font-size:10px;margin-top:2px;line-height:1.5;">' + esc(r.preview||'').slice(0,160) + '</div>';
        h += '</div>';
      });
      break;

    /* ── RERANK ── */
    case 'rerank':
      h += '<div style="color:' + tc.fg + ';">model: ' + esc(data.model||'—') + ' · applied: ' + (data.applied ? '✓' : '✗') + '</div>';
      if (data.before && data.before.length) {
        h += '<div style="color:var(--console-dim);margin:8px 0 4px 0;font-weight:500;">重排前后排序变化:</div>';
        // Build a unified table: max length
        var maxLen = Math.max(data.before.length, (data.after||[]).length);
        for (var i = 0; i < maxLen; i++) {
          var b = data.before[i];
          var a = data.after && data.after[i] ? data.after[i] : null;
          if (!b) continue;
          var bName = esc(b[0]);
          var bScore = b[1].toFixed(3);
          if (a) {
            var arrow = a[1] > b[1] ? '↑' : (a[1] < b[1] ? '↓' : '→');
            var col = a[1] > b[1] ? '#7ee787' : (a[1] < b[1] ? '#f85149' : '#6e7681');
            h += '<div style="margin:2px 0;display:flex;align-items:center;gap:6px;">';
            h += '<span style="color:#6e7681;min-width:56px;text-align:right;font-family:monospace;">' + bScore + '</span>';
            h += '<span style="color:#484f58;">→</span>';
            h += '<span style="color:' + col + ';min-width:56px;text-align:right;font-family:monospace;font-weight:600;">' + a[1].toFixed(3) + '</span>';
            h += '<span style="color:' + col + ';min-width:16px;">' + arrow + '</span>';
            h += '<span style="color:var(--console-dim);font-size:10px;">' + bName + '</span>';
            h += '</div>';
          } else {
            h += '<div style="margin:2px 0;color:#6e7681;">' + bScore + ' → <span style="color:#f85149;">dropped</span> ' + bName + '</div>';
          }
        }
      }
      break;

    /* ── GENERATE ── */
    case 'generate':
      h += '<div style="color:' + tc.fg + ';">model: ' + esc(data.model||'—') + ' · temperature: ' + (data.temperature||0.3) + ' · tokens: ' + (data.tokens_used||0) + '</div>';
      if (data.system_prompt) {
        h += '<div style="color:var(--console-dim);margin-top:8px;font-weight:500;">system_prompt:</div>';
        h += '<pre style="max-height:150px;">' + esc(data.system_prompt) + '</pre>';
      }
      if (data.user_prompt) {
        h += '<div style="color:var(--console-dim);margin-top:6px;font-weight:500;">user_prompt (' + (data.tokens_used||'?') + ' tokens):</div>';
        h += '<pre style="max-height:200px;">' + esc(data.user_prompt) + '</pre>';
      }
      break;
  }
  return h;
}

/* ═══════════════════════════════════════════════════
   搜索结果渲染（Markdown 渲染）
   ═══════════════════════════════════════════════════ */
function renderSearchResults(data) {
  var el = document.getElementById('search-results');
  if (!el) return;
  var h = '';

  if (data.answer) {
    h += '<div class="section-title">Answer</div>';
    h += '<div class="answer-text markdown-body">' + renderMarkdown(data.answer) + '</div>';
  }

  var sources = data.sources || [];
  if (sources.length) {
    h += '<div class="section-title">Sources</div>';
    sources.forEach(function(s) {
      var sc = s.score > 0.6 ? 'score-ok' : (s.score > 0.3 ? 'score-mid' : 'score-low');
      h += '<div class="source-card">';
      h += '<div class="source-header">';
      h += '<span class="source-file">[' + s.index + '] ' + (s.source_file||'').split('/').pop() + '</span>';
      h += '<span class="source-score ' + sc + '">' + (s.score||0).toFixed(2) + '</span>';
      h += '</div>';
      if (s.heading_path) h += '<div style="font-size:11px;color:var(--text-tertiary);margin-bottom:6px;">' + esc(s.heading_path) + '</div>';
      h += '<div class="source-preview">' + esc((s.preview||'').slice(0,280)) + '</div>';
      h += '</div>';
    });
  }

  var stats = data.stats || {};
  if (stats.chunks_found) {
    h += '<div class="stats-bar">' + (stats.chunks_found||0) + ' chunks · ' + (stats.chunks_used||0) + ' used · ~' + (stats.tokens_used||0) + ' tokens</div>';
  }

  el.innerHTML = h;
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
