import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import FamilyTrialsFolio from './FamilyTrialsFolio';

function buildRow(overrides = {}) {
  return {
    child_id: 1,
    child_name: 'Abby',
    quest: {
      id: 9,
      definition: { name: 'Dragon Slayer' },
      current_progress: 25,
      effective_target: 100,
      progress_percent: 25,
      end_date: '2026-09-04T23:00:00-07:00',
    },
    ...overrides,
  };
}

describe('FamilyTrialsFolio calendar export', () => {
  it('exports the family challenge deadline without copying the child name', async () => {
    const { user } = renderWithProviders(<FamilyTrialsFolio rows={[buildRow()]} />);
    await user.click(screen.getByRole('button', { name: 'Add Challenge deadline: Dragon Slayer to calendar' }));
    const google = screen.getByRole('link', { name: 'Google Calendar' });
    const event = new URL(google.href).searchParams;
    expect(event.get('text')).toBe('Challenge deadline: Dragon Slayer');
    expect(event.get('dates')).toBe('20260905T060000Z/20260905T063000Z');
    expect(event.get('details')).toContain('/quests?tab=trials');
    expect(event.get('details')).not.toContain('Abby');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeInTheDocument();
    google.addEventListener('click', (e) => e.preventDefault());
    await user.click(google);
  });

  it('omits calendar export for a family challenge without a saved deadline', () => {
    const row = buildRow();
    row.quest.end_date = null;
    renderWithProviders(<FamilyTrialsFolio rows={[row]} />);
    expect(screen.queryByRole('button', { name: /add .* to calendar/i })).not.toBeInTheDocument();
  });
});
