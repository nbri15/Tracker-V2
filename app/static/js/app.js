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

  document.querySelectorAll('.js-gap-table').forEach((table) => {
    const maxInputs = () => Array.from(table.querySelectorAll('.js-gap-max'));
    const rowTotals = () => table.querySelectorAll('tbody tr');
    const totalMaxCell = table.querySelector('.js-gap-total-max');

    const updateGapTotals = () => {
      const totalMax = maxInputs().reduce((sum, input) => sum + (Number.parseFloat(input.value || '0') || 0), 0);
      if (totalMaxCell) totalMaxCell.textContent = totalMax;
      rowTotals().forEach((row) => {
        const scoreInputs = row.querySelectorAll('.js-gap-score');
        const totalCell = row.querySelector('.js-gap-row-total');
        const values = Array.from(scoreInputs).map((input) => (input.value === '' ? null : Number.parseFloat(input.value)));
        if (!values.length || values.every((value) => value === null)) {
          totalCell.textContent = '—';
          return;
        }
        const total = values.reduce((sum, value) => sum + (value || 0), 0);
        totalCell.textContent = Number.isInteger(total) ? total : total.toFixed(1);
      });
    };

    table.querySelectorAll('.js-gap-max, .js-gap-score').forEach((input) => input.addEventListener('input', updateGapTotals));
    updateGapTotals();
  });
});
