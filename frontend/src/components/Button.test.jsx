import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Button from './Button.jsx';

describe('Button', () => {
  it('blocks repeated clicks while loading even when the caller passes disabled=false', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button loading disabled={false} onClick={onClick}>Save</Button>);
    await user.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole('button')).toBeDisabled();
    rerender(<Button loading={false} disabled={false} onClick={onClick}>Save</Button>);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders children inside a <button>', () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole('button', { name: 'Click me' });
    expect(btn.tagName).toBe('BUTTON');
  });

  it('defaults to variant=primary, type=button', () => {
    render(<Button>x</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('type', 'button');
    expect(btn.className).toContain('sheikah-teal-deep');
  });

  it('applies the requested variant', () => {
    const { rerender } = render(<Button variant="danger">x</Button>);
    expect(screen.getByRole('button').className).toContain('ember');
    rerender(<Button variant="success">x</Button>);
    expect(screen.getByRole('button').className).toContain('moss');
    rerender(<Button variant="secondary">x</Button>);
    expect(screen.getByRole('button').className).toContain('ink-page-aged');
    rerender(<Button variant="ghost">x</Button>);
    expect(screen.getByRole('button').className).toContain('ink-secondary');
  });

  it('applies size padding', () => {
    const { rerender } = render(<Button size="sm">x</Button>);
    expect(screen.getByRole('button').className).toMatch(/px-3 py-1/);
    rerender(<Button size="lg">x</Button>);
    expect(screen.getByRole('button').className).toMatch(/px-5 py-3/);
  });

  it('forwards onClick', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>x</Button>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('respects type=submit when explicitly set', () => {
    render(<Button type="submit">x</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });

  it('passes through disabled', () => {
    render(<Button disabled>x</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('appends caller className without overriding variant classes', () => {
    render(<Button className="w-full mt-4">x</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('w-full');
    expect(btn.className).toContain('mt-4');
    expect(btn.className).toContain('sheikah-teal-deep');
  });
});
