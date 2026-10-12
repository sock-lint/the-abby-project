import { describe, it, expect, vi } from 'vitest';
import { render, screen, userEvent } from '../../test/render';
import TomeSpine from './TomeSpine';
import { PROGRESS_TIER } from './mastery.constants';

describe('TomeSpine', () => {
  it('exposes the collection name and stable descriptor/state hooks', () => {
    render(<TomeSpine id="wood" name="Woodworking" icon="🪵" tier={PROGRESS_TIER.rising} />);
    const tab = screen.getByRole('tab', { name: 'Woodworking' });
    expect(tab).toHaveAttribute('data-spine-id', 'wood');
    expect(tab).toHaveAttribute('data-spine-variant', 'codex');
    expect(tab).toHaveAttribute('data-tier', 'rising');
    expect(tab).toHaveAttribute('data-active', 'false');
    expect(tab).toHaveAttribute('aria-selected', 'false');
    expect(tab).toHaveAttribute('tabindex', '-1');
  });

  it('preserves a domain-specific accessible label', () => {
    render(<TomeSpine id={7} name="Woodworking" chip="L4" ariaLabel="Woodworking, level 4, 1,200 XP" />);
    expect(screen.getByRole('tab', { name: 'Woodworking, level 4, 1,200 XP' })).toBeInTheDocument();
  });

  it.each(['codex', 'vessel'])('reserves the %s current marker without changing layout when selected', (variant) => {
    const { container, rerender } = render(<TomeSpine id={7} name="Woodworking" variant={variant} active={false} />);
    const marker = container.querySelector('[data-current-marker="true"]');
    expect(marker).toHaveClass('invisible');
    expect(marker).toHaveAttribute('aria-hidden', 'true');
    rerender(<TomeSpine id={7} name="Woodworking" variant={variant} active />);
    expect(container.querySelector('[data-current-marker="true"]')).toBe(marker);
    expect(marker).not.toHaveClass('invisible');
    expect(screen.getByRole('tab')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab')).toHaveAttribute('data-active', 'true');
    expect(screen.getByRole('tab')).toHaveAttribute('tabindex', '0');
  });

  it('calls the supplied click handler', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<TomeSpine id={7} name="Woodworking" onClick={onClick} />);
    await user.click(screen.getByRole('tab'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('shows supplied counts and measurable progress without changing them', () => {
    render(<TomeSpine id={7} name="Woodworking" chip="4/10" progressPct={42} tier={PROGRESS_TIER.rising} />);
    expect(screen.getByText('4/10')).toBeVisible();
    expect(screen.getByText('42%')).toBeVisible();
    expect(screen.getByRole('tab', { name: 'Woodworking, 4/10, 42% progress' })).toBeInTheDocument();
    const progress = screen.getByRole('progressbar', { name: 'Woodworking progress' });
    expect(progress).toHaveAttribute('aria-valuenow', '42');
    expect(progress).toHaveAttribute('aria-valuemin', '0');
    expect(progress).toHaveAttribute('aria-valuemax', '100');
    expect(progress).toHaveAttribute('data-progress', '42');
    expect(progress).toHaveAttribute('data-tier', 'rising');
    expect(progress.firstElementChild).toHaveStyle({ width: '42%' });
  });

  it('does not imply progress when only a count is supplied', () => {
    render(<TomeSpine id="eggs" name="Eggs" chip="×12" variant="vessel" />);
    expect(screen.getByRole('tab', { name: 'Eggs, ×12' })).toBeInTheDocument();
    expect(screen.getByText('×12')).toBeVisible();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('preserves a real zero count and zero progress', () => {
    render(<TomeSpine id="wood" name="Woodworking" chip={0} progressPct={0} />);
    expect(screen.getByText('0')).toBeVisible();
    expect(screen.getByText('0%')).toBeVisible();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });

  it.each([[140, 100], [-5, 0]])('clamps progress %s to its measurable range (%s)', (input, expected) => {
    render(<TomeSpine id="wood" name="Woodworking" progressPct={input} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', String(expected));
    expect(screen.getByText(`${expected}%`)).toBeVisible();
  });

  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY])('omits an absent or invalid progress value (%s)', (progressPct) => {
    render(<TomeSpine id="wood" name="Woodworking" progressPct={progressPct} />);
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('keeps long labels and counts readable in both card and pill layouts', () => {
    const name = 'A very long collection of mechanical engineering and imaginative storytelling';
    const { rerender } = render(<TomeSpine id="long" name={name} chip="12/128" active />);
    expect(screen.getByText(name)).toBeVisible();
    expect(screen.getByText('12/128')).toBeVisible();
    expect(screen.getByRole('tab', { name: `${name}, 12/128` })).toBeInTheDocument();
    rerender(<TomeSpine id="long" name={name} chip="12/128" variant="vessel" active />);
    expect(screen.getByText(name)).toBeVisible();
    expect(screen.getByText('12/128')).toBeVisible();
    expect(screen.getByRole('tab')).toHaveAttribute('data-spine-variant', 'vessel');
  });

  it.each(Object.entries(PROGRESS_TIER))('uses the shared %s tier for real progress', (key, tier) => {
    render(<TomeSpine id={key} name="Collection" progressPct={42} tier={tier} />);
    expect(screen.getByRole('tab')).toHaveAttribute('data-tier', key);
    expect(screen.getByRole('progressbar')).toHaveAttribute('data-tier', key);
  });

  it('uses locked tier for an unknown descriptor and accepts the shelf tab stop', () => {
    render(<TomeSpine id="unknown" name="Collection" tier={{}} tabIndex={0} />);
    expect(screen.getByRole('tab')).toHaveAttribute('data-tier', 'locked');
    expect(screen.getByRole('tab')).toHaveAttribute('tabindex', '0');
  });
});
