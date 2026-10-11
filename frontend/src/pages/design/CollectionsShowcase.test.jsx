import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen, within } from '../../test/render';
import CollectionsShowcase from './CollectionsShowcase';

describe('Collection navigation design showcase', () => {
  it('shows explicit earned counts and the selected badge collection', async () => {
    const { user } = renderWithProviders(<CollectionsShowcase />, { withAuth: false });
    const tabs = within(screen.getByRole('tablist', { name: 'Demo badge collections' }));
    const selected = tabs.getByRole('tab', { name: 'Making & learning, 1 of 4 badges earned' });
    await user.click(selected);
    expect(selected).toHaveAttribute('aria-selected', 'true');
    const contents = within(screen.getByRole('region', { name: 'Making & learning' }));
    expect(contents.getByText('First creation')).toBeInTheDocument();
    expect(contents.getAllByText('Earned')).toHaveLength(1);
    expect(contents.getAllByText('Not yet earned')).toHaveLength(3);
    expect(screen.queryByText('First adventure')).not.toBeInTheDocument();
  });

  it('opens a Lorebook topic with a long name and its available entries', async () => {
    const { user } = renderWithProviders(<CollectionsShowcase />, { withAuth: false });
    const tabs = within(screen.getByRole('tablist', { name: 'Demo Lorebook topics' }));
    const selected = tabs.getByRole('tab', { name: 'Skills, experience & growing at your own pace, 2 entries' });
    await user.click(selected);
    expect(selected).toHaveAttribute('aria-selected', 'true');
    const contents = within(screen.getByRole('region', { name: 'Skills, experience & growing at your own pace' }));
    expect(contents.getByText('How skill experience works')).toBeInTheDocument();
    expect(contents.getByText('Following a prerequisite path')).toBeInTheDocument();
    expect(screen.queryByText('Your first visit')).not.toBeInTheDocument();
  });

  it('filters the sample inventory and restores all treasures', async () => {
    const { user } = renderWithProviders(<CollectionsShowcase />, { withAuth: false });
    const tabs = within(screen.getByRole('tablist', { name: 'Demo Satchel filters' }));
    const potions = tabs.getByRole('tab', { name: 'Potions, 42 items' });
    await user.click(potions);
    expect(potions).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('region', { name: 'Potions' })).toHaveTextContent('Mint potion');
    expect(screen.queryByText('Meadow egg')).not.toBeInTheDocument();
    await user.click(tabs.getByRole('tab', { name: 'All treasures, 68 items' }));
    const contents = within(screen.getByRole('region', { name: 'All treasures' }));
    expect(contents.getByText('Meadow egg')).toBeInTheDocument();
    expect(contents.getByText('Flower portrait frame')).toBeInTheDocument();
    expect(contents.getAllByRole('listitem')).toHaveLength(6);
  });
});
