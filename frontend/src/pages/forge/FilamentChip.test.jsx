import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import FilamentChip from './FilamentChip';
import { describeFilament } from './forge.constants';

const PLA = {
  slot: 'A1',
  material: 'PLA',
  label: 'PLA Basic',
  display_name: 'PLA Basic',
  hex: '#00AE42',
  remain_percent: 92,
  is_external: false,
};

const THIRD_PARTY = {
  ...PLA, slot: 'A2', label: '', display_name: 'PETG', material: 'PETG',
  hex: '#1E90FF', remain_percent: null,
};

const UNREAD = {
  ...PLA, slot: 'A3', display_name: 'PLA', hex: null, remain_percent: null,
};

describe('describeFilament', () => {
  it('names the slot, the filament and what is left', () => {
    expect(describeFilament(PLA)).toBe('A1 · PLA Basic · 92% left');
  });

  it('omits the percentage the AMS never reported', () => {
    // A third-party spool has no RFID tag, so there is no number to give.
    // "0% left" on a full roll would be worse than saying nothing.
    expect(describeFilament(THIRD_PARTY)).toBe('A2 · PETG');
  });
});

describe('FilamentChip', () => {
  it('paints the swatch with the reported colour', () => {
    const { container } = renderWithProviders(<FilamentChip filament={PLA} />);
    const swatch = container.querySelector('[data-swatch="known"]');
    expect(swatch).toHaveStyle({ backgroundColor: '#00AE42' });
    expect(screen.getByText('PLA Basic')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('marks an unread bay as unknown rather than painting it black', () => {
    // #000000 is real black filament. An unread tag must not look like one.
    const { container } = renderWithProviders(<FilamentChip filament={UNREAD} />);
    expect(container.querySelector('[data-swatch="unknown"]')).toBeInTheDocument();
    expect(container.querySelector('[data-swatch="known"]')).toBeNull();
  });

  it('shows no percentage for a spool that reports none', () => {
    renderWithProviders(<FilamentChip filament={THIRD_PARTY} />);
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('is inert with no onSelect, and a button with one', async () => {
    const { rerender } = renderWithProviders(<FilamentChip filament={PLA} />);
    expect(screen.queryByRole('button')).toBeNull();

    const onSelect = vi.fn();
    rerender(<FilamentChip filament={PLA} onSelect={onSelect} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /A1 · PLA Basic/ }));
    expect(onSelect).toHaveBeenCalledWith(PLA);
  });

  it('reports its selected state to assistive tech', () => {
    renderWithProviders(
      <FilamentChip filament={PLA} selected onSelect={() => {}} />,
    );
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
  });
});
