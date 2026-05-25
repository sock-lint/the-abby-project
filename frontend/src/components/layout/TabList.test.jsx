import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TabList from './TabList';

const tabs = [
  { id: 'a', label: 'Alpha' },
  { id: 'b', label: 'Beta' },
  { id: 'c', label: 'Gamma' },
];

describe('TabList', () => {
  it('exposes a tablist with the supplied ariaLabel', () => {
    render(
      <TabList tabs={tabs} activeId="a" onSelect={() => {}} ariaLabel="Hub sections" />,
    );
    expect(screen.getByRole('tablist', { name: /Hub sections/i })).toBeInTheDocument();
  });

  it('renders one tab per descriptor with the active one marked', () => {
    render(
      <TabList tabs={tabs} activeId="b" onSelect={() => {}} ariaLabel="Hub" />,
    );
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false');
  });

  it('calls onSelect with the descriptor id when a tab is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<TabList tabs={tabs} activeId="a" onSelect={spy} ariaLabel="Hub" />);
    await user.click(screen.getByRole('tab', { name: 'Gamma' }));
    expect(spy).toHaveBeenCalledWith('c');
  });

  it('applies the pill variant by default for pill variant', () => {
    render(
      <TabList
        tabs={tabs}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        ariaLabel="Hub"
      />,
    );
    const active = screen.getByRole('tab', { name: 'Alpha' });
    expect(active.className).toContain('bg-sheikah-teal-deep');
  });

  it('applies the bookmark variant with the teal indicator on the active tab', () => {
    const { container } = render(
      <TabList
        tabs={tabs}
        activeId="b"
        onSelect={() => {}}
        variant="bookmark"
        ariaLabel="Hub"
      />,
    );
    // Active bookmark tab carries the bottom-aligned teal pip span.
    const pip = container.querySelector('span.bg-sheikah-teal-deep');
    expect(pip).not.toBeNull();
  });

  it('renders icons in pill variant when descriptor includes one', () => {
    const Icon = ({ size }) => <svg data-testid="tab-icon" data-size={size} />;
    render(
      <TabList
        tabs={[{ id: 'a', label: 'Alpha', icon: Icon }]}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        ariaLabel="Hub"
      />,
    );
    expect(screen.getByTestId('tab-icon')).toBeInTheDocument();
  });

  it('stretch makes pill tabs grow to fill the strip width', () => {
    render(
      <TabList
        tabs={tabs}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        stretch
        ariaLabel="Hub"
      />,
    );
    expect(screen.getByRole('tab', { name: 'Alpha' }).className).toContain('flex-1');
  });
});
