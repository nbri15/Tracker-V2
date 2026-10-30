(() => {
  const notes = new Map();
  let leaving = false;
  document.querySelectorAll('[data-intervention-note]').forEach(el => {
    const state = {el, saved: el.value, timer: null, running: null};
    notes.set(el.dataset.interventionNote, state);
    el.addEventListener('input', () => {
      clearTimeout(state.timer);
      state.timer = setTimeout(() => save(state).catch(() => {}), 450);
    });
    el.addEventListener('blur', () => save(state).catch(() => {}));
  });
  async function save(state) {
    clearTimeout(state.timer);
    if (state.running) { await state.running; return save(state); }
    if (state.saved === state.el.value) return;
    const value = state.el.value;
    const status = document.querySelector(`[data-note-status="${state.el.dataset.interventionNote}"]`);
    status.textContent = 'Saving…';
    state.running = (async () => {
      try {
        const response = await fetch('/teacher/api/interventions/quick-save', {
          method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
          body: JSON.stringify({record_id: state.el.dataset.interventionNote, field: 'note', value})
        });
        const body = await response.json();
        if (!response.ok || !body.ok) throw new Error('Save failed');
        state.saved = value;
        status.textContent = 'Saved';
      } catch (error) {
        status.textContent = 'Not saved. Use Save plan to retry.';
        throw error;
      } finally { state.running = null; }
    })();
    await state.running;
    if (state.saved !== state.el.value) return save(state);
  }
  // Finish pending notes before assignment, status changes, or filter/navigation.
  async function flush() { await Promise.all([...notes.values()].map(save)); }
  document.querySelectorAll('form').forEach(form => form.addEventListener('submit', async event => {
    if (leaving) return;
    event.preventDefault();
    try { await flush(); leaving = true; HTMLFormElement.prototype.submit.call(form); }
    catch { document.querySelector('#programme-feedback').textContent = 'A support plan could not be saved. Retry Save plan before leaving this page.'; }
  }));
  document.querySelectorAll('a[href]').forEach(link => link.addEventListener('click', async event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (![...notes.values()].some(s => s.saved !== s.el.value || s.running)) return;
    event.preventDefault();
    try { await flush(); leaving = true; window.location.assign(link.href); }
    catch { document.querySelector('#programme-feedback').textContent = 'Save your support plan before leaving this page.'; }
  }));
  window.addEventListener('beforeunload', event => {
    if (!leaving && [...notes.values()].some(s => s.saved !== s.el.value || s.running)) { event.preventDefault(); event.returnValue = ''; }
  });
  document.querySelectorAll('[data-pupil-drag]').forEach(row => {
    row.addEventListener('dragstart', event => {
      if (event.target.closest('input, textarea, select, button, a, summary')) { event.preventDefault(); return; }
      event.dataTransfer.setData('application/x-class-compass-pupil', row.dataset.pupilDrag);
      event.dataTransfer.effectAllowed = 'copy';
    });
  });
  document.querySelectorAll('[data-programme-drop]').forEach(card => {
    card.addEventListener('dragover', event => {
      if (!event.dataTransfer.types.includes('application/x-class-compass-pupil')) return;
      event.preventDefault(); card.classList.add('drop-ready'); event.dataTransfer.dropEffect = 'copy';
    });
    card.addEventListener('dragleave', event => { if (!card.contains(event.relatedTarget)) card.classList.remove('drop-ready'); });
    card.addEventListener('drop', event => {
      event.preventDefault(); card.classList.remove('drop-ready');
      const pupilId = event.dataTransfer.getData('application/x-class-compass-pupil');
      if (!/^\d+$/.test(pupilId)) return;
      const form = document.querySelector('#programme-drop-form');
      form.elements.pupil_id.value = pupilId; form.elements.programme_id.value = card.dataset.programmeDrop;
      form.requestSubmit();
    });
  });
})();
