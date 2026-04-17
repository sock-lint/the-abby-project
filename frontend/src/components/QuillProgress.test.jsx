import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '../test/render';
import QuillProgress from './QuillProgress';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

describe('QuillProgress', () => {
  it('exposes a progressbar role with a default label', () => {
    renderWithProviders(<QuillProgress value={40} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '40');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).toHaveAttribute('aria-label');
  });

  it('clamps the value into [0, max]', () => {
    const { rerender } = renderWithProviders(<QuillProgress value={-20} max={50} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    rerender(<QuillProgress value={9001} max={50} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
  });

  it('accepts an aria-label override and reports the correct aria-valuemax', () => {
    renderWithProviders(
      <QuillProgress value={3} max={12} aria-label="Tape Measure XP progress to level 4" />,
    );
    const bar = screen.getByRole('progressbar', {
      name: 'Tape Measure XP progress to level 4',
    });
    expect(bar).toHaveAttribute('aria-valuemax', '12');
    expect(bar).toHaveAttribute('aria-valuenow', '3');
  });

  it('tags the fill with the requested tailwind color class', () => {
    const { container } = renderWithProviders(
      <QuillProgress value={60} color="bg-gold-leaf" />,
    );
    const fill = container.querySelector('[data-quill-fill="true"]');
    expect(fill).not.toBeNull();
    expect(fill.className).toContain('bg-gold-leaf');
  });

  it('renders the quill-texture overlay', () => {
    const { container } = renderWithProviders(<QuillProgress value={40} />);
    expect(container.querySelector('[data-quill-texture="true"]')).not.toBeNull();
  });

  it('renders max=0 safely at zero progress', () => {
    renderWithProviders(<QuillProgress value={3} max={0} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });
});
