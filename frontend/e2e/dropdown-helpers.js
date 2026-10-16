// Only the expanded dropdown exposes a visible listbox.
export function dropdownListbox(control) {
  return control.page().getByRole('listbox').filter({
    visible: true,
  });
}

export async function chooseDropdown(control, selection) {
  // Small setContent fixtures intentionally retain native HTML selects.
  if (await control.evaluate(element => element.tagName === 'SELECT')) {
    await control.selectOption(selection);
    return;
  }
  await control.click();
  // Follow the control's own popup ID: it may portal outside its form.
  const id = await control.getAttribute('aria-controls');
  const listbox = control.page().locator(`[id=${JSON.stringify(id)}]`);
  const option = typeof selection === 'object' && 'label' in selection
    ? listbox.getByRole('option', { name: selection.label, exact: true })
    : listbox.locator(`[role="option"][data-value=${JSON.stringify(String(selection))}]`);
  await option.click();
}
