import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import content from '../../../contracts/api/fixtures/authoring-content-archived.json';
import editorial from '../../../contracts/api/fixtures/authoring-editorial-archived.json';
import experiment from '../../../contracts/api/fixtures/authoring-experiment-archived.json';
import contentHistory from '../../../contracts/api/fixtures/authoring-content-history.json';
import editorialHistory from '../../../contracts/api/fixtures/authoring-editorial-history.json';
import experimentHistory from '../../../contracts/api/fixtures/authoring-experiment-history.json';
import restored from '../../../contracts/api/fixtures/authoring-experiment-restored.json';
import replay from '../../../contracts/api/fixtures/authoring-experiment-archive-replay.json';
import { setAuthoringArchived, listAuthoringHistory } from './authoringArchives';
import { server } from '../test/server';

const cases = [
  ['content', '/api/rpg/content-workbench/drafts/', content, contentHistory],
  ['editorial', '/api/rpg/editorial/drafts/', editorial, editorialHistory],
  ['experiment', '/api/rpg/progression-lab/experiments/', experiment, experimentHistory],
];

describe('Shared authoring archive contracts', () => {
  it.each(cases)('preserves %s archive receipts and bounded retained-history selectors', async (kind, root, receipt, history) => {
    const data = { revision: 1, is_archived: true, request_id: receipt.request_id, confirmation: true };
    server.use(
      http.post(`*${root}:id/archive/`, async ({ request, params }) => {
        expect(params.id).toBe(receipt.id);
        expect(await request.json()).toEqual(data);
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(receipt);
      }),
      http.get(`*${root}`, ({ request }) => {
        const query = new URL(request.url).searchParams;
        expect(query.get('include_archived')).toBe('true');
        expect(query.get('limit')).toBe('1');
        return HttpResponse.json(history);
      }),
    );
    expect(await setAuthoringArchived(kind, receipt.id, data)).toEqual(receipt);
    expect(await listAuthoringHistory(kind, { includeArchived: true, limit: 1 })).toEqual(history);
    expect(history.total).toBe(1);
    expect(history.experiments?.[0].is_archived ?? history.drafts[0].is_archived).toBe(true);
    expect(receipt.operation).toEqual({ is_archived: true, revision: 2 });
  });

  it('keeps current restored state distinct from the original archive operation on retry', async () => {
    const root = '/api/rpg/progression-lab/experiments/';
    const data = { revision: 2, is_archived: false, request_id: restored.request_id, confirmation: true };
    server.use(http.post(`*${root}:id/archive/`, async ({ request }) => {
      const body = await request.json();
      return HttpResponse.json(body.request_id === restored.request_id ? restored : replay);
    }));
    expect(await setAuthoringArchived('experiment', restored.id, data)).toEqual(restored);
    const result = await setAuthoringArchived('experiment', restored.id, {
      revision: 1, is_archived: true, request_id: experiment.request_id, confirmation: true,
    });
    expect(result).toEqual(replay);
    expect(result).toMatchObject({ is_archived: false, revision: 3, replayed: true,
      operation: { is_archived: true, revision: 2 } });
  });
});
