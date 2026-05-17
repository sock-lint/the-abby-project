import { describe, expect, it, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import QuestCodex from './QuestCodex.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const defBoss = (overrides = {}) => ({
  id: 1, name: 'Dragon Slayer', description: 'slay the dragon',
  icon: '🐲', sprite_key: '', quest_type: 'boss',
  quest_type_display: 'Boss Fight', target_value: 100,
  duration_days: 7, coin_reward: 50, xp_reward: 100, required_badge: null,
  ...overrides,
});
const defCollection = (overrides = {}) => ({
  id: 2, name: 'Berry Hunt', description: 'gather berries',
  icon: '🍓', sprite_key: '', quest_type: 'collection',
  quest_type_display: 'Collection Quest', target_value: 10,
  duration_days: 5, coin_reward: 20, xp_reward: 40, required_badge: null,
  ...overrides,
});
const questOf = (definition, status = 'completed', overrides = {}) => ({
  id: 99, status, definition, participants: [],
  current_progress: 100, effective_target: 100, progress_percent: 100,
  ...overrides,
});

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});

describe('QuestCodex', () => {
  it('renders the available chapter by default and lists its quests', async () => {
    render(
      <QuestCodex
        available={[defBoss({ id: 1, name: 'Available Boss' })]}
        activeQuest={null}
        history={[]}
        earnedBadgeIds={new Set()}
      />,
    );
    expect(await screen.findByText(/Available Boss/)).toBeInTheDocument();
    // Codex shelf shows all four chapter spines.
    expect(screen.getByRole('tab', { name: /Available/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Underway/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Closed/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Locked/ })).toBeInTheDocument();
  });

  it('prefers the underway chapter when an active quest exists', async () => {
    render(
      <QuestCodex
        available={[defBoss({ id: 1, name: 'Available Boss' })]}
        activeQuest={questOf(defBoss({ id: 2, name: 'Active Boss' }), 'active')}
        history={[]}
        earnedBadgeIds={new Set()}
      />,
    );
    expect(await screen.findByText(/Active Boss/)).toBeInTheDocument();
    // The available row should NOT be visible when underway is active.
    expect(screen.queryByText(/Available Boss/)).toBeNull();
  });

  it('switches the active chapter on shelf tab click and reflects it on the folio body', async () => {
    render(
      <QuestCodex
        available={[defBoss({ id: 1, name: 'Available Boss' })]}
        activeQuest={null}
        history={[questOf(defCollection({ id: 9, name: 'Old Collection' }), 'completed')]}
        earnedBadgeIds={new Set()}
      />,
    );
    expect(await screen.findByText(/Available Boss/)).toBeInTheDocument();

    const user = userEvent.setup();
    const closedSpine = screen.getByRole('tab', { name: /Closed/ });
    await user.click(closedSpine);

    await waitFor(() => {
      expect(screen.getByText(/Old Collection/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Available Boss/)).toBeNull();
  });

  it('persists the active chapter to localStorage and rehydrates on remount', async () => {
    const props = {
      available: [defBoss({ id: 1, name: 'Available Boss' })],
      activeQuest: null,
      history: [questOf(defCollection({ id: 9, name: 'Old Collection' }), 'completed')],
      earnedBadgeIds: new Set(),
    };
    const { unmount } = render(<QuestCodex {...props} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: /Closed/ }));
    await waitFor(() => {
      expect(screen.getByText(/Old Collection/)).toBeInTheDocument();
    });
    unmount();
    expect(window.localStorage.getItem('trials:codex:active-chapter')).toBe('closed');

    render(<QuestCodex {...props} />);
    // Closed chapter should be the active one on remount, not Available.
    expect(await screen.findByText(/Old Collection/)).toBeInTheDocument();
    expect(screen.queryByText(/Available Boss/)).toBeNull();
  });

  it('routes locked quests into their own chapter and renders the unlock hint', async () => {
    const locked = defBoss({
      id: 1, name: 'Hidden Trial',
      required_badge: 42, required_badge_name: 'Iron Will',
    });
    render(
      <QuestCodex
        available={[locked]}
        activeQuest={null}
        history={[]}
        earnedBadgeIds={new Set()}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: /Locked/ }));
    expect(await screen.findByText(/Hidden Trial/)).toBeInTheDocument();
    expect(screen.getByText(/Iron Will seal to unlock/i)).toBeInTheDocument();
  });

  it('shows the vessel filter shelf when the chapter holds 2+ kinds and filters tiles by kind', async () => {
    render(
      <QuestCodex
        available={[
          defBoss({ id: 1, name: 'Slay Beast' }),
          defCollection({ id: 2, name: 'Pick Apples' }),
        ]}
        activeQuest={null}
        history={[]}
        earnedBadgeIds={new Set()}
      />,
    );
    // Both render in the Available folio with the kind shelf above.
    expect(await screen.findByText(/Slay Beast/)).toBeInTheDocument();
    expect(screen.getByText(/Pick Apples/)).toBeInTheDocument();

    const user = userEvent.setup();
    const bossPill = screen.getByRole('tab', { name: /Boss \(1\)/ });
    await user.click(bossPill);

    await waitFor(() => {
      expect(screen.queryByText(/Pick Apples/)).toBeNull();
    });
    expect(screen.getByText(/Slay Beast/)).toBeInTheDocument();
  });

  it('fires onBegin with the QuestDefinition when an available tile Begin button is tapped', async () => {
    const onBegin = vi.fn();
    render(
      <QuestCodex
        available={[defBoss({ id: 7, name: 'Slay Beast' })]}
        activeQuest={null}
        history={[]}
        earnedBadgeIds={new Set()}
        onBegin={onBegin}
      />,
    );
    const user = userEvent.setup();
    const beginBtn = await screen.findByRole('button', { name: /^Begin$/ });
    await user.click(beginBtn);
    expect(onBegin).toHaveBeenCalledTimes(1);
    expect(onBegin.mock.calls[0][0]).toMatchObject({ id: 7, name: 'Slay Beast' });
  });

  it('hides the Begin button on available tiles when an active quest already exists', async () => {
    render(
      <QuestCodex
        available={[defBoss({ id: 7, name: 'Slay Beast' })]}
        activeQuest={questOf(defBoss({ id: 99, name: 'Other Active' }), 'active')}
        history={[]}
        earnedBadgeIds={new Set()}
      />,
    );
    const user = userEvent.setup();
    // Active chapter defaults to underway — switch to Available manually.
    await user.click(screen.getByRole('tab', { name: /Available/ }));
    await waitFor(() => {
      expect(screen.getByText(/Slay Beast/)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /^Begin$/ })).toBeNull();
  });
});
