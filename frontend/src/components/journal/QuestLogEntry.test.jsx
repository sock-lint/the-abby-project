import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QuestLogEntry from './QuestLogEntry.jsx';

describe('QuestLogEntry', () => {
  it('renders title', () => {
    render(<QuestLogEntry title="Do dishes" />);
    expect(screen.getByText('Do dishes')).toBeInTheDocument();
  });

  it('renders meta and reward', () => {
    render(<QuestLogEntry title="t" meta="meta" reward="$1" />);
    expect(screen.getByText('meta')).toBeInTheDocument();
    expect(screen.getByText('$1')).toBeInTheDocument();
  });

  it('renders a kind RuneBadge when kind is set', () => {
    render(<QuestLogEntry title="t" kind="Venture" tone="royal" />);
    expect(screen.getByText('Venture')).toBeInTheDocument();
  });

  it('renders leading icon', () => {
    render(<QuestLogEntry title="t" icon={<svg data-testid="icn" />} />);
    expect(screen.getByTestId('icn')).toBeInTheDocument();
  });

  it('fires onAction when the check button is clicked', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    render(<QuestLogEntry title="t" onAction={onAction} />);
    await user.click(screen.getByRole('button'));
    expect(onAction).toHaveBeenCalled();
  });

  it('does not fire onAction when status=locked', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    render(<QuestLogEntry title="t" status="locked" onAction={onAction} />);
    await user.click(screen.getByRole('button'));
    expect(onAction).not.toHaveBeenCalled();
  });

  it('renders check glyph when done', () => {
    const { container } = render(<QuestLogEntry title="t" status="done" />);
    expect(container.querySelector('.line-through')).toBeTruthy();
  });

  it('applies overdue styles', () => {
    const { container } = render(<QuestLogEntry title="t" status="overdue" />);
    expect(container.firstChild.className).toContain('bg-ember/10');
  });

  it('uses actionLabel as aria-label when provided', () => {
    render(<QuestLogEntry title="t" actionLabel="Start quest" />);
    expect(screen.getByRole('button', { name: /start quest/i })).toBeInTheDocument();
  });
});
