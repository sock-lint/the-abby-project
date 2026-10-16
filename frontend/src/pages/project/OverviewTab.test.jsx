import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OverviewTab from './OverviewTab.jsx';
import { buildProject } from '../../test/factories.js';

describe('OverviewTab', () => {
  it('shows school planning information without project payouts or XP rewards', () => {
    render(<OverviewTab project={buildProject({
      is_homework_plan: true, payment_kind: 'bounty', bonus_amount: '13.00',
      hourly_rate_override: '8.50', xp_reward: 99, description: 'Research the solar system.',
    })} />);
    expect(screen.getByText('Research the solar system.')).toBeInTheDocument();
    expect(screen.queryByText(/cash reward|^bonus$|xp reward|rate override/i)).not.toBeInTheDocument();
    expect(screen.queryByText('$13.00')).not.toBeInTheDocument();
  });

  it('exports the project due date without keeper notes or project description', async () => {
    const user = userEvent.setup();
    render(<OverviewTab project={buildProject({
      id: 12, due_date: '2026-09-03', parent_notes: 'Private keeper note',
      description: 'Private project details',
    })} isParent />);
    await user.click(screen.getByRole('button', { name: 'Add Project due: Build a Bird Feeder to calendar' }));
    const google = screen.getByRole('link', { name: 'Google Calendar' });
    const event = new URL(google.href).searchParams;
    expect(event.get('text')).toBe('Project due: Build a Bird Feeder');
    expect(event.get('dates')).toBe('20260903/20260904');
    expect(event.get('details')).toContain('/quests/ventures/12');
    expect(event.get('details')).not.toMatch(/Private keeper note|Private project details/);
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeInTheDocument();
    google.addEventListener('click', (e) => e.preventDefault());
    await user.click(google);
  });

  it('omits calendar export when the project has no due date', () => {
    render(<OverviewTab project={buildProject({ due_date: null })} />);
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add .* to calendar/i })).not.toBeInTheDocument();
  });

  it('renders description and Instructables link', () => {
    render(
      <OverviewTab
        project={buildProject({ description: 'Do cool thing', instructables_url: 'https://x' })}
        isParent={false}
      />,
    );
    expect(screen.getByText('Do cool thing')).toBeInTheDocument();
    expect(screen.getByText(/view on instructables/i)).toBeInTheDocument();
  });

  it('omits optional sections when absent', () => {
    render(<OverviewTab project={buildProject({ description: '', instructables_url: null })} />);
    expect(screen.queryByText(/view on instructables/i)).toBeNull();
  });
});
