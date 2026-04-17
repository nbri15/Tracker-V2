document.addEventListener('DOMContentLoaded', () => {
  const serialiseFieldValue = (field) => {
    if (field.tagName === 'SELECT') {
      return field.options[field.selectedIndex]?.textContent?.trim() || '';
    }
    if (field.type === 'checkbox' || field.type === 'radio') {
      return field.checked ? '✓' : '';
    }
    return field.value;
  };

  const replaceFormFieldsForPdf = (root) => {
    root.querySelectorAll('input, select, textarea').forEach((field) => {
      if (field.type === 'hidden') {
        field.remove();
        return;
      }
      const value = serialiseFieldValue(field);
      const replacement = document.createElement('span');
      replacement.className = 'form-control form-control-sm d-inline-block';
      replacement.style.minHeight = 'calc(1.5em + .5rem + 2px)';
      replacement.style.backgroundColor = '#fff';
      replacement.textContent = value || '—';
      field.replaceWith(replacement);
    });
  };

  const createPdfFromSection = async (button) => {
    const targetSelector = button.dataset.pdfTarget;
    const target = targetSelector ? document.querySelector(targetSelector) : null;
    if (!target) return;
    const jsPdf = window.jspdf?.jsPDF;
    if (!jsPdf || !window.html2canvas) {
      window.alert('PDF export libraries are unavailable. Please refresh and try again.');
      return;
    }

    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = 'Preparing PDF...';

    try {
      const clone = target.cloneNode(true);
      clone.querySelectorAll('[data-pdf-exclude], .no-pdf').forEach((node) => node.remove());
      replaceFormFieldsForPdf(clone);

      const staging = document.createElement('div');
      staging.style.position = 'fixed';
      staging.style.left = '-100000px';
      staging.style.top = '0';
      staging.style.padding = '16px';
      staging.style.background = '#fff';
      staging.style.width = `${Math.max(target.scrollWidth, target.clientWidth)}px`;
      staging.appendChild(clone);
      document.body.appendChild(staging);

      const canvas = await window.html2canvas(staging, {
        backgroundColor: '#ffffff',
        scale: 2,
        useCORS: true,
      });
      staging.remove();

      const orientation = canvas.width > canvas.height ? 'landscape' : 'portrait';
      const pdf = new jsPdf({ orientation, unit: 'mm', format: 'a4', compress: true });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const imgWidth = pageWidth - 10;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;

      let heightLeft = imgHeight;
      let position = 5;

      const imgData = canvas.toDataURL('image/png');
      pdf.addImage(imgData, 'PNG', 5, position, imgWidth, imgHeight, undefined, 'FAST');
      heightLeft -= pageHeight - 10;

      while (heightLeft > 0) {
        position = heightLeft - imgHeight + 5;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 5, position, imgWidth, imgHeight, undefined, 'FAST');
        heightLeft -= pageHeight - 10;
      }

      const fallbackName = (document.title || 'tracker').toLowerCase().replace(/[^a-z0-9]+/g, '-');
      const filename = button.dataset.pdfFilename || `${fallbackName}-snapshot.pdf`;
      pdf.save(filename.endsWith('.pdf') ? filename : `${filename}.pdf`);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('PDF export failed', error);
      window.alert('Could not generate the PDF from this view. Please try again.');
    } finally {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  };

  document.querySelectorAll('.js-download-pdf').forEach((button) => {
    button.addEventListener('click', () => createPdfFromSection(button));
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
