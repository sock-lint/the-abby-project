import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import SectionHeader from './SectionHeader';

describe('SectionHeader', () => {
  it('renders title in a heading element', () => {
    render(<SectionHeader title="Treasury" />);
    expect(
      screen.getByRole('heading', { name: /treasury/i, level: 2 }),
    ).toBeInTheDocument();
  });

  it('supports a custom heading level via the `as` prop', () => {
    render(<SectionHeader as="h3" title="Hoard" />);
    expect(
      screen.getByRole('heading', { name: /hoard/i, level: 3 }),
    ).toBeInTheDocument();
  });

  it('renders a decorative numbered marker when index is supplied', () => {
    const { container } = render(<SectionHeader title="Hoard" index={2} />);
    expect(container.querySelector('[data-chapter-marker="3"]')).toHaveAttribute('aria-hidden', 'true');
  });

  it('omits the chapter marker when index is undefined', () => {
    const { container } = render(<SectionHeader title="Hoard" />);
    expect(container.querySelector('[data-chapter-marker]')).toBeNull();
  });

  it('renders kicker when supplied', () => {
    render(<SectionHeader title="Treasury" kicker="a quiet ledger" />);
    expect(screen.getByText(/a quiet ledger/i)).toBeInTheDocument();
  });

  it('renders count badge when supplied', () => {
    render(<SectionHeader title="Quests" count={7} />);
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('renders actions slot when supplied', () => {
    render(
      <SectionHeader
        title="Quests"
        actions={<button type="button">Add</button>}
      />,
    );
    expect(screen.getByRole('button', { name: /add/i })).toBeInTheDocument();
  });

  it('renders supporting body line from children', () => {
    render(
      <SectionHeader title="Quests">
        manage your active campaigns
      </SectionHeader>,
    );
    expect(screen.getByText(/manage your active campaigns/i)).toBeInTheDocument();
  });
});
