import { waitFor, within } from '@testing-library/react';

/** Open the shared dropdown and query its visible, accessible listbox. */
export async function openDropdown(user, control) {
  await waitFor(() => {
    if (control.disabled) throw new Error('Dropdown is still disabled');
  });
  if (control.getAttribute('aria-expanded') !== 'true') await user.click(control);
  const listbox = document.getElementById(control.getAttribute('aria-controls'));
  if (!listbox || listbox.getAttribute('role') !== 'listbox') {
    throw new Error('Dropdown did not open its controlled listbox');
  }
  return within(listbox);
}

/** Choose an enabled option by its raw API value or its visible label. */
export async function selectDropdown(user, control, valueOrLabel) {
  const listbox = await openDropdown(user, control);
  const options = listbox.getAllByRole('option');
  const enabled = options.filter((item) => item.getAttribute('aria-disabled') !== 'true');
  const value = String(valueOrLabel);
  const option = enabled.find((item) => item.getAttribute('data-value') === value)
    ?? enabled.find((item) => item.textContent.trim() === value);
  if (!option) throw new Error(`Dropdown has no option matching "${value}"`);
  await user.click(option);
}
