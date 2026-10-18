import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { AuthProvider } from '../hooks/useApi';
import useParentPendingCounts from '../hooks/useParentPendingCounts';
import { approveCreation } from '../api';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent } from '../test/factories';
import { PulseContext } from './pulseContext';
import ParentReviewProvider from './ParentReviewProvider';

function Count({ name }) {
  const { total, ready, incomplete } = useParentPendingCounts();
  return <output aria-label={name}>{ready ? `${total}${incomplete ? ' unavailable' : ''}` : 'loading'}</output>;
}
function Workspace({ pulse = null }) {
  return <AuthProvider><PulseContext.Provider value={{ pulse }}><ParentReviewProvider>
    <Count name="Header count" /><Count name="Today count" />
  </ParentReviewProvider></PulseContext.Provider></AuthProvider>;
}

describe('one complete parent review source', () => {
  it('shares initial reads and refreshes both counts after a decision elsewhere', async () => {
    let pending = true;
    const creations = spyHandler('get', '*/api/creations/pending/', () => pending ? [{ id: 9 }] : []);
    const decision = spyHandler('post', '*/api/creations/9/approve/', () => { pending = false; return {}; });
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())), creations.handler, decision.handler);
    render(<Workspace />);
    await waitFor(() => expect(screen.getByLabelText('Header count')).toHaveTextContent(/^1$/));
    expect(screen.getByLabelText('Today count')).toHaveTextContent(/^1$/);
    expect(creations.calls).toHaveLength(1);
    await approveCreation(9, {});
    await waitFor(() => expect(screen.getByLabelText('Header count')).toHaveTextContent(/^0$/));
    expect(screen.getByLabelText('Today count')).toHaveTextContent(/^0$/);
    expect(decision.calls).toHaveLength(1);
    expect(decision.calls[0].body).toEqual({});
    expect(creations.calls).toHaveLength(2);
  });

  it('refreshes after a co-parent changes the heartbeat revision', async () => {
    let pending = true;
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/creations/pending/', () => HttpResponse.json(pending ? [{ id: 9 }] : [])));
    const view = render(<Workspace pulse={{ parent_attention: { revision: 'first' } }} />);
    await waitFor(() => expect(screen.getByLabelText('Today count')).toHaveTextContent(/^1$/));
    pending = false;
    view.rerender(<Workspace pulse={{ parent_attention: { revision: 'co-parent-decided' } }} />);
    await waitFor(() => expect(screen.getByLabelText('Today count')).toHaveTextContent(/^0$/));
  });

  it('checks the first heartbeat even when the initial inbox finished earlier', async () => {
    let pending = false;
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/creations/pending/', () => HttpResponse.json(pending ? [{ id: 9 }] : [])));
    const view = render(<Workspace />);
    await waitFor(() => expect(screen.getByLabelText('Today count')).toHaveTextContent(/^0$/));
    pending = true;
    view.rerender(<Workspace pulse={{ parent_attention: { revision: 'first-arrival' } }} />);
    await waitFor(() => expect(screen.getByLabelText('Today count')).toHaveTextContent(/^1$/));
  });

  it('keeps an unavailable state shared across both counts', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/redemptions/', () => HttpResponse.json({}, { status: 503 })));
    render(<Workspace />);
    await waitFor(() => expect(screen.getByLabelText('Header count')).toHaveTextContent('unavailable'));
    expect(screen.getByLabelText('Today count')).toHaveTextContent('unavailable');
  });
});
