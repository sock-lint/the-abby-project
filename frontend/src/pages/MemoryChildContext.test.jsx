import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { useAuth } from '../hooks/useApi';
import JournalReader from './chronicle/JournalReader';
import GradesPage from './grades/GradesPage';
import Yearbook from './Yearbook';

function Harness() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const tab = new URLSearchParams(location.search).get('tab');
  return <>
    <button onClick={() => navigate('/chronicle?tab=grades&child=8')}>Open grades</button>
    <button onClick={() => navigate('/chronicle?tab=yearbook&child=8')}>Open timeline</button>
    <button onClick={() => setUser(buildParent({ id: 100, family: { id: 2 } }))}>Switch family</button>
    {tab === 'grades' ? <GradesPage /> : tab === 'yearbook' ? <Yearbook /> : <JournalReader />}
  </>;
}
function handlers() {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ family: { id: 1 } }))),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, username: 'abby' }, { id: 8, username: 'ben' }])),
  );
}
const summary = (user, title) => ({ chapters: [{ chapter_year: 2026, label: 'This year', is_current: true, entries: [
  { id: user, user, kind: 'journal', title, summary: 'Shared memory', is_private: false },
] }] });

describe('Memory child context', () => {
  it('opens the explicit child and carries it through related Memory tabs', async () => {
    handlers();
    const reads = [];
    server.use(
      http.get('*/api/chronicle/summary/', ({ request }) => {
        reads.push(new URL(request.url).searchParams.get('user_id'));
        return HttpResponse.json(summary(8, 'Ben memory'));
      }),
      http.get('*/api/chronicle/grades/', ({ request }) => {
        reads.push(new URL(request.url).searchParams.get('user_id'));
        return HttpResponse.json({ results: [], count: 0 });
      }),
    );
    const { user } = renderWithProviders(<Harness />, { route: '/chronicle?tab=journal&child=8' });
    expect(await screen.findByRole('combobox', { name: 'Viewing' })).toHaveValue('8');
    await screen.findByRole('heading', { name: 'Ben memory' });
    await user.click(screen.getByRole('button', { name: 'Open grades' }));
    expect(await screen.findByRole('combobox', { name: 'Viewing' })).toHaveValue('8');
    await waitFor(() => expect(reads).toHaveLength(2));
    await user.click(screen.getByRole('button', { name: 'Open timeline' }));
    expect(await screen.findByRole('combobox', { name: 'Viewing' })).toHaveValue('8');
    await waitFor(() => expect(reads).toEqual(['8', '8', '8']));
  });
  it('never renders a sibling or private journal if the response includes it', async () => {
    handlers();
    server.use(http.get('*/api/chronicle/summary/', () => HttpResponse.json({ chapters: [{ chapter_year: 2026, entries: [
      { id: 1, user: 8, kind: 'journal', title: 'Selected shared', is_private: false },
      { id: 2, user: 7, kind: 'journal', title: 'Sibling shared', is_private: false },
      { id: 3, user: 8, kind: 'journal', title: 'Private', is_private: true },
      { id: 4, kind: 'journal', title: 'Unknown author', is_private: false },
    ] }] })));
    renderWithProviders(<JournalReader />, { route: '/chronicle?tab=journal&child=8' });
    await screen.findByText('Selected shared');
    expect(screen.queryByText('Sibling shared')).toBeNull();
    expect(screen.queryByText('Private')).toBeNull();
    expect(screen.queryByText('Unknown author')).toBeNull();
  });
  it('clears the previous family roster and memories before the new roster arrives', async () => {
    handlers();
    server.use(http.get('*/api/chronicle/summary/', () => HttpResponse.json(summary(8, 'Old family memory'))));
    const { user } = renderWithProviders(<Harness />, { route: '/chronicle?tab=journal&child=8' });
    await screen.findByText('Old family memory');
    let release;
    server.use(http.get('*/api/children/', async () => {
      await new Promise((resolve) => { release = resolve; });
      return HttpResponse.json([{ id: 9, username: 'new-child' }]);
    }));
    await user.click(screen.getByRole('button', { name: 'Switch family' }));
    expect(screen.queryByText('Old family memory')).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
    await waitFor(() => expect(release).toBeDefined());
    server.use(http.get('*/api/chronicle/summary/', () => HttpResponse.json(summary(9, 'New family memory'))));
    release();
    expect(await screen.findByText('New family memory')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('9');
  });
});

it('rejects a child outside the verified roster and ignores child links for child accounts', async () => {
  handlers();
  const targets = [];
  server.use(http.get('*/api/chronicle/summary/', ({ request }) => {
    const target = new URL(request.url).searchParams.get('user_id');
    targets.push(target);
    return HttpResponse.json(summary(target ? 7 : 1, 'Safe memory'));
  }));
  const view = renderWithProviders(<JournalReader />, { route: '/chronicle?child=999' });
  await screen.findByText('Safe memory');
  expect(targets).toEqual(['7']);
  expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('7');
  view.unmount();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 1, role: 'child', username: 'abby' })));
  renderWithProviders(<JournalReader />, { route: '/chronicle?child=8' });
  await screen.findByText('Safe memory');
  expect(targets).toEqual(['7', null]);
  expect(screen.queryByRole('combobox')).toBeNull();
});

it('a delayed response from a previous selected child cannot replace the current history', async () => {
  handlers();
  let release;
  server.use(http.get('*/api/chronicle/summary/', async ({ request }) => {
    const child = Number(new URL(request.url).searchParams.get('user_id'));
    if (child === 7) await new Promise((resolve) => { release = resolve; });
    return HttpResponse.json(summary(child, child === 7 ? 'Late Abby memory' : 'Ben memory'));
  }));
  const { user } = renderWithProviders(<JournalReader />);
  await waitFor(() => expect(release).toBeDefined());
  await user.selectOptions(screen.getByRole('combobox', { name: 'Viewing' }), '8');
  await screen.findByText('Ben memory');
  release();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText('Late Abby memory')).toBeNull();
  expect(screen.getByText('Ben memory')).toBeInTheDocument();
});
