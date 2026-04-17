import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import PrereqChain from './PrereqChain';

const prereqs = [
  { skill_id: 10, skill_name: 'Reading Plans', required_level: 2, met: true },
  { skill_id: 11, skill_name: 'Tape Measure', required_level: 3, met: false },
];

describe('PrereqChain', () => {
  it('renders one link per prerequisite', () => {
    const { container } = renderWithProviders(<PrereqChain prerequisites={prereqs} />);
    expect(container.querySelectorAll('[data-prereq-link="true"]').length).toBe(2);
  });

  it('exposes met vs unmet state', () => {
    const { container } = renderWithProviders(<PrereqChain prerequisites={prereqs} />);
    const links = container.querySelectorAll('[data-prereq-link="true"]');
    expect(links[0]).toHaveAttribute('data-met', 'true');
    expect(links[1]).toHaveAttribute('data-met', 'false');
  });

  it('uses the prereq label as the accessible title', () => {
    renderWithProviders(<PrereqChain prerequisites={prereqs} />);
    expect(screen.getByLabelText(/Reading Plans · Level 2 · met/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tape Measure · Level 3 · not yet met/i)).toBeInTheDocument();
  });

  it('renders nothing when prerequisites is empty or nullish', () => {
    const { container, rerender } = renderWithProviders(<PrereqChain prerequisites={[]} />);
    expect(container.firstChild).toBeNull();
    rerender(<PrereqChain prerequisites={null} />);
    expect(container.firstChild).toBeNull();
  });
});
