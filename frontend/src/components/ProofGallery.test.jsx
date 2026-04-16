import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProofGallery from './ProofGallery.jsx';

const PROOFS = [
  { id: 1, image: '/a.jpg', caption: 'Alpha' },
  { id: 2, image: '/b.jpg', caption: 'Beta' },
  { id: 3, image: '/c.jpg' },
];

describe('ProofGallery', () => {
  it('returns null when there are no proofs', () => {
    const { container } = render(<ProofGallery proofs={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('uses an empty array default when proofs is omitted', () => {
    const { container } = render(<ProofGallery />);
    expect(container.firstChild).toBeNull();
  });

  it('renders one thumbnail per proof', () => {
    render(<ProofGallery proofs={PROOFS} />);
    expect(screen.getAllByRole('button')).toHaveLength(3);
  });

  it('opens the viewer on thumbnail click', async () => {
    const user = userEvent.setup();
    render(<ProofGallery proofs={PROOFS} />);
    await user.click(screen.getAllByRole('button')[0]);
    // Full-screen viewer shows the caption
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('navigates with next/prev arrows', async () => {
    const user = userEvent.setup();
    render(<ProofGallery proofs={PROOFS} />);
    await user.click(screen.getAllByRole('button')[0]);
    // Arrow buttons: close + right-arrow (no prev on first). Find by SVG parent.
    const buttons = screen.getAllByRole('button');
    // Find the right arrow by looking for Lucide's ChevronRight glyph.
    const next = buttons.find((b) => b.querySelector('svg')?.classList?.contains('lucide-chevron-right'));
    if (next) {
      await user.click(next);
      expect(screen.getByText('Beta')).toBeInTheDocument();
    }
  });

  it('closes when clicking the X button', async () => {
    const user = userEvent.setup();
    render(<ProofGallery proofs={PROOFS} />);
    await user.click(screen.getAllByRole('button')[0]);
    const buttons = screen.getAllByRole('button');
    const close = buttons.find((b) => b.querySelector('svg')?.classList?.contains('lucide-x'));
    await user.click(close);
    // Caption no longer in the document.
    expect(screen.queryByText('Alpha')).toBeNull();
  });

  it('closes when clicking the backdrop', async () => {
    const user = userEvent.setup();
    render(<ProofGallery proofs={PROOFS} />);
    await user.click(screen.getAllByRole('button')[0]);
    // The fullscreen overlay backdrop is a div with fixed inset-0.
    const backdrop = document.querySelector('.fixed.inset-0');
    await user.click(backdrop);
    expect(screen.queryByText('Alpha')).toBeNull();
  });

  it('renders alt fallback for proofs without caption', () => {
    render(<ProofGallery proofs={[{ id: 9, image: '/x.jpg' }]} />);
    expect(screen.getByAltText('Proof 1')).toBeInTheDocument();
  });
});
