import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TabButton from './TabButton.jsx';

describe('TabButton', () => {
  it('renders its children', () => {
    render(<TabButton>Label</TabButton>);
    expect(screen.getByText('Label')).toBeInTheDocument();
  });

  it('fires onClick when clicked', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<TabButton onClick={onClick}>Click</TabButton>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });

  it('applies active styles when active', () => {
    const { container } = render(<TabButton active>Active</TabButton>);
    expect(container.firstChild.className).toContain('border-sheikah-teal-deep');
  });

  it('applies idle styles when not active', () => {
    const { container } = render(<TabButton>Idle</TabButton>);
    expect(container.firstChild.className).toContain('text-ink-secondary');
  });

  it('accepts a custom className', () => {
    const { container } = render(
      <TabButton className="extra">x</TabButton>,
    );
    expect(container.firstChild.className).toContain('extra');
  });
});
