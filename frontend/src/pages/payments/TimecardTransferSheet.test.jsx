import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen } from '@testing-library/react';
import TimecardTransferSheet from './TimecardTransferSheet';
import { server } from '../../test/server';

describe('TimecardTransferSheet', () => {
  it('withholds confirmation when a previously approved timecard is no longer payable', async () => {
    server.use(http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json({ approved_timecards: [] })));
    render(<TimecardTransferSheet timecard={{ id: 2, user: 7, username: 'Abby' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('This timecard is no longer ready for payment.');
    expect(screen.queryByRole('button', { name: 'Record completed transfer' })).not.toBeInTheDocument();
  });
});
