/* Sysnet platform shared JS (vanilla, no dependencies) */
(function () {
  'use strict';

  // ---------- mobile sidebar ----------
  const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
  const sidebar = document.querySelector('.dash-sidebar');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  // ---------- confirm dialogs ----------
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      if (!window.confirm(form.dataset.confirm || 'Are you sure?')) e.preventDefault();
    });
  });

  // ---------- toast auto-dismiss ----------
  document.querySelectorAll('.alert[data-auto]').forEach((el) => {
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 400); }, 5000);
  });

  // ---------- document line builder ----------
  const lineTable = document.querySelector('[data-lines]');
  if (lineTable) {
    const products = window.SYSNET_PRODUCTS || [];
    const tbody = lineTable.querySelector('tbody');
    const countInput = lineTable.querySelector('input[name="lines-count"]');

    function money(n) {
      const v = parseFloat(n || 0);
      return isNaN(v) ? '0.00' : v.toFixed(2);
    }

    function recalc() {
      let subtotal = 0, vatTotal = 0, grossTotal = 0;
      tbody.querySelectorAll('tr[data-row]').forEach((row) => {
        const qty = parseFloat(row.querySelector('.f-qty').value) || 0;
        const price = parseFloat(row.querySelector('.f-price').value) || 0;
        const disc = parseFloat(row.querySelector('.f-disc').value) || 0;
        const mode = row.querySelector('.f-mode').value;
        const rate = parseFloat(row.querySelector('.f-tax').selectedOptions[0]?.dataset.rate || 0) || 0;

        const gross = qty * price;
        const afterDisc = gross * (1 - disc / 100);
        let net, vat;
        if (mode === 'inclusive' && rate > 0) {
          vat = afterDisc - afterDisc / (1 + rate / 100);
          net = afterDisc - vat;
        } else {
          net = afterDisc;
          vat = net * rate / 100;
        }
        net = money(net); vat = money(vat);
        row.querySelector('.c-net').textContent = net;
        row.querySelector('.c-vat').textContent = vat;
        row.querySelector('.c-total').textContent = money(afterDisc + (mode === 'inclusive' ? 0 : vat));

        subtotal += parseFloat(net);
        vatTotal += parseFloat(vat);
        grossTotal += parseFloat(afterDisc) + (mode === 'inclusive' ? 0 : parseFloat(vat));
      });
      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = money(v); };
      set('sum-net', subtotal);
      set('sum-vat', vatTotal);
      set('sum-total', grossTotal);
    }

    function rowHtml() {
      const opts = products.map((p) =>
        `<option value="${p.id}" data-price="${p.price}" data-unit="${p.unit || ''}" data-desc="${p.name}" data-tax="${p.tax_category_id || ''}">${p.name}</option>`
      ).join('');
      const taxOpts = (window.SYSNET_TAXES || []).map((t) =>
        `<option value="${t.id}" data-rate="${t.rate}">${t.name}</option>`
      ).join('');
      return `
        <tr data-row>
          <td>
            <select class="input f-item" style="min-width:11rem"><option value="">— Custom —</option>${opts}</select>
            <input class="input f-desc mt-1" placeholder="Description" style="min-width:11rem">
          </td>
          <td><input class="input f-unit" placeholder="e.g. item" style="width:5.5rem"></td>
          <td><input class="input f-qty" type="number" min="0.01" step="0.01" value="1" style="width:5rem"></td>
          <td><input class="input f-price" type="number" min="0" step="0.01" placeholder="0.00" style="width:7rem"></td>
          <td>
            <select class="input f-mode"><option value="exclusive">Excl. VAT</option><option value="inclusive">Incl. VAT</option></select>
          </td>
          <td><input class="input f-disc" type="number" min="0" max="100" step="0.01" value="0" style="width:5rem"></td>
          <td><select class="input f-tax" style="min-width:10rem"><option value="">Out of scope</option>${taxOpts}</select></td>
          <td class="num c-net">0.00</td>
          <td class="num c-vat">0.00</td>
          <td class="num c-total">0.00</td>
          <td><button type="button" class="btn btn-ghost btn-sm" data-remove title="Remove line">✕</button></td>
        </tr>`;
    }

    function addRow() {
      tbody.insertAdjacentHTML('beforeend', rowHtml());
      const row = tbody.lastElementChild;
      bindRow(row);
      recalc();
    }

    function bindRow(row) {
      const sel = row.querySelector('.f-item');
      sel.addEventListener('change', () => {
        const opt = sel.selectedOptions[0];
        if (!opt || !opt.value) return;
        row.querySelector('.f-desc').value = opt.dataset.desc || '';
        row.querySelector('.f-price').value = opt.dataset.price || '';
        row.querySelector('.f-unit').value = opt.dataset.unit || '';
        if (opt.dataset.tax) row.querySelector('.f-tax').value = opt.dataset.tax;
        recalc();
      });
      row.querySelectorAll('input, select').forEach((el) => el.addEventListener('input', recalc));
      row.querySelector('[data-remove]').addEventListener('click', () => {
        row.remove();
        if (!tbody.querySelector('tr[data-row]')) addRow();
        recalc();
      });
    }

    lineTable.querySelector('[data-add-line]').addEventListener('click', addRow);
    tbody.querySelectorAll('tr[data-row]').forEach(bindRow);

    // serialize rows into lines-N-* hidden convention on submit
    const form = lineTable.closest('form');
    form.addEventListener('submit', () => {
      const rows = [...tbody.querySelectorAll('tr[data-row]')];
      countInput.value = rows.length;
      rows.forEach((row, i) => {
        const p = `lines-${i}-`;
        const add = (name, cls, attr) => {
          const inp = document.createElement('input');
          inp.type = 'hidden';
          inp.name = p + name;
          inp.value = row.querySelector(cls)[attr] ?? '';
          form.appendChild(inp);
        };
        add('description', '.f-desc', 'value');
        add('unit', '.f-unit', 'value');
        add('quantity', '.f-qty', 'value');
        add('unit_price', '.f-price', 'value');
        add('pricing_mode', '.f-mode', 'value');
        add('discount_percent', '.f-disc', 'value');
        add('tax_category', '.f-tax', 'value');
        const itemSel = row.querySelector('.f-item');
        const hiddenItem = document.createElement('input');
        hiddenItem.type = 'hidden';
        hiddenItem.name = p + 'catalog_item_id';
        hiddenItem.value = itemSel.value || '';
        form.appendChild(hiddenItem);
      });
    });
    recalc();
  }
})();
