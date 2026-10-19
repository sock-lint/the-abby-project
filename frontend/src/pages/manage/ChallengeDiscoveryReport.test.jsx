import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor, act } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { useAuth } from '../../hooks/useApi';
import observed from '../../../../contracts/api/fixtures/challenge-discovery-observed.json';
import ChallengeDiscoveryReport from './ChallengeDiscoveryReport';

function setup(body = observed) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ is_staff: true }))),
    http.get('*/api/challenges/discovery/', () => HttpResponse.json(body)),
  );
}

function SwitchFamily() {
  const { setUser } = useAuth();
  return <button onClick={() => setUser(buildParent({ id: 96, family: { id: 96 } }))}>Switch family</button>;
}

describe('recorded challenge discovery', () => {
  it('consumes real endpoint fixtures and keeps openings separate from completions and impressions', async () => {
    setup();
    const { user } = renderWithProviders(<ChallengeDiscoveryReport />);
    const report = await screen.findByRole('region', { name: 'Recorded challenge discovery' });
    await within(report).findByText('Completed without a recorded opening');
    const metrics = within(report).getAllByRole('definition').map((row) => row.textContent);
    expect(metrics).toEqual(['2', '1', '2', '1']);
    expect(within(report).getByText(/Opening details does not establish/)).toBeInTheDocument();
    expect(within(report).getByText(/not screen impressions/)).toBeInTheDocument();
    await user.click(within(report).getByText('Discovery coverage and accounting'));
    expect(within(report).getByText(/1 tracked children/)).toHaveTextContent('1 with unknown earlier opening history');
    expect(within(report).getByText(/counts overlap/i)).toBeInTheDocument();
  });

  it.each(['insufficient_evidence', 'cohort_limit_exceeded', 'occurrence_limit_exceeded'])('shows %s without presenting missing counts as measured zeros', async (status) => {
    setup({ ...observed, status, catalog_occurrences: Object.fromEntries(Object.keys(observed.catalog_occurrences).map((key) => [key, null])) });
    renderWithProviders(<ChallengeDiscoveryReport />);
    const message = status === 'insufficient_evidence' ? /No tracked challenge windows/ : /Observation capacity was exceeded/;
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole('definition')).not.toBeInTheDocument();
  });

  it('keeps a failed read recoverable and refreshes from the server', async () => {
    setup();
    server.use(http.get('*/api/challenges/discovery/', () => HttpResponse.json({ detail: 'Temporarily unavailable.' }, { status: 503 })));
    const { user } = renderWithProviders(<ChallengeDiscoveryReport />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporarily unavailable.');
    setup();
    await user.click(screen.getByRole('button', { name: 'Refresh discovery' }));
    expect(await screen.findByText('Completed without a recorded opening')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not request household discovery for a child', async () => {
    let reads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/discovery/', () => { reads += 1; return HttpResponse.json(observed); }),
    );
    const { container } = renderWithProviders(<ChallengeDiscoveryReport />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
    expect(reads).toBe(0);
  });

  it('discards a previous family response after the account context changes', async () => {
    setup();
    let release;
    let reads = 0;
    const gate = new Promise((resolve) => { release = resolve; });
    server.use(http.get('*/api/challenges/discovery/', async () => {
      reads += 1;
      if (reads === 1) { await gate; return HttpResponse.json(observed); }
      return HttpResponse.json({ ...observed, status: 'insufficient_evidence' });
    }));
    const { user } = renderWithProviders(<><SwitchFamily /><ChallengeDiscoveryReport /></>);
    await waitFor(() => expect(reads).toBe(1));
    await user.click(screen.getByRole('button', { name: 'Switch family' }));
    await screen.findByText(/No tracked challenge windows/);
    await act(async () => { release(); await gate; });
    expect(screen.queryByText('Completed without a recorded opening')).not.toBeInTheDocument();
    expect(reads).toBe(2);
  });
});
