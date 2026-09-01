(function () {
  const pending = new Map();
  const timers = new Map();

  function setStatus(el, state, msg) {
    const target = el.dataset.autosaveStatus && document.querySelector(el.dataset.autosaveStatus);
    if (target) target.textContent = msg || (state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved' : 'Error saving');
    el.classList.remove('autosave-ok', 'autosave-error');
    if (state === 'saved') {
      el.classList.add('autosave-ok');
      setTimeout(() => el.classList.remove('autosave-ok'), 1200);
    }
    if (state === 'error') el.classList.add('autosave-error');
  }

  async function saveField(el, retry = true) {
    if (!el.checkValidity()) return;
    const key = [el.dataset.autosaveUrl, el.dataset.field, el.dataset.recordId || '', el.name || ''].join('|');
    const value = el.type === 'checkbox' ? el.checked : el.value;
    const payload = {
      field: el.dataset.field,
      value,
      record_id: el.dataset.recordId || null,
      year_group: el.dataset.yearGroup || null,
      term: el.dataset.term || null,
      subject: el.dataset.subject || null,
      school_id: el.dataset.schoolId || null,
    };
    if (pending.get(key) === JSON.stringify(payload)) return;
    pending.set(key, JSON.stringify(payload));
    setStatus(el, 'saving', 'Saving…');
    try {
      const res = await fetch(el.dataset.autosaveUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body.ok === false) throw new Error(body.error || `Failed with status ${res.status}`);
      pending.delete(key);
      setStatus(el, 'saved', 'Saved');
    } catch (e) {
      console.error('Autosave failed:', e);
      setStatus(el, 'error', e?.message || 'Error saving');
      if (retry) setTimeout(() => saveField(el, false), 1000);
    }
  }

  function queueSave(el) {
    const key = el.name || el.dataset.field;
    clearTimeout(timers.get(key));
    timers.set(key, setTimeout(() => saveField(el), 450));
  }

  document.querySelectorAll('[data-autosave="true"]').forEach((el) => {
    const t = (el.type || '').toLowerCase();
    if (t === 'checkbox' || el.tagName === 'SELECT') {
      el.addEventListener('change', () => saveField(el));
      return;
    }
    el.addEventListener('blur', () => saveField(el));
    el.addEventListener('input', () => queueSave(el));
  });
})();
