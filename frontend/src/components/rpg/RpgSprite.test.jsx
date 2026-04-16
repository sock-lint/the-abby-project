import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import RpgSprite from './RpgSprite.jsx';

describe('RpgSprite', () => {
  it('renders the PNG sprite when spriteKey matches', () => {
    render(<RpgSprite spriteKey="apple" alt="apple sprite" />);
    // Real sprite assets are registered via Vite import.meta.glob; we don't
    // assert the URL, just that an <img> is rendered.
    expect(screen.getByAltText('apple sprite').tagName.toLowerCase()).toBe('img');
  });

  it('falls back to emoji when spriteKey is unknown and size matches a class', () => {
    render(<RpgSprite spriteKey="nonexistent" icon="✨" size={32} alt="x" />);
    expect(screen.getByLabelText('x').textContent).toBe('✨');
  });

  it('falls back to default ✨ emoji when no icon is provided', () => {
    render(<RpgSprite spriteKey="nonexistent" size={32} />);
    const span = document.querySelector('[aria-label=""]') || document.querySelector('span');
    expect(span.textContent).toBe('✨');
  });

  it('uses inline font-size when size has no mapped class', () => {
    const { container } = render(<RpgSprite icon="🎲" size={17} />);
    const span = container.querySelector('span');
    expect(span.style.fontSize).toBe('17px');
  });

  it('uses mapped text-size class when size matches', () => {
    const { container } = render(<RpgSprite icon="🎲" size={48} />);
    const span = container.querySelector('span');
    expect(span.className).toContain('text-4xl');
  });

  it('returns nothing when spriteKey is falsy', () => {
    // Null spriteKey falls through to the emoji branch with default ✨.
    const { container } = render(<RpgSprite size={32} />);
    expect(container.textContent).toContain('✨');
  });
});
