import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DropdownShowcase from './DropdownShowcase';
import { openDropdown, selectDropdown } from '../../test/selectDropdown';

describe('Dropdown design examples', () => {
  it('lets visitors try grouped choices and a modal form without sending account requests', async () => {
    const user = userEvent.setup();
    const request = vi.spyOn(globalThis, 'fetch');
    try {
      render(<DropdownShowcase />);
      const grouped = screen.getByRole('combobox', { name: 'Grouped activities' });
      const options = await openDropdown(user, grouped);
      expect(options.getByRole('group', { name: 'Creative' })).toBeInTheDocument();
      expect(options.getByRole('option', { name: 'Swimming — unavailable' })).toHaveAttribute('aria-disabled', 'true');
      await selectDropdown(user, grouped, 'walking');
      expect(grouped).toHaveTextContent('Walking');
      await user.click(screen.getByRole('button', { name: 'Preview dropdown in a form' }));
      const dialog = screen.getByRole('dialog', { name: 'Dropdown form preview' });
      await selectDropdown(user, within(dialog).getByRole('combobox', { name: 'Assignment child' }), 'Riley');
      await user.click(within(dialog).getByRole('button', { name: 'Use selection' }));
      expect(screen.getByRole('status', { name: 'Dropdown preview selection' })).toHaveTextContent('Selected child: Riley. No account data was saved.');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(request).not.toHaveBeenCalled();
    } finally {
      request.mockRestore();
    }
  });
});
