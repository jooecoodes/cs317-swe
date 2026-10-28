// A touch-friendly combobox. The saved value is always an actual employee ID.
export function employeeMatches(employees, query) {
  const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return employees.filter(employee => words.every(word =>
    `${employee.name} ${employee.id} ${employee.department || ''}`.toLocaleLowerCase().includes(word)
  ));
}

export function bindEmployeePicker(root, employees, selectedId, esc) {
  const input = root.querySelector('#record-employee');
  const value = root.querySelector('#record-employee-id');
  const list = root.querySelector('#employee-suggestions');
  const status = root.querySelector('#employee-picker-status');
  const picker = input.closest('.employee-picker');
  const label = employee => `${employee.name} · ${employee.id}`;
  let selected = employees.find(employee => employee.id === selectedId);
  let matches = [];
  let active = -1;

  function validate() {
    input.setCustomValidity(value.value ? '' : 'Choose an employee from the suggestions.');
  }
  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }
  function choose(employee) {
    selected = employee;
    input.value = label(employee);
    value.value = employee.id;
    validate();
    close();
    status.textContent = `Selected: ${employee.name}, ${employee.id}.`;
  }
  function highlight(index) {
    active = index;
    [...list.querySelectorAll('[role="option"]')].forEach((option, i) => option.setAttribute('aria-selected', String(i === active)));
    if (active >= 0) {
      const option = list.querySelectorAll('[role="option"]')[active];
      input.setAttribute('aria-activedescendant', option.id);
      option.scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }
  function show() {
    const query = selected && input.value === label(selected) ? '' : input.value;
    const all = employeeMatches(employees, query);
    matches = all.slice(0, 6);
    active = -1;
    input.removeAttribute('aria-activedescendant');
    list.innerHTML = matches.map((employee, index) => `<button type="button" role="option" aria-selected="false" tabindex="-1" id="employee-option-${index}" data-employee-option="${index}"><strong>${esc(employee.name)}</strong><span>${esc(employee.id)}${employee.department ? ` · ${esc(employee.department)}` : ''}</span></button>`).join('');
    list.hidden = !matches.length;
    input.setAttribute('aria-expanded', String(matches.length > 0));
    status.textContent = matches.length ? `${matches.length} suggestion${matches.length === 1 ? '' : 's'}${all.length > 6 ? ` of ${all.length} matches; keep typing to narrow the list` : ''}. Tap a name to select.` : 'No matching employees. Try another name or employee code.';
  }
  if (selected) choose(selected);
  else validate();
  input.addEventListener('focus', show);
  input.addEventListener('input', () => {
    selected = null;
    value.value = '';
    validate();
    show();
  });
  input.addEventListener('blur', () => {
    if (!value.value) {
      const exact = employees.filter(employee => [employee.name, employee.id, label(employee)].some(text => text.toLocaleLowerCase() === input.value.trim().toLocaleLowerCase()));
      if (exact.length === 1) choose(exact[0]);
    }
    close();
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (list.hidden) show();
      if (matches.length) highlight(event.key === 'ArrowDown' ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1));
    } else if (event.key === 'Enter' && !list.hidden && matches.length) {
      event.preventDefault();
      choose(matches[active < 0 ? 0 : active]);
    } else if (event.key === 'Escape' && !list.hidden) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  });
  // Keep the keyboard/input focus while a touch or mouse selects a suggestion.
  list.addEventListener('pointerdown', event => {
    if (event.target.closest('[data-employee-option]')) event.preventDefault();
  });
  list.addEventListener('click', event => {
    const option = event.target.closest('[data-employee-option]');
    if (option && matches[Number(option.dataset.employeeOption)]) choose(matches[Number(option.dataset.employeeOption)]);
  });
  picker.addEventListener('focusout', event => {
    if (!picker.contains(event.relatedTarget)) close();
  });
}
