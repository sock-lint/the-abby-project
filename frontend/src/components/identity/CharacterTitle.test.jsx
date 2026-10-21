import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import CharacterTitle from './CharacterTitle';

vi.mock('../rpg/CatalogIcon', () => ({
  default: ({ assetId, icon }) => <span data-title-icon={assetId}>{icon}</span>,
}));

describe('CharacterTitle', () => {
  it('uses the title’s own name and icon instead of a shared crown', () => {
    render(<CharacterTitle title={{ name: 'Chore Hero', icon: '🧹', catalog_icon: 'item-title-chore-hero' }} />);
    expect(screen.getByText('Chore Hero')).toBeInTheDocument();
    expect(screen.getByText('🧹')).toHaveAttribute('data-title-icon', 'item-title-chore-hero');
    expect(screen.queryByText('👑')).not.toBeInTheDocument();
  });

  it('honors authored title text and allows long names to wrap', () => {
    const { container } = render(<CharacterTitle title={{ name: 'Catalog name', metadata: { text: 'Maker of wonderfully elaborate things' } }} />);
    expect(screen.getByText('Maker of wonderfully elaborate things')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('character-title');
  });

  it('omits missing titles and missing artwork without inventing an icon', () => {
    const { container, rerender } = render(<CharacterTitle />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CharacterTitle title={{ name: 'Scholar' }} />);
    expect(screen.getByText('Scholar')).toBeInTheDocument();
    expect(container.querySelector('[data-title-icon]')).toBeNull();
  });
});
