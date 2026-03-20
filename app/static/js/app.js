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
    const totalMaxCells = () => Array.from(table.querySelectorAll('.js-gap-total-max'));
    const addPanel = document.querySelector('.js-gap-add-panel');
    const addButton = document.querySelector('.js-gap-add-question');
    const selectedPaper = addPanel?.dataset.selectedPaper || 'paper_1';

    const updateGapTotals = () => {
      const totalMax = maxInputs().reduce((sum, input) => sum + (Number.parseFloat(input.value || '0') || 0), 0);
      totalMaxCells().forEach((cell) => {
        cell.textContent = totalMax;
      });
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

    table.addEventListener('input', (event) => {
      if (event.target.matches('.js-gap-max, .js-gap-score')) {
        updateGapTotals();
      }
    });

    const addQuestionColumn = () => {
      if (!addPanel) return;
      const labelInput = addPanel.querySelector('.js-gap-add-label');
      const typeInput = addPanel.querySelector('.js-gap-add-type');
      const maxInput = addPanel.querySelector('.js-gap-add-max');
      const orderInput = addPanel.querySelector('.js-gap-add-order');
      const label = labelInput?.value.trim() || '';
      const topic = typeInput?.value.trim() || '';
      const maxValue = maxInput?.value || '1';
      const displayOrder = orderInput?.value || String(maxInputs().length + 1);

      if (!label) {
        labelInput?.focus();
        return;
      }

      const headRows = table.querySelectorAll('thead tr');
      const bodyRows = table.querySelectorAll('tbody tr');
      const footerRow = table.querySelector('tfoot tr');
      const totalHeaderCount = 2;

      if (headRows.length < 4 || !footerRow) return;

      const labelCell = document.createElement('th');
      labelCell.setAttribute('data-gap-col', '');
      labelCell.innerHTML = `
        <input type="hidden" name="question_id[]" value="">
        <input type="hidden" name="question_paper[]" value="${selectedPaper}">
        <input type="text" class="form-control form-control-sm" name="question_label[]" value="${label}" placeholder="Label">
      `;

      const topicCell = document.createElement('th');
      topicCell.setAttribute('data-gap-col', '');
      topicCell.innerHTML = `<input type="text" class="form-control form-control-sm" name="question_type[]" value="${topic}" placeholder="Topic">`;

      const maxCell = document.createElement('th');
      maxCell.setAttribute('data-gap-col', '');
      maxCell.innerHTML = `<input type="number" min="0" class="form-control form-control-sm js-gap-max" name="question_max[]" value="${maxValue}">`;

      const orderCell = document.createElement('th');
      orderCell.setAttribute('data-gap-col', '');
      orderCell.innerHTML = `<input type="number" min="1" class="form-control form-control-sm" name="question_display_order[]" value="${displayOrder}">`;

      headRows[0].insertBefore(labelCell, headRows[0].children[headRows[0].children.length - totalHeaderCount]);
      headRows[1].insertBefore(topicCell, headRows[1].children[headRows[1].children.length - totalHeaderCount]);
      headRows[2].insertBefore(maxCell, headRows[2].children[headRows[2].children.length - totalHeaderCount]);
      headRows[3].insertBefore(orderCell, headRows[3].children[headRows[3].children.length - totalHeaderCount]);

      bodyRows.forEach((row) => {
        if (!row.querySelector('.js-gap-row-total')) return;
        const td = document.createElement('td');
        td.setAttribute('data-gap-col', '');
        td.innerHTML = '<div class="small text-muted">Save first</div>';
        row.insertBefore(td, row.children[row.children.length - 2]);
      });

      const footerCell = document.createElement('th');
      footerCell.setAttribute('data-gap-col', '');
      footerCell.textContent = '—';
      footerRow.insertBefore(footerCell, footerRow.children[footerRow.children.length - totalHeaderCount]);

      if (orderInput) orderInput.value = String(maxInputs().length + 1);
      if (labelInput) labelInput.value = '';
      if (typeInput) typeInput.value = '';
      if (maxInput) maxInput.value = '1';
      updateGapTotals();
    };

    addButton?.addEventListener('click', addQuestionColumn);
    updateGapTotals();
  });
});
