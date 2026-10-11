import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import MeadowVisitCard from './MeadowVisitCard';

describe('Meadow visit card', () => {
  it('launches Play directly without requiring a router or auth provider', () => {
    render(<MeadowVisitCard />);
    const link = screen.getByRole('link', { name: 'Visit Play, the interactive meadow' });
    expect(link).toHaveAttribute('href', '/play/');
    expect(link.href).toBe(new URL('/play/', window.location.href).href);
    expect(link).not.toHaveAttribute('data-discover');
    expect(screen.getByText('Explore the meadow, meet companions, and enjoy your rewards.')).toBeInTheDocument();
    expect(screen.getByText('A little world to explore')).toBeInTheDocument();
    // The staged portrait is world artwork, not proof of an owned pet.
    expect(link.querySelector('img')).toHaveAttribute('alt', '');
  });
});
