import { describe, expect, it } from 'vitest';
import { HttpResponse } from 'msw';
import parentPreview from '../../../contracts/api/fixtures/lifecycle-preview.json';
import childPreview from '../../../contracts/api/fixtures/lifecycle-child-preview.json';
import closePreview from '../../../contracts/api/fixtures/lifecycle-close-preview.json';
import { getAccountLifecycle, transferFamilyContact, deleteOwnAccount, closeOwnFamily } from './index';
import { spyHandler } from '../test/spy';
import { server } from '../test/server';

describe('Account lifecycle responses shared with Django', () => {
  it.each([parentPreview, childPreview, closePreview])('preserves the verified current-account impact preview ($user.username)', async (fixture) => {
    const read = spyHandler('get', /\/api\/account\/lifecycle\/$/, fixture);
    server.use(read.handler);
    expect(await getAccountLifecycle()).toEqual(fixture);
    expect(read.calls[0].url).toMatch(/\/api\/account\/lifecycle\/$/);
    expect(read.calls[0].method).toBe('GET');
    expect(fixture.shared_work).toHaveProperty('projects');
    expect(typeof fixture.can_delete_account).toBe('boolean');
    expect(typeof fixture.can_close_family).toBe('boolean');
    expect(fixture.family_version).toMatch(/^[a-f0-9]{64}$/);
  });

  it('sends current-password confirmation to the exact lifecycle mutation endpoints and accepts their 204 receipts', async () => {
    const password = 'synthetic-current-password';
    const successor_id = parentPreview.successors[0].id;
    const transfer = spyHandler('post', /\/api\/account\/lifecycle\/transfer\/$/, new HttpResponse(null, { status: 204 }));
    const deletion = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/, new HttpResponse(null, { status: 204 }));
    const closure = spyHandler('post', /\/api\/account\/lifecycle\/close-family\/$/, new HttpResponse(null, { status: 204 }));
    server.use(transfer.handler, deletion.handler, closure.handler);
    const handoff = { password, successor_id };
    const remove = { password, successor_id, confirm_username: parentPreview.user.username };
    const close = { password, confirm_family_slug: closePreview.family.slug, family_version: closePreview.family_version };
    expect(await transferFamilyContact(handoff)).toBeNull();
    expect(await deleteOwnAccount(remove)).toBeNull();
    expect(await closeOwnFamily(close)).toBeNull();
    for (const [spy, body, path] of [[transfer, handoff, 'transfer'], [deletion, remove, 'delete'], [closure, close, 'close-family']]) {
      expect(spy.calls).toHaveLength(1);
      expect(spy.calls[0]).toMatchObject({ method: 'POST', body });
      expect(spy.calls[0].url).toMatch(new RegExp(`/api/account/lifecycle/${path}/$`));
    }
    expect(JSON.stringify(localStorage)).not.toContain(password);
  });
});
