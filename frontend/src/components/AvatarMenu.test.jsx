import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AvatarMenu from './AvatarMenu.jsx';
import { PulseContext } from '../providers/pulseContext';

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
  it('keeps the compact portrait and level together and repeats the saved identity in the menu', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><PulseContext.Provider value={{ pulse: { identity: {
      id: 7, active_title: { name: 'Chore Hero', icon: '🧹' },
      active_trophy_badge: { name: 'First Dollar', icon: '🏅' },
    }, header: { level: 3 } } }}>
      <AvatarMenu compact user={{ id: 7, username: 'test3', display_name: 'Test child', role: 'child', family: { name: 'Default Family' } }} />
    </PulseContext.Provider></MemoryRouter>);
    const trigger = screen.getByRole('button', { name: 'Open profile menu' });
    expect(within(trigger).getByLabelText('Level 3')).toHaveTextContent('Lv. 3');
    expect(within(trigger).getByText('Test child')).toBeInTheDocument();
    expect(within(trigger).queryByText('Default Family')).not.toBeInTheDocument();
    expect(within(trigger).queryByText('child')).not.toBeInTheDocument();

    await user.click(trigger);
    const menu = screen.getByRole('menu', { name: 'Profile' });
    expect(within(menu).getByText('Test child')).toBeInTheDocument();
    expect(menu).toHaveTextContent(/child · Default Family/i);
    expect(within(menu).getByText('Chore Hero')).toBeInTheDocument();
    expect(within(menu).getByText('First Dollar')).toBeInTheDocument();
    expect(within(menu).getByLabelText('Level 3')).toHaveTextContent('Lv. 3');
    expect(within(menu).getByText('🧹')).toBeInTheDocument();
    expect(within(menu).getByText('🏅')).toBeInTheDocument();
    expect(menu.querySelector('[data-portrait-frame]')).toBeInTheDocument();
  });

  it('keeps the account name visible without a saved title or level', () => {
    renderMenu({ compact: true });
    const trigger = screen.getByRole('button', { name: 'Open profile menu' });
    expect(within(trigger).getByText('Abby')).toBeInTheDocument();
    expect(within(trigger).queryByLabelText(/^Level /)).not.toBeInTheDocument();
    expect(within(trigger).queryByText('child')).not.toBeInTheDocument();
  });

  it('shows a confirmed level zero instead of treating it as missing', () => {
    render(<MemoryRouter><PulseContext.Provider value={{ pulse: {
      identity: { id: 7 }, header: { level: 0 },
    } }}>
      <AvatarMenu compact user={{ id: 7, username: 'abby', display_name: 'Abby', role: 'child' }} />
    </PulseContext.Provider></MemoryRouter>);
    expect(within(screen.getByRole('button', { name: 'Open profile menu' })).getByLabelText('Level 0')).toHaveTextContent('Lv. 0');
  });

  it('does not attach a previous account’s saved look or level to this account', async () => {
    render(<MemoryRouter><PulseContext.Provider value={{ pulse: {
      identity: { id: 88, active_title: { name: 'Previous title' }, active_trophy_badge: { name: 'Previous badge' } },
      header: { level: 6 },
    } }}>
      <AvatarMenu compact user={{ id: 7, username: 'abby', display_name: 'Abby', role: 'child' }} />
    </PulseContext.Provider></MemoryRouter>);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Open profile menu' }));
    expect(screen.queryByText('Previous title')).not.toBeInTheDocument();
    expect(screen.queryByText('Previous badge')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Level /)).not.toBeInTheDocument();
  });

  it('shows the initial from display_name', () => {
    renderMenu();
    // "Abby" → "A" initial; there are two "A"s rendered (trigger + menu).
    expect(screen.getAllByText('A').length).toBeGreaterThan(0);
  });

  it('falls back to username initial when no display_name', () => {
    renderMenu({ user: { username: 'xyz', role: 'child' } });
    expect(screen.getAllByText('X').length).toBeGreaterThan(0);
  });

  it('keeps a readable member fallback when the user is null', () => {
    renderMenu({ user: null });
    const trigger = screen.getByRole('button', { name: 'Open profile menu' });
    expect(within(trigger).getByText('Member')).toBeInTheDocument();
    expect(within(trigger).queryByLabelText(/^Level /)).not.toBeInTheDocument();
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
    expect(trigger).toHaveFocus();
  });

  it('supports arrow entry, wrapping, Home and End across the parent utility links', async () => {
    const user = userEvent.setup();
    renderMenu({ user: { username: 'dad', display_name: 'Dad', role: 'parent' } });
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.tab();
    await user.keyboard('{ArrowDown}');
    const menu = screen.getByRole('menu', { name: 'Profile' });
    expect(trigger).toHaveAttribute('aria-controls', menu.id);
    const sigil = screen.getByRole('menuitem', { name: /profile/i });
    const settings = screen.getByRole('menuitem', { name: /settings/i });
    expect(sigil).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(settings).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(sigil).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: /manage/i })).toHaveFocus();
    await user.keyboard('{End}');
    expect(settings).toHaveFocus();
    await user.keyboard('{Home}');
    expect(sigil).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(settings).toHaveFocus();
  });

  it('closes on Tab and continues to the next control outside the menu', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AvatarMenu user={{ username: 'abby', display_name: 'Abby', role: 'child' }} />
        <button type="button">Next action</button>
      </MemoryRouter>,
    );
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.click(trigger);
    expect(screen.getByRole('menuitem', { name: /profile/i })).toHaveFocus();
    await user.tab();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Next action' })).toHaveFocus();
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

  it('renders a Profile menu link pointing to /sigil', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    const link = screen.getByRole('menuitem', { name: /profile/i });
    expect(link.getAttribute('href')).toBe('/sigil');
  });

  it('clicking the Profile link closes the menu', async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole('button', { name: /profile menu/i });
    await user.click(trigger);
    const link = screen.getByRole('menuitem', { name: /profile/i });
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

  it('opens the compact profile menu from a portrait-sized trigger', async () => {
    const { container } = renderMenu({ compact: true });
    expect(container.querySelector('[data-portrait-frame]')).toHaveStyle({ '--portrait-size': '40px' });
    await userEvent.setup().click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.getByRole('menu')).toHaveClass('left-0');
  });

  it('supports align=top anchor classes', async () => {
    const user = userEvent.setup();
    renderMenu({ align: 'top' });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.getByRole('menu').className).toContain('bottom-full');
  });

  it('keeps a readable menu identity when user fields are missing', async () => {
    const user = userEvent.setup();
    renderMenu({ user: {} });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    const menu = screen.getByRole('menu', { name: 'Profile' });
    expect(within(menu).getByText('Member')).toBeInTheDocument();
    expect(within(menu).queryByLabelText(/^Level /)).not.toBeInTheDocument();
  });

  it('renders Manage / Activity / Content Catalog menu items for parents', async () => {
    const user = userEvent.setup();
    renderMenu({ user: { username: 'dad', display_name: 'Dad', role: 'parent' } });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.getByRole('menuitem', { name: /manage/i }).getAttribute('href')).toBe('/manage');
    expect(screen.getByRole('menuitem', { name: /activity/i }).getAttribute('href')).toBe('/activity');
    expect(
      screen.getByRole('menuitem', { name: /content catalog/i }).getAttribute('href'),
    ).toBe('/codex');
  });

  it('does not describe the /codex row as Lorebook authoring', async () => {
    const user = userEvent.setup();
    renderMenu({ user: { username: 'dad', display_name: 'Dad', role: 'parent' } });
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    // /codex administers the RPG content catalog. The Lorebook is a separate
    // kid-facing page, and "Codex" already names the Bestiary species tab —
    // the row has to agree with the page heading ("Content Catalog").
    const row = screen.getByRole('menuitem', { name: /content catalog/i });
    expect(row.textContent).not.toMatch(/lorebook/i);
    expect(screen.queryByRole('menuitem', { name: /^codex$/i })).toBeNull();
  });

  it('hides the parent-only menu items for child users', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(screen.queryByRole('menuitem', { name: /manage/i })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /activity/i })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /content catalog/i })).toBeNull();
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
