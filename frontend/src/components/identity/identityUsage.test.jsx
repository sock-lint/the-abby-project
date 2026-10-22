import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import AvatarMenu from '../AvatarMenu';
import ChildDashboard from '../../pages/ChildDashboard';
import ProjectHeader from '../../pages/project/ProjectHeader';
import { AuthProvider, useAuth } from '../../hooks/useApi';
import { PulseContext } from '../../providers/pulseContext';
import { server } from '../../test/server';
import { buildProject, buildUser } from '../../test/factories';

const appearance = {
  id: 1, username: 'abby', display_name: 'Abby', avatar: '',
  active_frame: { id: 51, slug: 'frame-steampunk', name: 'Steampunk Gear Frame', metadata: { border_color: '#8B6F3A' } },
  active_title: { id: 52, name: 'Master Crafter', icon: '🔨', metadata: { text: 'Master Crafter' } },
  active_trophy_badge: { id: 53, name: 'First Project', icon: '🏆', rarity: 'common' },
};

function navigation(identity = appearance) {
  return render(<MemoryRouter><PulseContext.Provider value={{ pulse: { identity } }}>
    <AvatarMenu user={buildUser({ display_name: 'Abby' })} />
  </PulseContext.Provider></MemoryRouter>);
}

function AuthenticatedToday() {
  const { user } = useAuth();
  return user ? <ChildDashboard data={{
    rpg: { identity: appearance }, next_actions: [], active_projects: [],
  }} reload={() => {}} /> : null;
}

describe('Earned identity in everyday use', () => {
  it('wears the saved frame, title and trophy in navigation', () => {
    const { container } = navigation();
    const trigger = screen.getByRole('button', { name: 'Open profile menu' });
    expect(within(trigger).getByText('Master Crafter')).toBeInTheDocument();
    expect(within(trigger).getByLabelText('Featured badge: First Project')).toBeInTheDocument();
    expect(container.querySelector('[data-portrait-frame="steampunk"]')).not.toBeNull();
  });

  it('does not wear a previous account’s appearance', () => {
    const { container } = navigation({ ...appearance, id: 88 });
    expect(screen.queryByText('Master Crafter')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Featured badge: First Project')).not.toBeInTheDocument();
    expect(container.querySelector('[data-portrait-frame="steampunk"]')).toBeNull();
  });

  it('leads Today with task guidance without repeating the saved look card', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ display_name: 'Abby' }))));
    render(<MemoryRouter><AuthProvider><AuthenticatedToday /></AuthProvider></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Today', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No urgent tasks right now' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your look' })).not.toBeInTheDocument();
    expect(screen.queryByText('Master Crafter')).not.toBeInTheDocument();
    expect(screen.queryByText('First Project')).not.toBeInTheDocument();
  });

  it('signs a completed project with its maker’s identity, including in the parent view', () => {
    const { container } = render(<MemoryRouter><ProjectHeader
      project={buildProject({ status: 'completed', maker_signature: appearance })}
      isParent isAssigned={false} onAction={() => {}} onEdit={() => {}} onOpenQR={() => {}}
    /></MemoryRouter>);
    const signature = screen.getByRole('region', { name: 'Project maker' });
    expect(within(signature).getByText('Made by Abby')).toBeInTheDocument();
    expect(within(signature).getByText('Master Crafter')).toBeInTheDocument();
    expect(within(signature).getByText('First Project')).toBeInTheDocument();
    expect(container.querySelector('[data-portrait-frame="steampunk"]')).not.toBeNull();
  });

  it('does not invent a maker when the server supplies no signature', () => {
    render(<MemoryRouter><ProjectHeader project={buildProject({ maker_signature: null })}
      isParent={false} isAssigned onAction={() => {}} onEdit={() => {}} onOpenQR={() => {}}
    /></MemoryRouter>);
    expect(screen.queryByRole('region', { name: 'Project maker' })).not.toBeInTheDocument();
  });

  it('does not restore the saved look card when Today receives confirmed identity updates', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ display_name: 'Abby' }))));
    render(<MemoryRouter><AuthProvider><PulseContext.Provider value={{ pulse: { identity: appearance } }}>
      <AuthenticatedToday />
    </PulseContext.Provider></AuthProvider></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Today', level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your look' })).not.toBeInTheDocument();
    expect(screen.queryByText('Master Crafter')).not.toBeInTheDocument();
    expect(screen.queryByText('First Project')).not.toBeInTheDocument();
  });

  it('does not label unfinished work as made', () => {
    render(<MemoryRouter><ProjectHeader project={buildProject({ status: 'in_progress', maker_signature: appearance })}
      isParent isAssigned={false} onAction={() => {}} onEdit={() => {}} onOpenQR={() => {}}
    /></MemoryRouter>);
    const signature = screen.getByRole('region', { name: 'Project maker' });
    expect(within(signature).getByText('Project by Abby')).toBeInTheDocument();
    expect(within(signature).queryByText('Made by Abby')).not.toBeInTheDocument();
  });
});
