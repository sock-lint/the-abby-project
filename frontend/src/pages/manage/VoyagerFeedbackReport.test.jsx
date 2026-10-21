import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { useAuth } from '../../hooks/useApi';
import observed from '../../../../contracts/api/fixtures/voyager-feedback-observed.json';
import empty from '../../../../contracts/api/fixtures/voyager-feedback-empty.json';
import VoyagerFeedbackReport from './VoyagerFeedbackReport';

const staff = () => buildParent({ is_staff: true, family: { id: 1 } });
function setup(body = observed) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(staff())),
    http.get('*/api/challenges/voyager-feedback/', () => HttpResponse.json(body)),
  );
}

function SwitchContext({ kind }) {
  const { setUser } = useAuth();
  return <button onClick={() => {
    if (kind === 'credential') localStorage.setItem('abby_auth_token', 'replacement-test-session');
    setUser(staffContext(kind));
  }}>Switch context</button>;
}
function staffContext(kind) {
  return { ...staff(), ...(kind === 'account' ? { id: 101 } : {}), ...(kind === 'family' ? { family: { id: 2 } } : {}) };
}

describe('Reading Voyager feedback', () => {
  it('consumes actual endpoint states and separates saved 45-day, historical 56-day and selected 84-day promises', async () => {
    setup();
    const { user } = renderWithProviders(<VoyagerFeedbackReport />);
    const panel = within(await screen.findByRole('region', { name: 'Reading Voyager feedback' }));
    await panel.findByText(/11 new children/);
    expect(panel.getAllByRole('definition').map((item) => item.textContent)).toEqual(['1', '1', '2', '4', '2', '1']);
    expect(panel.getByText('Ready for next Reading Adventure')).toBeVisible();
    expect(panel.getByText(/not measure global retention or when a child first became eligible/)).toBeVisible();
    expect(panel.getByText(/Snapshot recorded:/)).toHaveTextContent(observed.period.as_of);
    const table = within(panel.getByRole('table', { name: 'Voyager outcomes by saved policy' }));
    for (const group of observed.policy_groups) {
      const cells = within(table.getByRole('row', { name: new RegExp(group.label) })).getAllByRole('cell');
      expect(cells.slice(0, 5).map((item) => item.textContent)).toEqual([
        group.accepted_windows, group.pending_windows, group.mature_completed, group.mature_expired, group.mature_unknown,
      ].map(String));
      expect(cells[5]).toHaveTextContent(`${group.mature_completed} of ${group.mature_denominator} resolved mature windows`);
      expect(cells[6]).toHaveTextContent(String(group.unknown_windows));
    }
    expect(table.getAllByRole('rowheader').map((item) => item.textContent)).toEqual([
      'Saved 45-day windows', '56 days · milestones', '84 days · selected milestones', 'Other or unknown policy',
    ]);
    const historical = within(table.getByRole('row', { name: /56 days/ }));
    expect(historical.getByText('0%', { exact: false })).toHaveTextContent('0 of 1 resolved mature windows');
    const selected = within(table.getByRole('row', { name: /84 days/ }));
    expect(selected.getByText('50%', { exact: false })).toHaveTextContent('1 of 2 resolved mature windows');
    expect(panel.getByText(/Still observing includes early completions/)).toBeVisible();
    expect(panel.getByText(/Unresolved outcomes and unknown timing are excluded/)).toBeVisible();
    expect(panel.getByText(/Historical 45- and 56-day windows, the selected 84-day milestones/)).toBeVisible();
    await user.click(panel.getByText('Voyager coverage and accounting'));
    for (const note of observed.notes) expect(panel.getByText(note)).toBeVisible();
  });

  it.each(['milestone_56_day', 'milestone_84_day'].flatMap((policy) => [
    [`${policy} pending and early-completed`, policy, { accepted_windows: 2, pending_windows: 2, mature_unknown: 0 }],
    [`${policy} unresolved mature`, policy, { accepted_windows: 1, pending_windows: 0, mature_unknown: 1 }],
  ]))('does not turn %s windows into a zero-percent failure rate', async (_label, policy, counts) => {
    const group = observed.policy_groups.find((row) => row.policy === policy);
    setup({ ...observed, policy_groups: [{ ...group, ...counts, mature_completed: 0, mature_expired: 0, unknown_windows: 0, mature_denominator: 0, completion_rate: null }] });
    renderWithProviders(<VoyagerFeedbackReport />);
    expect(await screen.findByText('No resolved mature outcomes')).toBeVisible();
    expect(screen.queryByText('0%', { exact: false })).not.toBeInTheDocument();
  });

  it('describes ungated current catalog readiness as automatic tracking without inventing a next-reading gate', async () => {
    setup({ ...observed, catalog: { ...observed.catalog, acceptance_mode: 'automatic_tracking' } });
    renderWithProviders(<VoyagerFeedbackReport />);
    expect(await screen.findByText('Available for automatic tracking')).toBeVisible();
    expect(screen.queryByText('Ready for next Reading Adventure')).not.toBeInTheDocument();
    expect(screen.queryByText(/Ready children start their window/)).not.toBeInTheDocument();
  });

  it('keeps a cohort with no saved windows distinct from having no eligible children', async () => {
    setup({ ...observed, policy_groups: [] });
    renderWithProviders(<VoyagerFeedbackReport />);
    expect(await screen.findByText('No saved Voyager windows are recorded for this cohort.')).toBeVisible();
    expect(screen.getByText(/11 new children/)).toBeVisible();
  });

  it.each([
    ['insufficient_evidence', /No eligible new children/],
    ['catalog_unavailable', /could not be identified/],
    ['catalog_ambiguous', /More than one Reading Voyager/],
    ['cohort_limit_exceeded', /cohort exceeds this report’s capacity/],
    ['record_limit_exceeded', /records exceed this report’s capacity/],
    ['unrecognized_report_status', /report is unavailable/],
  ])('shows %s without fabricating measured counts or rates', async (status, message) => {
    setup({ ...empty, status });
    renderWithProviders(<VoyagerFeedbackReport />);
    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.queryByRole('definition')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('retries a failed read and preserves explicitly stale saved counts if a refresh fails', async () => {
    setup();
    let reads = 0;
    server.use(http.get('*/api/challenges/voyager-feedback/', () => ++reads === 2
      ? HttpResponse.json({ detail: 'Feedback is temporarily unavailable.' }, { status: 503 })
      : HttpResponse.json(observed)));
    const { user } = renderWithProviders(<VoyagerFeedbackReport />);
    await screen.findByText(/11 new children/);
    await user.click(screen.getByRole('button', { name: 'Refresh Voyager feedback' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Feedback is temporarily unavailable.');
    expect(screen.getByText(/Last successful snapshot shown below/)).toBeVisible();
    expect(screen.getByRole('table', { name: 'Voyager outcomes by saved policy' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.queryByText(/Last successful snapshot shown below/)).not.toBeInTheDocument();
    expect(reads).toBe(3);
  });

  it.each([buildUser(), buildParent({ is_staff: false })])('does not request household feedback for nonstaff accounts', async (account) => {
    let reads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(account)),
      http.get('*/api/challenges/voyager-feedback/', () => { reads += 1; return HttpResponse.json(observed); }),
    );
    const { container } = renderWithProviders(<VoyagerFeedbackReport />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
    expect(reads).toBe(0);
  });

  it.each(['account', 'family', 'credential'])('discards delayed feedback after %s replacement', async (kind) => {
    setup();
    let release;
    let reads = 0;
    const gate = new Promise((resolve) => { release = resolve; });
    server.use(http.get('*/api/challenges/voyager-feedback/', async () => {
      reads += 1;
      if (reads === 1) { await gate; return HttpResponse.json(observed); }
      return HttpResponse.json(empty);
    }));
    const { user } = renderWithProviders(<><SwitchContext kind={kind} /><VoyagerFeedbackReport /></>);
    await waitFor(() => expect(reads).toBe(1));
    await user.click(screen.getByRole('button', { name: 'Switch context' }));
    await screen.findByText(/No eligible new children/);
    await act(async () => { release(); await gate; });
    expect(screen.queryByText(/11 new children/)).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(reads).toBe(2);
  });
});
