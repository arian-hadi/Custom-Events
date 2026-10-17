/* Progressive enhancement: every admin destination remains available without JS. */
(() => {
  document.querySelectorAll('[data-bulk-delete]').forEach(button => {
    const actions = button.closest('.actions');
    const select = actions?.querySelector('select[name="action"]');
    const submit = actions?.querySelector('button[name="index"]');
    if (!select || !submit || !select.querySelector('option[value="delete_selected"]')) return;
    button.hidden = false;
    button.addEventListener('click', () => {
      select.value = 'delete_selected';
      // Preserve Django's selection, filtering, permissions and confirmation.
      submit.click();
    });
  });
})();
(() => {
  const wrapper = document.querySelector('[data-control-search]');
  const input = document.getElementById('control-module-search');
  if (!wrapper || !input) return;
  const sections = [...document.querySelectorAll('[data-control-section]')];
  const empty = document.querySelector('[data-control-no-results]');
  wrapper.hidden = false;
  input.addEventListener('input', () => {
    const terms = input.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    let count = 0;
    sections.forEach(section => {
      let matches = 0;
      section.querySelectorAll('[data-control-module]').forEach(row => {
        const label = row.dataset.searchLabel.toLocaleLowerCase();
        row.hidden = !terms.every(term => label.includes(term));
        if (!row.hidden) matches++;
      });
      section.hidden = matches === 0;
      count += matches;
    });
    if (empty) empty.hidden = count !== 0;
  });
})();
