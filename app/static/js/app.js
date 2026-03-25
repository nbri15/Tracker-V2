document.addEventListener('DOMContentLoaded', () => {
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

        if (values.some((value) => Number.isNaN(value)) || values.includes(null)) {
          combinedCell.textContent = '—';
          percentCell.textContent = '—';
          bandCell.innerHTML = '<span class="text-muted">—</span>';
          return;
        }

        const combined = values[0] + values[1];
        const percent = combinedMax ? ((combined / combinedMax) * 100).toFixed(1) : null;
        let band = 'On Track';
        if (percent === null) {
          band = '—';
        } else if (Number.parseFloat(percent) < belowThreshold) {
          band = 'Working Towards';
        } else if (Number.parseFloat(percent) >= exceedingThreshold) {
          band = 'Exceeding';
        }

        combinedCell.textContent = combined;
        percentCell.textContent = percent === null ? '—' : `${percent}%`;
        bandCell.innerHTML = percent === null ? '<span class="text-muted">—</span>' : `<span class="badge text-bg-light border">${band}</span>`;
      };

      paperInputs.forEach((input) => input.addEventListener('input', updateRow));
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
  });
});
