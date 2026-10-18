import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery';
import { server } from '../../../test/server';
import { spyHandler } from '../../../test/spy';
import { selectDropdown } from '../../../test/selectDropdown';
import inventory from '../../../../../contracts/api/fixtures/inventory-roster-hatching.json';
import claimReceipt from '../../../../../contracts/api/fixtures/pet-incubation-roster-hatched.json';

vi.mock('../../../pedestal/PedestalPreview', () => ({ default: () => null }));
vi.mock('../PetCeremonyModal', () => ({
  default: ({ onDismiss }) => <div role="dialog" aria-label="Hatch celebration"><button onClick={onDismiss}>Close celebration</button></div>,
}));

const egg = inventory.find(({ item }) => item.slug === 'meshtint-bat-egg');
const potion = inventory.find(({ item }) => item.slug === 'base-potion');
const pet = claimReceipt.pet;
const serverNow = '2026-10-18T10:00:00Z';
const empty = { incubation: null, duration_seconds: 7200, server_now: serverNow };
const waiting = {
  id: 7, egg: egg.item, potion: potion.item, species: pet.species, potion_type: pet.potion,
  started_at: serverNow, ready_at: '2026-10-18T12:00:00Z', remaining_seconds: 7200,
  is_ready: false, status: 'incubating', hatched_at: null, pet_id: null,
};
const ready = { ...waiting, remaining_seconds: 0, is_ready: true, status: 'ready' };
const hatched = { ...ready, status: 'hatched', hatched_at: '2026-10-18T12:01:00Z', pet_id: pet.id };

function page(props = {}, handlers = []) {
  server.use(
    ...handlers,
    http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 15 })),
    http.get('*/api/inventory/', () => HttpResponse.json([egg, potion])),
  );
  return render(<MemoryRouter><Hatchery {...props} /></MemoryRouter>);
}
async function selectPair(user) {
  await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.item.id));
  await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(potion.item.id));
}

describe('Timed egg incubation', () => {
  it('presents the server default as a 24-hour incubation before starting an egg', async () => {
    page();
    expect(await screen.findByText(/Incubation takes 24h and continues while you are away/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
  });

  it.each(['inventory', 'pets/stable'])('allows a ready egg to hatch despite a failed %s read, without claiming supplies are empty', async (endpoint) => {
    let current = ready;
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, () => {
      current = null;
      return { incubation: hatched, pet, freshly_hatched: true, server_now: serverNow };
    });
    const onChanged = vi.fn();
    page({ onChanged }, [claim.handler,
      http.get(`*/api/${endpoint}/`, () => HttpResponse.json({ detail: 'Supplies temporarily unavailable' }, { status: 503 })),
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current }))]);
    const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('Supplies temporarily unavailable');
    const hatch = screen.getByRole('button', { name: 'Hatch pet' });
    expect(hatch).toBeEnabled();
    expect(screen.queryByText(/No eggs or potions/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Start incubation' })).toBeNull();
    await user.click(hatch);
    expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', `/bestiary?tab=companions&pet=${pet.id}`);
    expect(claim.calls).toHaveLength(1);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('shows and claims a ready egg while the unrelated inventory read is still pending', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, { incubation: hatched, pet, freshly_hatched: true, server_now: serverNow });
    page({ onChanged: vi.fn() }, [claim.handler,
      http.get('*/api/inventory/', async () => { await pending; return HttpResponse.json([]); }),
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: ready }))]);
    try {
      const hatch = await screen.findByRole('button', { name: 'Hatch pet' });
      expect(hatch).toBeEnabled();
      expect(screen.queryByText(/No eggs or potions/)).toBeNull();
      expect(screen.queryByRole('button', { name: 'Start incubation' })).toBeNull();
      const user = userEvent.setup();
      await user.click(hatch);
      expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', `/bestiary?tab=companions&pet=${pet.id}`);
      expect(claim.calls).toHaveLength(1);
    } finally { await act(async () => { release(); await pending; }); }
  });

  it('shows an incubation read error and its retry while inventory is still pending', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    let unavailable = true;
    page({}, [
      http.get('*/api/inventory/', async () => { await pending; return HttpResponse.json([]); }),
      http.get('*/api/pets/incubations/', () => unavailable
        ? HttpResponse.json({ detail: 'Hatchery unavailable' }, { status: 503 })
        : HttpResponse.json({ ...empty, incubation: ready })),
    ]);
    try {
      expect(await screen.findByRole('alert')).toHaveTextContent('Hatchery unavailable');
      expect(screen.queryByRole('button', { name: 'Start incubation' })).toBeNull();
      unavailable = false;
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: 'Try again' }));
      expect(await screen.findByRole('button', { name: 'Hatch pet' })).toBeEnabled();
    } finally { await act(async () => { release(); await pending; }); }
  });

  it('offers an explicit incubation start instead of immediately hatching selected ingredients', async () => {
    const instantHatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
    server.use(instantHatch.handler);
    const user = userEvent.setup();
    page();
    await selectPair(user);
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeEnabled();
    expect(instantHatch.calls).toHaveLength(0);
  });

  it('starts once with a UUID, consumes no hatch, and restores the pending egg after remount', async () => {
    let current = null;
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, () => {
      current = waiting;
      return HttpResponse.json({ incubation: current, server_now: serverNow }, { status: 201 });
    });
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, {});
    server.use(start.handler, claim.handler,
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current })));
    const user = userEvent.setup();
    let view = page();
    await selectPair(user);
    await user.dblClick(screen.getByRole('button', { name: 'Start incubation' }));
    expect(await screen.findByRole('heading', { name: 'Your egg is incubating' })).toBeInTheDocument();
    expect(screen.getByText('Ready to hatch in 2h.')).toBeInTheDocument();
    expect(start.calls).toHaveLength(1);
    expect(start.calls[0].body).toEqual({ egg_item_id: String(egg.item.id), potion_item_id: String(potion.item.id), request_id: expect.stringMatching(/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i) });
    expect(new URL(start.calls[0].url).pathname).toBe('/api/pets/incubations/');
    expect(claim.calls).toHaveLength(0);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeDisabled();
    view.unmount();
    view = page();
    expect(await screen.findByRole('heading', { name: 'Your egg is incubating' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    expect(start.calls).toHaveLength(1);
    view.unmount();
  });

  it('reuses a start UUID after an uncertain response instead of consuming another pair', async () => {
    let current = null;
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, () => {
      if (start.calls.length === 1) return HttpResponse.json({ detail: 'Connection interrupted' }, { status: 503 });
      current = waiting;
      return { incubation: current, server_now: serverNow };
    });
    server.use(start.handler, http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current })));
    page();
    const user = userEvent.setup();
    await selectPair(user);
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start incubation' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    expect(start.calls).toHaveLength(2);
    expect(start.calls[0].body).toEqual(start.calls[1].body);
  });

  it('reconciles an uncertain committed start on a read without retrying the write', async () => {
    let current = null;
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, () => {
      current = waiting;
      return HttpResponse.json({ detail: 'Connection interrupted' }, { status: 503 });
    });
    server.use(start.handler, http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current })));
    page();
    const user = userEvent.setup();
    await selectPair(user);
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    expect(await screen.findByRole('heading', { name: 'Your egg is incubating' })).toBeInTheDocument();
    expect(start.calls).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeDisabled();
  });

  it('blocks an unknown incubation state, retries the read, and retains a known egg after a failed refresh', async () => {
    let unavailable = true;
    server.use(http.get('*/api/pets/incubations/', () => unavailable
      ? HttpResponse.json({ detail: 'Hatchery unavailable' }, { status: 503 })
      : HttpResponse.json({ ...empty, incubation: waiting })));
    page();
    const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('Hatchery unavailable');
    expect(screen.queryByRole('button', { name: 'Start incubation' })).toBeNull();
    unavailable = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    unavailable = true;
    await user.click(screen.getByRole('button', { name: 'Check readiness' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Hatchery unavailable');
    expect(screen.getByRole('heading', { name: 'Your egg is incubating' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check readiness' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeDisabled();
    unavailable = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it.each([true, false])('requires a ready server read and explicit claim, with a fresh-only ceremony (%s)', async (fresh) => {
    let current = waiting;
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, () => {
      current = null;
      return { incubation: hatched, pet, freshly_hatched: fresh, server_now: serverNow };
    });
    server.use(claim.handler, http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current })));
    page();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    current = ready;
    fireEvent.focus(window);
    await screen.findByRole('heading', { name: 'Your egg is ready to hatch' });
    expect(claim.calls).toHaveLength(0);
    await user.dblClick(screen.getByRole('button', { name: 'Hatch pet' }));
    expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', `/bestiary?tab=companions&pet=${pet.id}`);
    expect(claim.calls).toHaveLength(1);
    expect(claim.calls[0]).toMatchObject({ method: 'POST', body: null });
    expect(new URL(claim.calls[0].url).pathname).toBe('/api/pets/incubations/7/hatch/');
    expect(!!screen.queryByRole('dialog', { name: 'Hatch celebration' })).toBe(fresh);
  });

  it('keeps a rejected early hatch from granting a pet or ceremony and reconciles the server wait', async () => {
    let current = ready;
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, () => {
      current = waiting;
      return HttpResponse.json({ detail: 'Your egg is still incubating.' }, { status: 409 });
    });
    server.use(claim.handler, http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: current })));
    page();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Hatch pet' }));
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Care for your new pet' })).toBeNull();
    expect(claim.calls).toHaveLength(1);
  });

  it('handles a completed start replay without blocking the Hatchery or celebrating it again', async () => {
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, { incubation: hatched, server_now: serverNow });
    server.use(start.handler);
    page();
    const user = userEvent.setup();
    await selectPair(user);
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', `/bestiary?tab=companions&pet=${pet.id}`);
    expect(screen.queryByRole('region', { name: 'Your incubating egg' })).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('ignores a delayed claim receipt after the account credential changes', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const claim = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, async () => {
      await pending;
      return { incubation: hatched, pet, freshly_hatched: true, server_now: serverNow };
    });
    server.use(claim.handler, http.get('*/api/pets/incubations/', () => HttpResponse.json({ ...empty, incubation: ready })));
    const onChanged = vi.fn();
    page({ onChanged });
    const user = userEvent.setup();
    await user.dblClick(await screen.findByRole('button', { name: 'Hatch pet' }));
    expect(claim.calls).toHaveLength(1);
    localStorage.setItem('abby_auth_token', 'another-synthetic-session');
    await act(async () => { release(); await pending; });
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Care for your new pet' })).toBeNull();
  });
});
