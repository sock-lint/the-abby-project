import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import Companions from './party/Companions';
import OwnedMountGrid from './party/OwnedMountGrid';
import VitalPipStrip from '../../components/dashboard/VitalPipStrip';
import ExpeditionLaunchSheet from './party/ExpeditionLaunchSheet';
import SpeciesDetailSheet from './codex/SpeciesDetailSheet';

const chick = {
  id: 1, name: '', species: { id: 2, name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐤' },
  potion: { id: 3, name: 'Base', slug: 'base', rarity: 'common' }, is_active: true,
  catalog_available: true, evolved_to_mount: false, happiness_level: 'happy',
};

afterEach(() => vi.unstubAllEnvs());

describe('Server-confirmed pet stages across the accessible UI', () => {
  it.each([
    ['chick', 20, false, 'Chick'],
    ['fledgling', 50, false, 'Fledgling'],
    ['bird', 100, true, 'Bird'],
  ])('shows %s in the home, collection and care sheet without WebGL', async (evolution_stage, growth_points, evolved_to_mount, label) => {
    vi.stubEnv('VITE_COMPANION_3D', 'false');
    const pet = { ...chick, evolution_stage, growth_points, evolved_to_mount };
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [pet], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    renderWithProviders(<Companions />);
    expect(await screen.findByRole('heading', { name: `Base ${label}` })).toBeInTheDocument();
    const guide = screen.getByRole('list', { name: 'Pet growth stages' });
    expect(within(guide).getAllByRole('listitem')).toHaveLength(3);
    expect(guide.querySelector('[aria-current="step"]')).toHaveTextContent(label);
    const careAction = within(screen.getByRole('list', { name: 'Your companions' })).getByRole('button', { name: `Care for Base ${label}` });
    await userEvent.setup().click(careAction);
    const care = screen.getByRole('dialog', { name: `Care for Base ${label}` });
    if (!evolved_to_mount) expect(within(care).getByText(new RegExp(`${label} · ${growth_points}/100 growth`))).toBeInTheDocument();
  });

  it('keeps a nickname while describing the confirmed form beside it', async () => {
    vi.stubEnv('VITE_COMPANION_3D', 'false');
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [{ ...chick, name: 'Peep', evolution_stage: 'fledgling', growth_points: 65 }], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    renderWithProviders(<Companions />);
    expect(await screen.findByRole('heading', { name: 'Peep' })).toBeInTheDocument();
    expect(screen.getByText('Base Fledgling · 65/100 growth')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Feed your companion' }));
    expect(screen.getByRole('dialog', { name: 'Care for Peep' })).toBeInTheDocument();
    expect(screen.getByText('Fledgling · 65/100 growth')).toBeInTheDocument();
  });

  it('explains all three stages in the species collection without claiming ownership of the middle stage', () => {
    renderWithProviders(<SpeciesDetailSheet species={{ ...chick.species, discovered: true, owned_pet_ids: [1], available_potions: [chick.potion], owned_mount_potion_ids: [] }} onClose={() => {}} />);
    const guide = screen.getByRole('list', { name: 'Pet growth stages' });
    expect(within(guide).getAllByRole('listitem')).toHaveLength(3);
    expect(within(guide).getByText('Fledgling')).toBeInTheDocument();
    expect(within(guide).getByText('From 50 growth')).toBeInTheDocument();
    expect(guide.querySelector('[aria-current]')).toBeNull();
    expect(screen.getByRole('img', { name: 'Base Bird — not yet evolved' })).toBeInTheDocument();
  });

  it('names the intermediate form in the Today pet shortcut', () => {
    renderWithProviders(<VitalPipStrip activePet={{ ...chick, evolution_stage: 'fledgling', growth_points: 65 }} />);
    expect(screen.getByRole('button', { name: 'Fledgling growth' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Base Fledgling' })).toBeInTheDocument();
  });

  it('names Bird in the expedition sheet without changing the saved identity', () => {
    renderWithProviders(<ExpeditionLaunchSheet mount={chick} />);
    expect(screen.getByRole('dialog', { name: 'Send Bird on an expedition' })).toBeInTheDocument();
  });

  it('uses Bird for a grown Chick while preserving a saved legacy species name', () => {
    renderWithProviders(<OwnedMountGrid mounts={[chick, { ...chick, id: 4, species: { slug: 'fox', name: 'Fox', sprite_key: 'fox' } }]} onPreview={() => {}} />);
    expect(screen.getByText('Base Bird')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Visit Base Bird' })).toBeInTheDocument();
    expect(screen.getByText('Base Fox')).toBeInTheDocument();
  });
});
