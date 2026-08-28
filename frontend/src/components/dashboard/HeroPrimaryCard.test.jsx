import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import HeroPrimaryCard from './HeroPrimaryCard';
import { renderWithProviders } from '../../test/render';

describe('HeroPrimaryCard — next-action variant', () => {
  it('renders homework next-action with subtitle and icon', () => {
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday',
          dateStr: 'April 16',
          nextAction: {
            kind: 'homework', id: 42, title: 'Math workbook',
            subtitle: 'Math · due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
        }}
      />,
    );
    expect(screen.getByText('Math workbook')).toBeInTheDocument();
    expect(screen.getByText(/due tomorrow/i)).toBeInTheDocument();
  });

  it('calls onOpenHomework when homework "Submit" clicked', async () => {
    const onOpenHomework = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'homework', id: 42, title: 'Math workbook',
            subtitle: 'Math · due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
          onOpenHomework,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /submit/i }));
    expect(onOpenHomework).toHaveBeenCalledWith(42);
  });

  it('calls onCompleteChore when chore "Complete" clicked', async () => {
    const onCompleteChore = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'chore', id: 7, title: 'Clean Room',
            subtitle: 'duty · $1.00', score: 34,
            icon: 'Sparkles', tone: 'moss', action_url: '/chores',
            due_at: null, reward: { money: '1.00', coins: 2 },
          },
          onCompleteChore,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /complete/i }));
    expect(onCompleteChore).toHaveBeenCalledWith(7);
  });

  it('calls onTapHabit when habit "Tap" clicked', async () => {
    const onTapHabit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'habit', id: 9, title: 'Brush teeth',
            subtitle: 'keep your 5-day streak', score: 65,
            icon: 'Flame', tone: 'ember', action_url: '/habits',
            due_at: null, reward: null,
          },
          onTapHabit,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /tap/i }));
    expect(onTapHabit).toHaveBeenCalledWith(9);
  });

  it('falls back to idle variant when no nextAction and nothing else', () => {
    renderWithProviders(
      <HeroPrimaryCard role="child" ctx={{ weekday: 'T', dateStr: 'Apr 16' }} />,
    );
    expect(screen.getByText(/pick something/i)).toBeInTheDocument();
  });

  it('renders an IlluminatedVersal of the next-action title first letter', () => {
    const { container } = renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'homework', id: 42, title: 'Math workbook',
            subtitle: 'Math · due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
        }}
      />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    expect(versal.textContent).toContain('M');
  });

  it('quest-progress CTA calls the active quest a trial, matching its kicker', () => {
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'T', dateStr: 'Apr 16',
          activeQuest: {
            status: 'active', current_progress: 3, effective_target: 10,
            progress_percent: 30, definition: { name: 'Dragon Slayer' },
          },
        }}
      />,
    );
    expect(screen.getByText(/active trial/i)).toBeInTheDocument();
    // "View quest →" sent a kid looking for the Quests hub; the link lands on
    // the Trials tab, so the label has to say trial.
    expect(screen.getByRole('button', { name: /view trial/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /view quest/i })).toBeNull();
  });

  it('parent hero holds off the all-clear while the queue is still loading', () => {
    renderWithProviders(
      <HeroPrimaryCard role="parent" ctx={{ pendingCount: 0, loading: true }} />,
    );
    expect(screen.queryByText(/nothing needs your seal/i)).toBeNull();
    expect(screen.getByText(/turning today's page/i)).toBeInTheDocument();
  });

  it('parent hero shows the all-clear once the queue has resolved empty', () => {
    renderWithProviders(
      <HeroPrimaryCard role="parent" ctx={{ pendingCount: 0, loading: false }} />,
    );
    expect(screen.getByText(/nothing needs your seal/i)).toBeInTheDocument();
  });

  it('clocked variant still wins over nextAction', () => {
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'T', dateStr: 'Apr 16',
          activeTimer: { project_title: 'Birdhouse', elapsed_minutes: 42 },
          nextAction: {
            kind: 'homework', id: 42, title: 'Math',
            subtitle: 'due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
        }}
      />,
    );
    expect(screen.getByText('Birdhouse')).toBeInTheDocument();
    expect(screen.queryByText('Math')).not.toBeInTheDocument();
  });
});
