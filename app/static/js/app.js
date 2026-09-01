const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
const nativeFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const method = (init.method || 'GET').toUpperCase();
  const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
  if (url.origin === window.location.origin && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const headers = new Headers(init.headers || {});
    headers.set('X-CSRFToken', csrfToken);
    init = { ...init, headers };
  }
  return nativeFetch(input, init);
};

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form').forEach((form) => {
    if ((form.method || 'get').toLowerCase() !== 'post' || form.querySelector('input[name="csrf_token"]')) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = csrfToken;
    form.appendChild(input);
  });

  const pdfUrlForButton = (button) => {
    if (button.dataset.pdfUrl) return button.dataset.pdfUrl;
    const url = new URL(window.location.href);
    url.searchParams.set('pdf', '1');
    return url.toString();
  };

  document.querySelectorAll('.js-download-pdf').forEach((button) => {
    button.addEventListener('click', () => {
      window.location.href = pdfUrlForButton(button);
    });
  });

  document.querySelectorAll('.js-subject-table').forEach((table) => {
    const combinedMax = Number.parseFloat(table.dataset.combinedMax || '0');
    const belowThreshold = Number.parseFloat(table.dataset.belowThreshold || '0');
    const exceedingThreshold = Number.parseFloat(table.dataset.exceedingThreshold || '0');

    table.querySelectorAll('tbody tr').forEach((row) => {
      const paperInputs = row.querySelectorAll('.js-paper-score');
      if (paperInputs.length !== 2) return;

      const updateRow = () => {
        const values = Array.from(paperInputs).map((input) => (input.value === '' ? null : Number.parseFloat(input.value)));
        const combinedCell = row.querySelector('.js-combined-score');
        const percentCell = row.querySelector('.js-combined-percent');
        const bandCell = row.querySelector('.js-band-label');
        const assessmentSelect = row.querySelector('.js-assessment-year-group');
        const pupilYearGroup = Number.parseInt(row.dataset.pupilYearGroup || '', 10);
        const clearBandClasses = (cell) => {
          cell.classList.remove('band-wts', 'band-ot', 'band-gds');
        };

        if (values.some((value) => Number.isNaN(value)) || values.includes(null)) {
          combinedCell.textContent = '—';
          percentCell.textContent = '—';
          bandCell.innerHTML = '<span class="text-muted">—</span>';
          clearBandClasses(combinedCell);
          clearBandClasses(percentCell);
          clearBandClasses(bandCell);
          return;
        }

        const combined = values[0] + values[1];
        const percent = combinedMax ? ((combined / combinedMax) * 100).toFixed(1) : null;
        let band = 'On Track';
        let bandClass = 'band-ot';
        let badgeClass = 'result-badge-ot';
        const assessmentYearGroup = assessmentSelect ? Number.parseInt(assessmentSelect.value || '', 10) : null;
        const belowYearExpectation = Number.isFinite(pupilYearGroup) && Number.isFinite(assessmentYearGroup) && assessmentYearGroup < pupilYearGroup;
        if (percent === null) {
          band = '—';
        } else if (belowYearExpectation || Number.parseFloat(percent) < belowThreshold) {
          band = 'Working Towards';
          bandClass = 'band-wts';
          badgeClass = 'result-badge-wt';
        } else if (Number.parseFloat(percent) >= exceedingThreshold) {
          band = 'Exceeding';
          bandClass = 'band-gds';
          badgeClass = 'result-badge-ex';
        }

        combinedCell.textContent = combined;
        percentCell.textContent = percent === null ? '—' : `${percent}%`;
        clearBandClasses(combinedCell);
        clearBandClasses(percentCell);
        clearBandClasses(bandCell);
        if (percent !== null) {
          combinedCell.classList.add(bandClass);
          percentCell.classList.add(bandClass);
          bandCell.classList.add(bandClass);
        }
        row.classList.toggle('table-warning', belowYearExpectation);
        bandCell.innerHTML = percent === null ? '<span class="text-muted">—</span>' : `<span class="result-badge ${badgeClass}">${band}</span>`;
      };

      paperInputs.forEach((input) => input.addEventListener('input', updateRow));
      row.querySelectorAll('.js-assessment-year-group').forEach((input) => input.addEventListener('change', updateRow));
      updateRow();
    });
  });

  const formatGapNumber = (value) => (Number.isInteger(value) ? `${value}` : value.toFixed(1));

  document.querySelectorAll('.js-gap-form').forEach((form) => {
    const tables = Array.from(form.querySelectorAll('.js-gap-table'));
    const activePaperField = form.querySelector('.js-gap-active-paper');

    const updateGapTotals = () => {
      const overallTotals = new Map();

      tables.forEach((table) => {
        const maxTotal = Array.from(table.querySelectorAll('.js-gap-max')).reduce((sum, input) => sum + (Number.parseFloat(input.value || '0') || 0), 0);
        table.querySelectorAll('.js-gap-paper-max').forEach((cell) => {
          cell.textContent = formatGapNumber(maxTotal);
        });

        table.querySelectorAll('tbody tr[data-pupil-id]').forEach((row) => {
          const scoreInputs = Array.from(row.querySelectorAll('.js-gap-score'));
          const values = scoreInputs.map((input) => (input.value === '' ? null : Number.parseFloat(input.value)));
          const paperTotalCell = row.querySelector('.js-gap-row-total');
          const pupilId = row.dataset.pupilId;
          const numericValues = values.filter((value) => value !== null && !Number.isNaN(value));

          if (!numericValues.length) {
            paperTotalCell.textContent = '—';
          } else {
            const total = numericValues.reduce((sum, value) => sum + value, 0);
            paperTotalCell.textContent = formatGapNumber(total);
            overallTotals.set(pupilId, (overallTotals.get(pupilId) || 0) + total);
          }
        });
      });

      tables.forEach((table) => {
        table.querySelectorAll('tbody tr[data-pupil-id]').forEach((row) => {
          const overallCell = row.querySelector('.js-gap-overall-total');
          const pupilId = row.dataset.pupilId;
          const total = overallTotals.get(pupilId);
          overallCell.textContent = total === undefined ? '—' : formatGapNumber(total);
        });
      });
    };

    form.querySelectorAll('.js-gap-max, .js-gap-score').forEach((input) => input.addEventListener('input', updateGapTotals));

    document.querySelectorAll('.gap-paper-tabs a[role="tab"]').forEach((tab) => {
      tab.addEventListener('click', () => {
        if (activePaperField) {
          const url = new URL(tab.href, window.location.origin);
          activePaperField.value = url.searchParams.get('paper') || '';
        }
      });
    });

    updateGapTotals();
  });

  document.querySelectorAll('.js-ghost-select').forEach((select) => {
    const ghostLabel = select.dataset.ghostLabel || '';

    const syncGhostState = () => {
      if (select.value) {
        select.classList.remove('has-ghost-value');
        select.removeAttribute('title');
        return;
      }
      if (!ghostLabel) {
        select.classList.remove('has-ghost-value');
        select.removeAttribute('title');
        return;
      }
      select.classList.add('has-ghost-value');
      select.title = 'Previous term value — not counted until saved';
    };

    select.addEventListener('change', syncGhostState);
    syncGhostState();
  });


  document.querySelectorAll('.js-sats-sheet-form').forEach((form) => {
    const calcSources = {
      maths_raw_total: ['maths_arithmetic', 'maths_reasoning_1', 'maths_reasoning_2'],
      reading_raw_total: ['reading_paper'],
      spag_raw_total: ['spag_paper_1', 'spag_paper_2'],
    };

    const computeRowTotals = (pupilId) => {
      Object.entries(calcSources).forEach(([targetKey, sourceKeys]) => {
        const sourceInputs = sourceKeys
          .map((key) => form.querySelector(`input[data-pupil-id="${pupilId}"][data-column-key="${key}"]`))
          .filter((node) => node);
        const target = form.querySelector(`input.js-sats-calc-output[data-pupil-id="${pupilId}"][data-column-key="${targetKey}"]`);
        if (!target || !sourceInputs.length) return;

        const numericValues = sourceInputs
          .map((input) => (input.value === '' ? null : Number.parseFloat(input.value)))
          .filter((value) => value !== null && !Number.isNaN(value));

        target.value = numericValues.length ? `${numericValues.reduce((sum, value) => sum + value, 0)}` : '';
      });
    };

    const applyScaledTheme = (input) => {
      const cell = input.closest('td');
      if (!cell) return;
      cell.classList.remove('sats-scaled-low', 'sats-scaled-pass', 'sats-scaled-high');
      if (input.value === '') return;
      const value = Number.parseFloat(input.value);
      if (Number.isNaN(value)) return;
      if (value < 100) {
        cell.classList.add('sats-scaled-low');
      } else if (value >= 110) {
        cell.classList.add('sats-scaled-high');
      } else {
        cell.classList.add('sats-scaled-pass');
      }
    };

    const pupilIds = new Set(
      Array.from(form.querySelectorAll('input[data-pupil-id]')).map((input) => input.dataset.pupilId).filter((value) => value),
    );
    pupilIds.forEach((pupilId) => computeRowTotals(pupilId));

    form.querySelectorAll('.js-sats-paper-input').forEach((input) => {
      input.addEventListener('input', () => {
        if (input.dataset.pupilId) {
          computeRowTotals(input.dataset.pupilId);
        }
      });
    });

    form.querySelectorAll('.js-sats-scaled-input').forEach((input) => {
      applyScaledTheme(input);
      input.addEventListener('input', () => applyScaledTheme(input));
    });
  });
});
