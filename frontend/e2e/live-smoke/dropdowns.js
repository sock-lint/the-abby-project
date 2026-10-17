// Only the expanded dropdown exposes a visible listbox.
export function dropdownListbox(control) {
  return control.page().getByRole('listbox').filter({
    visible: true,
  });
}

export async function chooseDropdown(control, selection) {
  // Small setContent fixtures intentionally retain native HTML selects.
  if (await control.evaluate(element => element.tagName === 'SELECT')) {
    await control.selectOption(selection, { timeout: 6_000 });
    return;
  }
  await control.click({ timeout: 6_000 });
  // Follow the control's own popup ID: it may portal outside its form.
  const id = await control.getAttribute('aria-controls');
  const listbox = control.page().locator(`[id=${JSON.stringify(id)}]`);
  const option = typeof selection === 'object' && 'label' in selection
    ? listbox.getByRole('option', { name: selection.label, exact: true })
    : listbox.locator(`[role="option"][data-value=${JSON.stringify(String(selection))}]`);
  await option.click({ timeout: 6_000 });
}

// Enumerate rendered choices while keeping focus and popup state predictable.
// Native compatibility permits the same reviewed harness to inspect old UI and
// disposable DOM fixtures during a staged application upgrade.
export async function dropdownValues(control) {
  if (await control.evaluate(element => element.tagName === 'SELECT')) {
    return control.locator('option').evaluateAll(options => options.map(option => option.value));
  }
  await control.click({ timeout: 6_000 });
  try {
    const id = await control.getAttribute('aria-controls');
    const listbox = control.page().locator(`[id=${JSON.stringify(id)}]`);
    await listbox.waitFor({ state: 'visible', timeout: 6_000 });
    return await listbox.getByRole('option').evaluateAll(options => options.map(option => option.dataset.value));
  } finally {
    await control.press('Escape', { timeout: 6_000 });
  }
}
