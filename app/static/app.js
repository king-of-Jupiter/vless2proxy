// VLESS dashboard — vanilla JS, без сборки.
(function () {
  'use strict';

  var panel = document.getElementById('addPanel');
  var form = document.getElementById('addForm');
  var formErr = document.getElementById('formErr');

  // Тёмная / светлая тема, выбор хранится в localStorage
  var themeToggle = document.getElementById('themeToggle');
  var themeLabel = document.getElementById('themeLabel');
  function paintThemeLabel() {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (themeLabel) themeLabel.textContent = dark ? 'Светлая' : 'Тёмная';
  }
  if (themeToggle) {
    paintThemeLabel();
    themeToggle.addEventListener('click', function () {
      var dark = document.documentElement.getAttribute('data-theme') === 'dark';
      var next = dark ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('vless-theme', next); } catch (e) { /* приватный режим */ }
      paintThemeLabel();
    });
  }

  function showPanel(v) { panel.hidden = !v; if (v) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  document.getElementById('openFormBtn').addEventListener('click', function () { showPanel(true); });
  document.getElementById('closeFormBtn').addEventListener('click', function () { showPanel(false); });
  document.getElementById('cancelFormBtn').addEventListener('click', function () { showPanel(false); });

  // Переключение полей портов по режиму
  var modeInputs = form.querySelectorAll('input[name="mode"]');
  var socksField = document.getElementById('socksField');
  var httpField = document.getElementById('httpField');
  function syncMode() {
    var mode = form.querySelector('input[name="mode"]:checked').value;
    socksField.hidden = (mode === 'http');
    httpField.hidden = (mode === 'socks5');
  }
  modeInputs.forEach(function (r) { r.addEventListener('change', syncMode); });
  syncMode();

  async function api(path, opts) {
    var res = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {}));
    var data = null;
    try { data = await res.json(); } catch (e) { /* пусто */ }
    if (!res.ok) {
      var msg = (data && data.detail) || ('HTTP ' + res.status);
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return data;
  }

  form.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    formErr.hidden = true;
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Запуск и проверка…';
    var fd = new FormData(form);
    var payload = {
      name: (fd.get('name') || '').toString().trim(),
      vless_url: (fd.get('vless_url') || '').toString().trim(),
      mode: (fd.get('mode') || 'socks5').toString(),
    };
    var sp = parseInt((fd.get('socks_port') || '').toString(), 10);
    var hp = parseInt((fd.get('http_port') || '').toString(), 10);
    if (!Number.isNaN(sp)) payload.socks_port = sp;
    if (!Number.isNaN(hp)) payload.http_port = hp;
    try {
      await api('/api/profiles', { method: 'POST', body: JSON.stringify(payload) });
      form.reset();
      // обновить подсказки портов
      var nxt = await api('/api/next-ports');
      form.querySelector('input[name="socks_port"]').value = nxt.socks_port;
      form.querySelector('input[name="http_port"]').value = nxt.http_port;
      var first = form.querySelector('input[name="mode"][value="socks5"]');
      if (first) first.checked = true;
      syncMode();
      showPanel(false);
      location.reload();
    } catch (e) {
      formErr.textContent = e.message;
      formErr.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Запустить';
    }
  });

  // Предпроверка ссылки до добавления: временный прокси + пинг + IP
  var precheckBtn = document.getElementById('precheckBtn');
  var precheckResult = document.getElementById('precheckResult');
  var urlField = form.querySelector('textarea[name="vless_url"]');
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]);
    });
  }
  function setPrecheck(html) { precheckResult.innerHTML = html; precheckResult.hidden = false; }
  urlField.addEventListener('input', function () { precheckResult.hidden = true; });
  precheckBtn.addEventListener('click', async function () {
    var url = urlField.value.trim();
    var mode = form.querySelector('input[name="mode"]:checked').value;
    if (!url) {
      setPrecheck('<span class="badge badge-offline">ошибка</span><span>Вставьте VLESS-ссылку</span>');
      return;
    }
    precheckBtn.disabled = true;
    precheckBtn.textContent = 'Проверяется…';
    setPrecheck('<span class="meta">Поднимаю временный прокси и меряю пинг…</span>');
    try {
      var r = await api('/api/validate', { method: 'POST', body: JSON.stringify({ vless_url: url, mode: mode }) });
      if (r.ok) {
        setPrecheck(
          '<span class="badge badge-online">онлайн</span>' +
          '<code class="mono">' + escapeHtml(r.ip || '—') + '</code>' +
          '<span class="ping mono">' + r.ping_ms + ' ms</span>' +
          '<span class="meta">' + escapeHtml((r.transport || '') + ' · ' + (r.server || '')) + '</span>'
        );
      } else {
        setPrecheck('<span class="badge badge-offline">офлайн</span><span>' + escapeHtml(r.error || 'неизвестная ошибка') + '</span>');
      }
    } catch (e) {
      setPrecheck('<span class="badge badge-offline">ошибка</span><span>' + escapeHtml(e.message) + '</span>');
    } finally {
      precheckBtn.disabled = false;
      precheckBtn.textContent = 'Проверить ссылку';
    }
  });

  // Делегирование действий карточек
  document.getElementById('cards').addEventListener('click', async function (ev) {
    var btn = ev.target.closest('button');
    if (!btn) return;
    if (btn.classList.contains('copy')) {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy || '');
        btn.textContent = 'ок';
        setTimeout(function () { btn.textContent = 'копия'; }, 1200);
      } catch (e) { /* clipboard недоступен */ }
      return;
    }
    var card = ev.target.closest('.card');
    if (!card || !btn.dataset.act) return;
    var id = card.dataset.id;
    var act = btn.dataset.act;
    btn.disabled = true;
    try {
      if (act === 'del') {
        if (!confirm('Удалить прокси и остановить процесс?')) return;
        await api('/api/profiles/' + id, { method: 'DELETE' });
        card.remove();
        return;
      }
      if (act === 'logs') {
        var pre = card.querySelector('.logs');
        var data = await api('/api/profiles/' + id + '/logs?n=120');
        pre.textContent = data.logs || '(лог пуст)';
        pre.hidden = !pre.hidden;
        return;
      }
      await api('/api/profiles/' + id + '/' + act, { method: 'POST' });
      location.reload();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  });

  // Мягкое появление блоков
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) {
        en.target.style.transitionDelay = 'calc(var(--index, 0) * 80ms)';
        en.target.classList.add('visible');
        io.unobserve(en.target);
      }
    });
  }, { threshold: 0.05 });
  document.querySelectorAll('.reveal').forEach(function (el, i) {
    if (!el.style.getPropertyValue('--index')) el.style.setProperty('--index', i);
    io.observe(el);
  });
})();
