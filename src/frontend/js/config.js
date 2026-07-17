/* 重建索引 — 进度条不可关闭 Modal */

async function startReindex() {
  var pre = document.getElementById('index-status-pre');
  var progress = document.getElementById('index-status-progress');
  var done = document.getElementById('index-status-done');
  var okBtn = document.getElementById('btn-index-done');
  var startBtn = document.getElementById('btn-start-index');
  var cancelBtn = document.getElementById('btn-index-cancel');

  // 切换到进度视图
  pre.style.display = 'none';
  progress.style.display = 'block';
  done.style.display = 'none';
  startBtn.style.display = 'none';
  cancelBtn.style.display = 'none';
  okBtn.style.display = 'none';

  // 重置进度
  setProgress('scan', 0, 0);
  setProgress('embed', 0, 0);
  setMsg('正在扫描文档…');

  try {
    var resp = await apiIndex('full');

    if (resp.status === 'ok' || resp.status === 'skipped') {
      showIndexDone(resp);
      return;
    }

    await pollIndexProgress();
  } catch(e) {
    setMsg('❌ 索引失败: ' + e.message);
    showIndexDone({doc_count: 0, chunk_count: 0});
  }
}

async function pollIndexProgress() {
  var maxPolls = 300;
  for (var i = 0; i < maxPolls; i++) {
    try {
      var pr = await apiIndexProgress();
      if (!pr) { await sleep(1000); continue; }

      var phase = pr.phase || '';
      var current = pr.current || 0;
      var total = pr.total || 0;

      if (phase === 'scanning') {
        setProgress('scan', current, total);
      } else if (phase === 'embedding') {
        setProgress('scan', total, total);
        setProgress('embed', current, total);
      }

      setMsg(phase === 'scanning'
        ? '正在扫描第 ' + current + ' / ' + total + ' 个文档…'
        : '正在向量化第 ' + current + ' / ' + total + ' 个块…');

      if (pr.status === 'ready' || pr.status === 'ok') {
        showIndexDone({doc_count: pr.doc_count, chunk_count: pr.chunk_count});
        return;
      }
      if (pr.status === 'error') {
        setMsg('❌ 索引出错');
        showIndexDone({doc_count: 0, chunk_count: 0});
        return;
      }
    } catch(e) {
      try {
        var st = await apiStatus();
        if (st.state === 'ready') {
          showIndexDone({doc_count: st.doc_count, chunk_count: st.chunk_count});
          return;
        }
      } catch(e2) {}
    }
    await sleep(1000);
  }
  setMsg('⏱ 轮询超时，请检查服务端状态');
  showIndexDone({doc_count: 0, chunk_count: 0});
}

function setProgress(phase, current, total) {
  var pct = total > 0 ? Math.round(current / total * 100) : 0;
  var bar = document.getElementById('progress-' + phase);
  var txt = document.getElementById('progress-' + phase + '-text');
  if (bar) bar.style.width = Math.min(pct, 100) + '%';
  if (txt) txt.textContent = current + ' / ' + total;
}

function setMsg(text) {
  var el = document.getElementById('progress-msg');
  if (el) el.textContent = text;
}

function showIndexDone(result) {
  var pre = document.getElementById('index-status-pre');
  var progress = document.getElementById('index-status-progress');
  var done = document.getElementById('index-status-done');
  var okBtn = document.getElementById('btn-index-done');
  var startBtn = document.getElementById('btn-start-index');
  var cancelBtn = document.getElementById('btn-index-cancel');

  pre.style.display = 'none';
  progress.style.display = 'none';
  done.style.display = 'block';
  startBtn.style.display = 'none';
  cancelBtn.style.display = 'inline-flex';
  okBtn.style.display = 'inline-flex';

  var msg = document.getElementById('index-done-msg');
  if (msg) msg.textContent = '文档: ' + (result.doc_count || 0) + ' | 块: ' + (result.chunk_count || 0);
}

function sleep(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

/* ── Eval (入口级，供 eval.html 调用) ── 仅保留空壳避免引用错误 */

async function doEval() {}
