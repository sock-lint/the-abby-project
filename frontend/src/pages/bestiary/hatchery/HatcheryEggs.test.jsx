import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery';
import { server } from '../../../test/server';
import { spyHandler } from '../../../test/spy';
import { selectDropdown } from '../../../test/selectDropdown';
import inventory from '../../../../../contracts/api/fixtures/inventory-roster-hatching.json';

vi.mock('../../../pedestal/PedestalPreview', () => ({ default: () => <div /> }));

const egg = inventory.find(({ item }) => item.slug === 'meshtint-bat-egg');
const potion = inventory.find(({ item }) => item.slug === 'base-potion');
const savedEgg = inventory.find(({ item }) => item.slug === 'cat-egg');

function setup(rows, stable = { pets: [], mounts: [] }, props = {}) {
  server.use(
    http.get('*/api/pets/stable/', () => HttpResponse.json(stable)),
    http.get('*/api/inventory/', () => HttpResponse.json(rows)),
  );
  return render(<MemoryRouter><Hatchery {...props} /></MemoryRouter>);
}

describe('Hatchery egg collection', () => {
  it('lets a child inspect owned eggs and every growth stage without a potion', async () => {
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
    server.use(hatch.handler);
    setup([egg]);
    const user = userEvent.setup();
    const collection = await screen.findByRole('region', { name: 'Your eggs' });
    expect(within(collection).getByText('×2')).toBeInTheDocument();
    expect(within(collection).getByText('Needs a potion')).toBeInTheDocument();
    await user.click(within(collection).getByRole('button', { name: 'Select Bat Egg' }));
    expect(screen.getByRole('heading', { name: 'Bat family' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Pet growth stages' })).toHaveTextContent('Middle');
    expect(screen.getByRole('button', { name: 'Hatch pet' })).toBeDisabled();
    expect(hatch.calls).toHaveLength(0);
  });

  it('retains earlier eggs visibly without offering an unavailable hatch action', async () => {
    setup([egg, potion, savedEgg]);
    const collection = await screen.findByRole('region', { name: 'Your eggs' });
    expect(within(collection).getByText('Cat Egg')).toBeInTheDocument();
    expect(within(collection).getByText('Saved egg · unavailable for new hatching')).toBeInTheDocument();
    expect(within(collection).queryByRole('button', { name: 'Select Cat Egg' })).toBeNull();
  });

  it.each(['pets', 'mounts'])('explains an already owned pair in %s before consuming any ingredients', async (kind) => {
    const stable = { pets: [], mounts: [] };
    stable[kind] = [{ id: 7, species: { slug: 'meshtint-bat', name: 'Bat' }, potion: { slug: 'base' }, evolved_to_mount: true }];
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
    server.use(hatch.handler);
    setup([egg, potion], stable);
    const user = userEvent.setup();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.item.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(potion.item.id));
    expect(screen.getByText('You already have this companion. Extra eggs stay in your inventory.')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Hatch pet' });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(hatch.calls).toHaveLength(0);
    expect(screen.getByRole('link', { name: 'Care for companions' })).toHaveAttribute('href', '/bestiary?tab=companions');
  });

  it('prevents repeated hatches and ignores a receipt after the account credential changes', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, async () => {
      await pending;
      return { id: 9, species: { name: 'Bat' }, potion: { name: 'Base' } };
    });
    server.use(hatch.handler);
    const onChanged = vi.fn();
    setup([egg, potion], undefined, { onChanged });
    const user = userEvent.setup();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.item.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(potion.item.id));
    await user.dblClick(screen.getByRole('button', { name: 'Hatch pet' }));
    await waitFor(() => expect(hatch.calls).toHaveLength(1));
    expect(hatch.calls[0].body).toEqual({ egg_item_id: String(egg.item.id), potion_item_id: String(potion.item.id) });
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/hatch\/$/);
    expect(screen.getByRole('button', { name: 'Hatching…' })).toBeDisabled();
    localStorage.setItem('abby_auth_token', 'another-synthetic-session');
    await act(async () => { release(); await pending; });
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText(/You hatched a/)).toBeNull();
  });
});
