import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import ActiveQuestFolio from './ActiveQuestFolio';

function buildQuest(overrides = {}) {
  return {
    id: 9,
    status: 'active',
    current_progress: 25,
    effective_target: 100,
    progress_percent: 25,
    end_date: '2026-09-04T23:00:00-07:00',
    participants: [],
    rage_shield: 0,
    definition: {
      id: 2, name: 'Dragon Slayer', quest_type: 'boss', target_value: 100,
      description: 'Private challenge details', icon: '🐲',
      coin_reward: 50, xp_reward: 100,
    },
    ...overrides,
  };
}

describe('ActiveQuestFolio calendar export', () => {
  it('exports the exact challenge deadline as a timed calendar event', async () => {
    const { user } = renderWithProviders(<ActiveQuestFolio quest={buildQuest()} />);
    await user.click(screen.getByRole('button', { name: 'Add Challenge deadline: Dragon Slayer to calendar' }));
    const google = screen.getByRole('link', { name: 'Google Calendar' });
    const event = new URL(google.href).searchParams;
    expect(event.get('text')).toBe('Challenge deadline: Dragon Slayer');
    expect(event.get('dates')).toBe('20260905T060000Z/20260905T063000Z');
    expect(event.get('details')).toContain('/quests?tab=trials');
    expect(event.get('details')).not.toContain('Private challenge details');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeInTheDocument();
    google.addEventListener('click', (e) => e.preventDefault());
    await user.click(google);
  });

  it('omits calendar export without a saved challenge deadline', () => {
    renderWithProviders(<ActiveQuestFolio quest={buildQuest({ end_date: null })} />);
    expect(screen.queryByRole('button', { name: /add .* to calendar/i })).not.toBeInTheDocument();
  });

  it('downloads an Apple Calendar event at the exact timed challenge deadline', async () => {
    const NativeURL = URL;
    const realSetTimeout = globalThis.setTimeout;
    vi.stubGlobal('URL', class extends NativeURL {
      static createObjectURL = vi.fn(() => 'blob:challenge-calendar');
      static revokeObjectURL = vi.fn();
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const timeout = vi.spyOn(globalThis, 'setTimeout').mockImplementation((callback, delay, ...args) => (
      delay === 60000 ? 0 : realSetTimeout(callback, delay, ...args)
    ));
    try {
      const { user } = renderWithProviders(<ActiveQuestFolio quest={buildQuest()} />);
      await user.click(screen.getByRole('button', { name: 'Add Challenge deadline: Dragon Slayer to calendar' }));
      await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
      expect(click).toHaveBeenCalledTimes(1);
      expect(click.mock.instances[0].download).toBe('Challenge-deadline-Dragon-Slayer.ics');
      const blob = URL.createObjectURL.mock.calls[0][0];
      const content = await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsText(blob);
      });
      expect(content).toContain('SUMMARY:Challenge deadline: Dragon Slayer');
      expect(content).toContain('DTSTART:20260905T060000Z');
      expect(content).toContain('DTEND:20260905T063000Z');
      expect(content).not.toContain('Private challenge details');
    } finally {
      click.mockRestore();
      timeout.mockRestore();
      vi.unstubAllGlobals();
    }
  });
});
