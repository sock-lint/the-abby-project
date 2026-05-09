import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CatalogSearch from './CatalogSearch.jsx';

describe('CatalogSearch', () => {
  it('emits the typed value', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CatalogSearch value="" onChange={onChange} />);
    await user.type(screen.getByRole('searchbox', { name: /filter catalog/i }), 'a');
    expect(onChange).toHaveBeenCalledWith('a');
  });

  it('shows a clear button only when value is non-empty', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<CatalogSearch value="" onChange={onChange} />);
    expect(screen.queryByRole('button', { name: /clear filter/i })).toBeNull();

    rerender(<CatalogSearch value="dragon" onChange={onChange} />);
    const clear = screen.getByRole('button', { name: /clear filter/i });
    await user.click(clear);
    expect(onChange).toHaveBeenLastCalledWith('');
  });
});
