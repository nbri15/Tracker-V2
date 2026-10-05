/* Fast entry; all displayed outcomes come from the server calculation service. */
(() => {
  const table = document.querySelector('.js-reliable-subject-table');
  if (!table) return;
  const form = table.closest('form');
  const state = document.getElementById('score-save-state');
  let dirty = false, timer, controller;
  const rows = [...table.querySelectorAll('tr[data-pupil-id]')];
  const inputs = row => [...row.querySelectorAll('.js-paper-score')];
  const showError = (input, message) => {
    input.setCustomValidity(message);
    input.classList.toggle('is-invalid', Boolean(message));
    let feedback = input.parentElement.querySelector('.score-validation');
    if (!feedback) { feedback = document.createElement('div'); feedback.className = 'score-validation small text-danger'; input.after(feedback); }
    feedback.textContent = message;
  };
  const validate = input => {
    const raw = input.value.trim(), max = Number(input.dataset.max);
    let error = '';
    if (raw && !/^\d+$/.test(raw)) error = 'Enter a whole number, zero, or leave blank.';
    else if (raw && Number(raw) > max) error = `Score ${raw} is greater than the maximum of ${max}.`;
    showError(input, error);
    return !error;
  };
  const markDirty = () => { dirty = true; state.textContent = 'Unsaved changes'; state.className = 'px-3 mt-3 text-warning-emphasis'; };
  const refreshOutcomes = async () => {
    if (controller) controller.abort();
    controller = new AbortController();
    const payload = rows.map(row => ({ pupil_id: Number(row.dataset.pupilId), paper_1_score: inputs(row)[0].value, paper_2_score: inputs(row)[1].value, assessment_year_group: row.querySelector('.js-assessment-year-group').value }));
    try {
      const response = await fetch(table.dataset.calculateUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify({ academic_year: table.dataset.academicYear, term: table.dataset.term, rows: payload }), signal: controller.signal});
      if (!response.ok) throw new Error('Preview unavailable');
      const data = await response.json();
      data.rows.forEach(result => {
        const row = rows.find(row => Number(row.dataset.pupilId) === result.pupil_id);
        row.querySelector('.js-combined-score').textContent = result.error ? 'Check scores' : result.combined_score ?? '—';
        row.querySelector('.js-combined-percent').textContent = result.error || result.combined_percent == null ? '—' : `${result.combined_percent.toFixed(1)}%`;
        row.querySelector('.js-band-label').textContent = result.error ? result.error : result.band_label ?? 'Missing scores';
        const theme = result.error || !result.band_label ? null : result.band_label === 'Working Towards' ? 'wt' : result.band_label === 'Exceeding' ? 'ex' : 'ot';
        ['wt', 'ot', 'ex'].forEach(value => {
          row.classList.toggle(`result-row-${value}`, theme === value);
          row.querySelectorAll('.js-combined-score, .js-combined-percent, .js-band-label').forEach(cell => cell.classList.toggle(`result-cell-${value}`, theme === value));
        });
        row.classList.toggle('table-warning', Number(row.querySelector('.js-assessment-year-group').value) < Number(row.dataset.pupilYearGroup));
        const locallyValid = inputs(row).map(validate).every(Boolean);
        if (result.error && locallyValid) showError(inputs(row)[0], result.error);
      });
    } catch (error) {
      if (error.name !== 'AbortError') state.textContent = 'Unsaved changes — live calculation unavailable; Save will validate all scores';
    }
  };
  form.addEventListener('input', event => {
    markDirty();
    if (event.target.matches('.js-paper-score')) validate(event.target);
    clearTimeout(timer); timer = setTimeout(refreshOutcomes, 200);
  });
  form.addEventListener('change', () => { markDirty(); clearTimeout(timer); timer = setTimeout(refreshOutcomes, 200); });
  table.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !event.target.matches('.js-paper-score')) return;
    event.preventDefault();
    const row = event.target.closest('tr'), column = inputs(row).indexOf(event.target), index = rows.indexOf(row);
    const next = rows[index + (event.shiftKey ? -1 : 1)];
    if (next) { inputs(next)[column].focus(); inputs(next)[column].select(); }
  });
  table.addEventListener('paste', event => {
    if (!event.target.matches('.js-paper-score')) return;
    const pasted = event.clipboardData.getData('text/plain').trimEnd();
    if (!/[\t\n]/.test(pasted)) return;
    event.preventDefault();
    const startRow = rows.indexOf(event.target.closest('tr')), startColumn = inputs(rows[startRow]).indexOf(event.target);
    const matrix = pasted.split(/\r?\n/).map(line => line.split('\t'));
    if (startRow + matrix.length > rows.length || matrix.some(line => startColumn + line.length > 2)) {
      showError(event.target, 'Paste only paper-score columns within the visible pupil rows.');
      return;
    }
    matrix.forEach((line, rowOffset) => line.forEach((value, columnOffset) => {
      const input = inputs(rows[startRow + rowOffset])[startColumn + columnOffset]; input.value = value.trim(); validate(input);
    }));
    markDirty(); clearTimeout(timer); timer = setTimeout(refreshOutcomes, 200);
  });
  form.addEventListener('submit', event => {
    if (!rows.flatMap(inputs).map(validate).every(Boolean)) { event.preventDefault(); form.reportValidity(); return; }
    state.textContent = 'Saving all changes…'; dirty = false;
  });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
})();
