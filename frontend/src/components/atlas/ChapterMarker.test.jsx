import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChapterMarker from './ChapterMarker';

describe('ChapterMarker', () => {
  it('keeps decorative numbering out of the adjacent heading name', () => {
    render(<h2><ChapterMarker index={0} />Treasury</h2>);
    expect(screen.getByRole('heading', { name: 'Treasury' })).toBeInTheDocument();
    expect(screen.getByText('1')).toHaveAttribute('aria-hidden', 'true');
  });

  it('supports labels from a chapter taxonomy and larger chapter indices', () => {
    const { rerender } = render(<ChapterMarker>7</ChapterMarker>);
    expect(screen.getByText('7')).toHaveAttribute('data-chapter-marker', '7');
    rerender(<ChapterMarker index={20} />);
    expect(screen.getByText('21')).toBeInTheDocument();
  });

  it('renders nothing without a chapter label', () => {
    const { container } = render(<ChapterMarker />);
    expect(container).toBeEmptyDOMElement();
  });
});
