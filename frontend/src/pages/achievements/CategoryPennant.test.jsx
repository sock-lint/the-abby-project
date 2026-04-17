import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import CategoryPennant from './CategoryPennant';

const category = { id: 7, name: 'Woodworking', icon: '🪵' };

describe('CategoryPennant', () => {
  it('renders the icon and name', () => {
    renderWithProviders(<CategoryPennant category={category} active={false} onClick={() => {}} />);
    expect(screen.getByText('🪵')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Woodworking/ })).toBeInTheDocument();
  });

  it('declares itself as an unselected tab when inactive', () => {
    renderWithProviders(<CategoryPennant category={category} active={false} onClick={() => {}} />);
    const tab = screen.getByRole('tab');
    expect(tab).toHaveAttribute('aria-selected', 'false');
  });

  it('declares itself as the selected tab when active', () => {
    renderWithProviders(<CategoryPennant category={category} active onClick={() => {}} />);
    const tab = screen.getByRole('tab');
    expect(tab).toHaveAttribute('aria-selected', 'true');
  });

  it('fires onClick when tapped', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(<CategoryPennant category={category} active={false} onClick={spy} />);
    await user.click(screen.getByRole('tab'));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('renders a level pip when summary is provided', () => {
    renderWithProviders(
      <CategoryPennant
        category={category}
        active
        onClick={() => {}}
        summary={{ level: 4 }}
      />,
    );
    expect(screen.getByText(/L ?4/i)).toBeInTheDocument();
  });
});
