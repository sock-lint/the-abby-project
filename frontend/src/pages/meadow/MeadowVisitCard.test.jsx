import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import MeadowVisitCard from './MeadowVisitCard';

describe('Meadow visit card', () => {
  it('launches Play directly without requiring a router or auth provider', () => {
    render(<MeadowVisitCard />);
    const link = screen.getByRole('link', { name: 'Visit Play, your companion and rewards' });
    expect(link).toHaveAttribute('href', '/play/');
    expect(link.href).toBe(new URL('/play/', window.location.href).href);
    expect(link).not.toHaveAttribute('data-discover');
    expect(screen.getByText('Spend a moment with your companion and see what you’ve earned.')).toBeInTheDocument();
  });
});
