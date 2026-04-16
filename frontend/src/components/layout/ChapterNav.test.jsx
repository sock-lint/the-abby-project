import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ChapterNav, { ChapterBottomBar, ChapterSidebar } from './ChapterNav.jsx';
import { buildParent, buildUser } from '../../test/factories.js';

function renderSidebar(user, onLogout = vi.fn()) {
  return render(
    <MemoryRouter>
      <ChapterSidebar user={user} onLogout={onLogout} />
    </MemoryRouter>,
  );
}

describe('ChapterSidebar', () => {
  it('renders the five chapter links for any user', () => {
    renderSidebar(buildUser());
    for (const label of ['Today', 'Quests', 'Bestiary', 'Treasury', 'Atlas']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('shows Manage only for parents', () => {
    renderSidebar(buildParent({ display_name: 'Dad' }));
    expect(screen.getByText('Manage')).toBeInTheDocument();
  });

  it('hides Manage for children', () => {
    renderSidebar(buildUser());
    expect(screen.queryByText('Manage')).toBeNull();
  });

  it('fires onLogout when Sign off is clicked', async () => {
    const onLogout = vi.fn();
    const user = userEvent.setup();
    renderSidebar(buildUser(), onLogout);
    await user.click(screen.getByRole('button', { name: /sign off/i }));
    expect(onLogout).toHaveBeenCalled();
  });

  it('renders vol. I with the user display name', () => {
    renderSidebar(buildUser({ display_name: 'Abby' }));
    expect(screen.getByText(/vol\. I — Abby/i)).toBeInTheDocument();
  });

  it('falls back to "adventurer" when no user fields', () => {
    renderSidebar({});
    expect(screen.getByText(/vol\. I — adventurer/i)).toBeInTheDocument();
  });
});

describe('ChapterBottomBar', () => {
  it('renders the five chapter links', () => {
    render(
      <MemoryRouter>
        <ChapterBottomBar />
      </MemoryRouter>,
    );
    for (const label of ['Today', 'Quests', 'Bestiary', 'Treasury', 'Atlas']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});

describe('default export', () => {
  it('exposes both parts', () => {
    expect(ChapterNav.ChapterSidebar).toBe(ChapterSidebar);
    expect(ChapterNav.ChapterBottomBar).toBe(ChapterBottomBar);
  });
});
