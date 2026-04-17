import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AvatarMenu from './AvatarMenu.jsx';

function renderMenu(props = {}) {
  return render(
    <MemoryRouter>
      <AvatarMenu
        user={{ username: 'abby', display_name: 'Abby', role: 'child' }}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe('AvatarMenu', () => {
  it('shows the initial from display_name', () => {
    renderMenu();
    // "Abby" → "A" initial; there are two "A"s rendered (trigger + menu).
    expect(screen.getAllByText('A').length).toBeGreaterThan(0);
  });

  it('falls back to username initial when no display_name', () => {
    renderMenu({ user: { username: 'xyz', role: 'child' } });
    expect(screen.getAllByText('X').length).toBeGreaterThan(0);
  });

  it('falls back to ? when the user is null', () => {
    renderMenu({ user: null });
    expect(screen.getAllByText('?').length).toBeGreaterThan(0);
  });

  it('opens the menu on button click and closes on escape', async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    await user.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    await user.keyboard('{Escape}');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('closes when clicking outside', async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    await user.click(document.body);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('renders a Sigil menu link pointing to /sigil', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    const link = screen.getByRole('menuitem', { name: /sigil/i });
    expect(link.getAttribute('href')).toBe('/sigil');
  });

  it('clicking the Sigil link closes the menu', async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.click(trigger);
    const link = screen.getByRole('menuitem', { name: /sigil/i });
    await user.click(link);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('renders a Settings menu link pointing to /settings', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    const link = screen.getByRole('menuitem', { name: /settings/i });
    expect(link.getAttribute('href')).toBe('/settings');
  });

  it('clicking the Settings link closes the menu', async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.click(trigger);
    const link = screen.getByRole('menuitem', { name: /settings/i });
    await user.click(link);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('supports the compact prop (left-align anchor classes)', () => {
    const { container } = renderMenu({ compact: true });
    expect(container.querySelector('.w-9')).toBeTruthy();
  });

  it('supports align=top anchor classes', async () => {
    const user = userEvent.setup();
    renderMenu({ align: 'top' });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.getByRole('menu').className).toContain('bottom-full');
  });

  it('falls back to "adventurer" and "traveler" in the header when user fields are missing', async () => {
    const user = userEvent.setup();
    renderMenu({ user: {} });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.getByText('adventurer')).toBeInTheDocument();
    expect(screen.getByText('traveler')).toBeInTheDocument();
  });

  it('renders an <img> when user.avatar is set', () => {
    const { container } = renderMenu({
      user: {
        username: 'abby', display_name: 'Abby', role: 'child',
        avatar: 'https://example.com/avatar.png',
      },
    });
    const img = container.querySelector('img[src="https://example.com/avatar.png"]');
    expect(img).toBeTruthy();
  });
});
