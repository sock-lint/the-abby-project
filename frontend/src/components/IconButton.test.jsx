import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IconButton from './IconButton.jsx';

describe('IconButton', () => {
  let warnSpy;
  beforeEach(() => { warnSpy = vi.spyOn(console, 'error').mockImplementation(() => {}); });
  afterEach(() => { warnSpy.mockRestore(); });

  it('renders the icon child inside a labeled button', () => {
    render(
      <IconButton aria-label="Close">
        <span data-testid="x-icon">x</span>
      </IconButton>,
    );
    const btn = screen.getByRole('button', { name: 'Close' });
    expect(btn).toContainElement(screen.getByTestId('x-icon'));
  });

  it('warns in dev when aria-label is missing', () => {
    render(<IconButton><span>x</span></IconButton>);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('IconButton requires aria-label'),
    );
  });

  it('uses a square padding sized for tap targets', () => {
    render(<IconButton aria-label="Close"><span>x</span></IconButton>);
    expect(screen.getByRole('button').className).toMatch(/p-2/);
  });

  it('forwards onClick', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton aria-label="x" onClick={onClick}><span>i</span></IconButton>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('supports the same variants as Button', () => {
    render(<IconButton aria-label="x" variant="danger"><span>i</span></IconButton>);
    expect(screen.getByRole('button').className).toContain('ember');
  });

  it('defaults to ghost variant', () => {
    render(<IconButton aria-label="x"><span>i</span></IconButton>);
    expect(screen.getByRole('button').className).toContain('ink-secondary');
  });
});
