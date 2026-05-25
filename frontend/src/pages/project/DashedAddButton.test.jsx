import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DashedAddButton from './DashedAddButton';

describe('DashedAddButton', () => {
  it('renders its children as the button label and fires onClick', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<DashedAddButton onClick={onClick}>add milestone</DashedAddButton>);
    const btn = screen.getByRole('button', { name: /add milestone/i });
    await user.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('applies the small-size token classes when size="sm"', () => {
    render(<DashedAddButton size="sm" onClick={() => {}}>add step here</DashedAddButton>);
    const btn = screen.getByRole('button', { name: /add step here/i });
    expect(btn.className).toContain('text-caption');
    expect(btn.className).toContain('py-1.5');
  });

  it('falls back to medium-size token classes by default', () => {
    render(<DashedAddButton onClick={() => {}}>add resource</DashedAddButton>);
    const btn = screen.getByRole('button', { name: /add resource/i });
    expect(btn.className).toContain('text-body');
    expect(btn.className).toContain('py-2.5');
  });
});
