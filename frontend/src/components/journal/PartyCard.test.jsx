import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PartyCard from './PartyCard.jsx';

describe('PartyCard', () => {
  it('renders the empty state when pet is null', () => {
    render(<PartyCard pet={null} />);
    expect(screen.getByText(/no party member/i)).toBeInTheDocument();
  });

  it('renders pet with fallback dragon emoji when no art_url', () => {
    render(<PartyCard pet={{ species_name: 'Drake', growth_points: 50 }} />);
    expect(screen.getByText('Drake')).toBeInTheDocument();
    expect(screen.getByText('GROWTH')).toBeInTheDocument();
    expect(screen.getByText('50/100')).toBeInTheDocument();
  });

  it('renders art_url image when provided', () => {
    render(<PartyCard pet={{ species_name: 'X', art_url: '/pet.png', growth_points: 10 }} />);
    expect(screen.getByAltText('X')).toBeInTheDocument();
  });

  it('renders potion variant rune badge', () => {
    render(<PartyCard pet={{ species_name: 'X', potion_variant: 'Ember', growth_points: 10 }} />);
    expect(screen.getByText('Ember')).toBeInTheDocument();
  });

  it('shows mount info in full variant', () => {
    render(
      <PartyCard
        variant="full"
        pet={{ species_name: 'X', growth_points: 10 }}
        mount={{ species_name: 'Griffon' }}
      />,
    );
    expect(screen.getByText(/riding: griffon/i)).toBeInTheDocument();
  });

  it('hides mount info in compact variant', () => {
    render(
      <PartyCard
        variant="compact"
        pet={{ species_name: 'X', growth_points: 10 }}
        mount={{ species_name: 'Griffon' }}
      />,
    );
    expect(screen.queryByText(/riding/i)).toBeNull();
  });

  it('feeds via onFeed in full variant', async () => {
    const onFeed = vi.fn();
    const user = userEvent.setup();
    render(
      <PartyCard
        variant="full"
        pet={{ species_name: 'X', growth_points: 10 }}
        onFeed={onFeed}
      />,
    );
    await user.click(screen.getByRole('button', { name: /feed/i }));
    expect(onFeed).toHaveBeenCalled();
  });

  it('hides Feed button in compact variant', () => {
    render(
      <PartyCard
        pet={{ species_name: 'X', growth_points: 10 }}
        onFeed={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /feed/i })).toBeNull();
  });

  it('clamps growth_points to 0..100', () => {
    render(<PartyCard pet={{ species_name: 'X', growth_points: 150 }} />);
    expect(screen.getByText('100/100')).toBeInTheDocument();
  });

  it('treats missing growth_points as 0', () => {
    render(<PartyCard pet={{ species_name: 'X' }} />);
    expect(screen.getByText('0/100')).toBeInTheDocument();
  });

  it('falls back to Companion when species_name missing', () => {
    render(<PartyCard pet={{}} />);
    expect(screen.getByText('Companion')).toBeInTheDocument();
  });
});
