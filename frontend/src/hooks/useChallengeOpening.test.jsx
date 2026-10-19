import { StrictMode } from 'react';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { recordChallengeOpening } from '../api';
import { setToken } from '../api/client';
import { buildChallengeGoal } from '../test/challenges';
import useChallengeOpening from './useChallengeOpening';

vi.mock('../api', () => ({ recordChallengeOpening: vi.fn() }));

const child = { id: 7, role: 'child', family: { id: 1 } };
const opened = { id: 'goal:11', first_details_opened_at: '2026-10-18T19:00:00Z' };
const goal = buildChallengeGoal({ origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null });
function deferred() { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function Probe({ value = goal, user = child, onConfirmed }) {
  useChallengeOpening(value, { user, onConfirmed });
  return <p>{value.description}</p>;
}

beforeEach(() => { recordChallengeOpening.mockReset(); setToken('opening-token'); });

describe('Challenge details opening', () => {
  it('shares one pending request across StrictMode replay and confirms only the server result', async () => {
    const request = deferred();
    recordChallengeOpening.mockReturnValue(request.promise);
    const confirmed = vi.fn();
    render(<StrictMode><Probe onConfirmed={confirmed} /></StrictMode>);
    expect(recordChallengeOpening).toHaveBeenCalledTimes(1);
    expect(recordChallengeOpening).toHaveBeenCalledWith(goal.id, { token: 'opening-token' });
    expect(confirmed).not.toHaveBeenCalled();
    await act(async () => request.resolve(opened));
    expect(confirmed).toHaveBeenCalledExactlyOnceWith(opened);
  });

  it('does not retry a failed request until the details are closed and reopened', async () => {
    recordChallengeOpening.mockRejectedValue(new Error('Offline'));
    const confirmed = vi.fn();
    const view = render(<Probe onConfirmed={confirmed} />);
    await act(async () => {});
    view.rerender(<Probe value={{ ...goal, progress: '1' }} onConfirmed={confirmed} />);
    await act(async () => {});
    expect(recordChallengeOpening).toHaveBeenCalledTimes(1);
    expect(confirmed).not.toHaveBeenCalled();
    view.unmount();
    recordChallengeOpening.mockResolvedValue(opened);
    render(<Probe onConfirmed={confirmed} />);
    await act(async () => {});
    expect(recordChallengeOpening).toHaveBeenCalledTimes(2);
    expect(confirmed).toHaveBeenCalledExactlyOnceWith(opened);
  });

  it.each([
    [{ ...child, role: 'parent' }, goal], [null, goal],
    [child, { ...goal, origin: 'parent' }], [child, { ...goal, origin: 'legacy', legacy: true }],
    [child, { ...goal, status: 'upcoming' }], [child, { ...goal, catalog_repeatable: undefined }],
    [child, { ...goal, first_details_opened_at: opened.first_details_opened_at }],
  ])('does not record ineligible or already confirmed details %#', async (user, value) => {
    render(<Probe value={value} user={user} onConfirmed={vi.fn()} />);
    await act(async () => {});
    expect(recordChallengeOpening).not.toHaveBeenCalled();
  });

  it('never records a cached identity without an authenticated credential', async () => {
    setToken(null);
    render(<Probe onConfirmed={vi.fn()} />);
    await act(async () => {});
    expect(recordChallengeOpening).not.toHaveBeenCalled();
  });

  it.each(['completed', 'expired'])('records catalog %s history without changing its progress', async (status) => {
    const confirmed = vi.fn();
    recordChallengeOpening.mockResolvedValue(opened);
    render(<Probe value={{ ...goal, status }} onConfirmed={confirmed} />);
    await act(async () => {});
    expect(confirmed).toHaveBeenCalledExactlyOnceWith(opened);
  });

  it('discards an old child response after the account changes', async () => {
    const oldRequest = deferred();
    const newRequest = deferred();
    recordChallengeOpening.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);
    const confirmed = vi.fn();
    const view = render(<Probe onConfirmed={confirmed} />);
    view.rerender(<Probe user={{ ...child, id: 8 }} onConfirmed={confirmed} />);
    await act(async () => oldRequest.resolve(opened));
    expect(confirmed).not.toHaveBeenCalled();
    await act(async () => newRequest.resolve(opened));
    expect(confirmed).toHaveBeenCalledExactlyOnceWith(opened);
  });

  it('discards late results after a token replacement without another render or after unmount', async () => {
    const request = deferred();
    recordChallengeOpening.mockReturnValue(request.promise);
    const confirmed = vi.fn();
    const view = render(<Probe onConfirmed={confirmed} />);
    setToken('different-token');
    await act(async () => request.resolve(opened));
    expect(confirmed).not.toHaveBeenCalled();
    view.unmount();
    const later = deferred();
    recordChallengeOpening.mockReturnValue(later.promise);
    const second = render(<Probe onConfirmed={confirmed} />);
    second.unmount();
    await act(async () => later.resolve(opened));
    expect(confirmed).not.toHaveBeenCalled();
  });

  it.each([{ ...opened, id: 'goal:99' }, { ...opened, first_details_opened_at: null }, { ...opened, first_details_opened_at: 'invalid' }])('does not confirm malformed or different-occurrence results %#', async (response) => {
    const confirmed = vi.fn();
    recordChallengeOpening.mockResolvedValue(response);
    render(<Probe onConfirmed={confirmed} />);
    await act(async () => {});
    expect(confirmed).not.toHaveBeenCalled();
  });
});
