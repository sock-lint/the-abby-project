import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { useAuth } from '../../hooks/useApi';
import UsageDashboard from './UsageDashboard';
import observed from '../../../../contracts/api/fixtures/usage-family-observed.json';
import empty from '../../../../contracts/api/fixtures/usage-family-empty.json';

const staff = () => buildParent({ is_staff: true, family: { id: 1 } });
function report(overrides = {}) {
  const counts = { active_families: 2, active_children: 3, active_parents: 1, completed_activities: 12, actions: 16, visitors: 5 };
  return {
    scope: 'family', can_view_deployment: false, filters: { days: 28, role: 'all', feature: 'all' },
    period: { start: '2026-09-26', end: '2026-10-23', previous_start: '2026-08-29', previous_end: '2026-09-25', timezone: 'UTC' },
    collection: { started_at: '2026-10-01T00:00:00Z', retention_days: 90, history_complete: false, previous_history_complete: false, notes: ['Prior visits cannot be reconstructed.', 'Saved rewards do not multiply actions.'] },
    summary: { current: counts, previous: { ...counts, completed_activities: 8 } },
    trend: [{ date: '2026-10-22', active_families: 1, active_people: 2, completed_activities: 4, visitors: 3 }, { date: '2026-10-23', active_families: 1, active_people: 2, completed_activities: 8, visitors: 2 }],
    features: [{ feature: 'reading', actors: 3, actions: 5, completed_activities: 5 }],
    onboarding: { families_created: 2, child_added: 2, first_activity: 1, first_parent_approval: 1, coverage: 'Recorded milestones only; earlier milestones are unknown.' },
    retention: { week_1: { eligible_families: 2, returned_families: 1, rate: 0.5, history_complete: true, cohort_start: '2026-10-05', cohort_end: '2026-10-11', return_start: '2026-10-12', return_end: '2026-10-18' }, week_4: { eligible_families: null, returned_families: null, rate: null, history_complete: false, cohort_start: '2026-09-14', cohort_end: '2026-09-20', return_start: '2026-10-12', return_end: '2026-10-18' }, definition: 'Full observed activity weeks only; unknown history is excluded.' },
    friction: { pending_reviews: 3, median_approval_hours: null, coverage: ['homework', 'chores'], unavailable: ['workflow_abandonment', 'failed_saves', 'sign_in_failures', 'request_latency'] },
    weekly_summary: { start: '2026-10-17', end: '2026-10-23', ...counts },
    ...overrides,
  };
}
function setup(body = report()) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(staff())),
    http.get('*/api/admin/usage/', () => HttpResponse.json(body)),
  );
}
async function select(user, label, option) {
  await user.click(screen.getByRole('combobox', { name: label }));
  await user.click(screen.getByRole('option', { name: option, exact: true }));
}
function SwitchContext({ kind }) {
  const { setUser } = useAuth();
  return <button onClick={() => {
    if (kind === 'credential') localStorage.setItem('abby_auth_token', 'replacement-session');
    setUser({ ...staff(), ...(kind === 'account' ? { id: 101 } : {}), ...(kind === 'family' ? { family: { id: 2 } } : {}), ...(kind === 'role' ? { role: 'child' } : {}) });
  }}>Switch context</button>;
}

describe('Usage dashboard', () => {
  it('renders the real endpoint aggregate fixture without family identities or source content', async () => {
    setup(observed);
    renderWithProviders(<UsageDashboard />);
    const features = within(await screen.findByRole('table', { name: 'Feature adoption' }));
    expect(features.getByRole('row', { name: 'Chores 2 4 3' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Returning families' })).toHaveTextContent('1 returned of 1 eligible families');
    expect(screen.getByRole('region', { name: 'Review queue and friction' })).toHaveTextContent('24 hours');
    expect(screen.queryByText('usage-child')).not.toBeInTheDocument();
    for (const note of observed.collection.notes) expect(screen.getByText(note)).toBeVisible();
  });

  it('renders the real unobserved endpoint fixture as collecting history', async () => {
    setup(empty);
    renderWithProviders(<UsageDashboard />);
    expect(await screen.findByText(/Collection is starting/)).toBeVisible();
    expect(screen.getAllByText('Collecting history')).toHaveLength(2);
    expect(screen.getAllByText('Previous period: Collecting history')).toHaveLength(4);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Activities recorded by/ })).not.toBeInTheDocument();
  });

  it('keeps unobserved trend dates unavailable and labels mixed weekly counts partial', async () => {
    const body = report();
    setup({ ...body, collection: { ...body.collection, started_at: '2026-10-23T12:00:00Z' } });
    const { user } = renderWithProviders(<UsageDashboard />);
    await screen.findByRole('table', { name: 'Feature adoption' });
    await user.click(screen.getByText('View exact trend counts'));
    const daily = within(screen.getByRole('table', { name: 'Activity trend counts' }));
    expect(daily.getByRole('row', { name: '2026-10-22 Unavailable' })).toBeVisible();
    expect(daily.getByRole('row', { name: '2026-10-23 8 (partial history)' })).toBeVisible();
    await select(user, 'Trend interval', 'Weekly');
    expect(screen.getByRole('row', { name: '2026-10-19 8 (partial history)' })).toBeVisible();
    expect(screen.getByRole('img', { name: /Activities recorded by week/ })).toHaveAccessibleName(/scale 0 to 8/);
  });
  it('shows meaningful counts, comparisons, honest gaps, mature returns and weekly summary', async () => {
    setup();
    const { user } = renderWithProviders(<UsageDashboard />);
    const features = within(await screen.findByRole('table', { name: 'Feature adoption' }));
    expect(features.getByRole('row', { name: 'Reading 3 5 5' })).toBeVisible();
    expect(screen.getAllByText('Previous period: Collecting history')).toHaveLength(4);
    expect(screen.getByText(/Partial history: collection began 2026-10-01/)).toBeVisible();
    const retention = within(screen.getByRole('region', { name: 'Returning families' }));
    expect(retention.getByText('50%')).toBeVisible();
    expect(retention.getByText('1 returned of 2 eligible families')).toBeVisible();
    expect(retention.getByText('Collecting history')).toBeVisible();
    expect(retention.queryByText('0%')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Review queue and friction' })).toHaveTextContent('Unavailable');
    expect(screen.getByRole('region', { name: 'Weekly summary' })).toHaveTextContent('2026-10-17 through 2026-10-23');
    expect(screen.getByText('Prior visits cannot be reconstructed.')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Coverage and privacy' })).toHaveTextContent('journal content, form text, raw page URLs and session recordings');
    await user.click(screen.getByText('View exact trend counts'));
    expect(screen.getByRole('table', { name: 'Activity trend counts' })).toHaveTextContent('2026-10-22');
    await select(user, 'Trend interval', 'Weekly');
    expect(screen.getByRole('table', { name: 'Activity trend counts' })).toHaveTextContent('2026-10-19');
    expect(screen.getByRole('row', { name: '2026-10-19 12' })).toBeVisible();
  });

  it('compares complete observed periods and distinguishes a mature empty cohort from missing history', async () => {
    const body = report();
    setup({ ...body, collection: { ...body.collection, history_complete: true, previous_history_complete: true }, retention: { ...body.retention, week_4: { ...body.retention.week_4, history_complete: true, eligible_families: 0, returned_families: 0 } } });
    renderWithProviders(<UsageDashboard />);
    expect(await screen.findByText('Previous period: 8')).toBeVisible();
    expect(screen.queryByText(/Partial history/)).not.toBeInTheDocument();
    expect(screen.getByText('No active families in the earlier week')).toBeVisible();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('uses server capability for deployment scope and sends exact supported filters', async () => {
    setup();
    const calls = [];
    server.use(http.get('*/api/admin/usage/', ({ request }) => {
      const params = new URL(request.url).searchParams;
      const filters = { days: Number(params.get('days')), role: params.get('role'), feature: params.get('feature') };
      calls.push({ scope: params.get('scope'), ...filters });
      return HttpResponse.json(report({ scope: params.get('scope'), filters, can_view_deployment: true }));
    }));
    const { user } = renderWithProviders(<UsageDashboard />);
    await screen.findByRole('table', { name: 'Feature adoption' });
    await select(user, 'Scope', 'All families');
    await screen.findByRole('table', { name: 'Feature adoption' });
    await select(user, 'Date range', 'Last 7 days');
    await screen.findByRole('table', { name: 'Feature adoption' });
    await select(user, 'Role', 'Children');
    await screen.findByRole('table', { name: 'Feature adoption' });
    await select(user, 'Feature', 'Reading');
    await screen.findByRole('table', { name: 'Feature adoption' });
    expect(calls[0]).toEqual({ scope: 'family', days: 28, role: 'all', feature: 'all' });
    expect(calls.at(-1)).toEqual({ scope: 'deployment', days: 7, role: 'child', feature: 'reading' });
    expect(screen.getByRole('region', { name: 'Getting started' })).toHaveTextContent('Role and feature filters do not apply');
  });

  it('does not offer deployment scope from a client account flag without server permission', async () => {
    setup();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ ...staff(), is_superuser: true })));
    const { user } = renderWithProviders(<UsageDashboard />);
    await screen.findByRole('table', { name: 'Feature adoption' });
    await user.click(screen.getByRole('combobox', { name: 'Scope' }));
    expect(screen.queryByRole('option', { name: 'All families' })).not.toBeInTheDocument();
  });

  it('shows a failed read with retry and labels retained same-filter snapshots stale', async () => {
    setup();
    let reads = 0;
    server.use(http.get('*/api/admin/usage/', () => ++reads % 2 === 1 ? HttpResponse.json({ detail: 'Report unavailable.' }, { status: 503 }) : HttpResponse.json(report())));
    const { user } = renderWithProviders(<UsageDashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Report unavailable.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('table', { name: 'Feature adoption' });
    await user.click(screen.getByRole('button', { name: 'Refresh usage' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Report unavailable.');
    expect(screen.getByText(/Last successful snapshot shown below/)).toBeVisible();
    expect(screen.getByRole('table', { name: 'Feature adoption' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('clears stale data on forbidden refresh', async () => {
    setup();
    const { user } = renderWithProviders(<UsageDashboard />);
    await screen.findByRole('table', { name: 'Feature adoption' });
    server.use(http.get('*/api/admin/usage/', () => HttpResponse.json({ detail: 'Forbidden' }, { status: 403 })));
    await user.click(screen.getByRole('button', { name: 'Refresh usage' }));
    await screen.findByText(/Viewing all families also requires deployment administrator access/);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('keeps empty observed data separate from missing history', async () => {
    const body = report();
    setup({ ...body, summary: { ...body.summary, current: { ...body.summary.current, actions: 0, completed_activities: 0 } } });
    renderWithProviders(<UsageDashboard />);
    expect(await screen.findByText(/No meaningful activity recorded for these filters/)).toBeVisible();
    expect(screen.getByText(/Partial history/)).toBeVisible();
  });

  it('removes previous filter data immediately and ignores delayed responses', async () => {
    setup();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    let reads = 0;
    server.use(http.get('*/api/admin/usage/', async ({ request }) => {
      reads += 1;
      const days = Number(new URL(request.url).searchParams.get('days'));
      if (days === 7) await gate;
      return HttpResponse.json(report({ filters: { days, role: 'all', feature: 'all' }, features: [{ feature: days === 7 ? 'homework' : 'reading', actors: 3, actions: 5, completed_activities: 5 }] }));
    }));
    const { user } = renderWithProviders(<UsageDashboard />);
    await screen.findByRole('table', { name: 'Feature adoption' });
    await select(user, 'Date range', 'Last 7 days');
    expect(screen.queryByRole('table', { name: 'Feature adoption' })).not.toBeInTheDocument();
    await select(user, 'Date range', 'Last 90 days');
    await screen.findByRole('table', { name: 'Feature adoption' });
    await act(async () => { release(); await gate; });
    expect(screen.getByRole('table', { name: 'Feature adoption' })).toHaveTextContent('Reading');
    expect(screen.getByRole('table', { name: 'Feature adoption' })).not.toHaveTextContent('Homework');
    expect(reads).toBe(3);
  });

  it.each(['account', 'family', 'credential', 'role'])('discards delayed data after %s change', async (kind) => {
    setup();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    let reads = 0;
    server.use(http.get('*/api/admin/usage/', async () => {
      if (++reads === 1) { await gate; return HttpResponse.json(report()); }
      return HttpResponse.json({ detail: 'Forbidden' }, { status: 403 });
    }));
    const { user } = renderWithProviders(<><SwitchContext kind={kind} /><UsageDashboard /></>);
    await waitFor(() => expect(reads).toBe(1));
    await user.click(screen.getByRole('button', { name: 'Switch context' }));
    await act(async () => { release(); await gate; });
    await screen.findByText(/Usage is available to staff parents/);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('does not request a report for child accounts', async () => {
    setup();
    let reads = 0;
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())), http.get('*/api/admin/usage/', () => { reads++; return HttpResponse.json(report()); }));
    renderWithProviders(<UsageDashboard />);
    await screen.findByText('Usage is available to staff parents.');
    expect(reads).toBe(0);
  });
});
