import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import PrintingSection from './PrintingSection';

describe('Printing settings', () => {
  it('loads only unmatched jobs and linkable requests, keeping dismissed jobs separate', async () => {
    const queries = [];
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/print-jobs/', ({ request }) => {
        queries.push(new URL(request.url));
        return HttpResponse.json([]);
      }),
      http.get('*/api/print-requests/', ({ request }) => {
        queries.push(new URL(request.url));
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<PrintingSection />);
    expect(await screen.findByRole('heading', { name: 'Prints without a request' })).toBeInTheDocument();
    const jobs = queries.filter((url) => url.pathname === '/api/print-jobs/');
    expect(jobs).toHaveLength(2);
    expect(jobs.every((url) => url.searchParams.get('unlinked') === 'true')).toBe(true);
    expect(jobs.some((url) => url.searchParams.get('dismissed') === 'true')).toBe(true);
    expect(queries.find((url) => url.pathname === '/api/print-requests/').searchParams.get('status')).toBe('approved,printing,failed,completed');
  });

  it('shows failed settings reads with retry and does not report an empty printer registry', async () => {
    let fails = true;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/printers/', () => fails
        ? HttpResponse.json({ detail: 'Temporarily unavailable' }, { status: 503 })
        : HttpResponse.json([])),
    );
    const { user } = renderWithProviders(<PrintingSection />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load all printing settings');
    expect(screen.queryByRole('button', { name: /add printer/i })).not.toBeInTheDocument();
    fails = false;
    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /add printer/i })).toBeInTheDocument();
  });

  it('gates the administration component itself for children', async () => {
    const reads = vi.fn();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/print-jobs/', () => { reads(); return HttpResponse.json([]); }),
    );
    renderWithProviders(<PrintingSection />);
    expect(await screen.findByText('Printing settings are available to parents.')).toBeInTheDocument();
    expect(reads).not.toHaveBeenCalled();
  });
});
