import { beforeEach, describe, expect, it } from 'vitest';
import { AUTH_CHANGED_EVENT } from '../../api/client';
import { STORAGE_KEYS } from '../../constants/storage';
import { clearAvatarDraft, readAvatarDraft, resetAvatarDrafts, writeAvatarDraft } from './draftStore';
import { archerConfiguration } from './catalog.fixtures';
const scope = { accountId: 8, credential: 'synthetic-one' };
beforeEach(resetAvatarDrafts);
describe('in-memory avatar drafts', () => {
  it('retains only independent edit copies for the same account and credential', () => {
    readAvatarDraft(scope, 'configuration');
    const draft = structuredClone(archerConfiguration);
    writeAvatarDraft(scope, 'configuration', draft);
    draft.accessories.left_hand = 'bow-myth';
    expect(readAvatarDraft(scope, 'configuration').accessories.left_hand).toBe('none');
    const loaded = readAvatarDraft(scope, 'configuration'); loaded.appearance.outfit = 'fire';
    expect(readAvatarDraft(scope, 'configuration').appearance.outfit).toBe('nature');
    clearAvatarDraft(scope, 'configuration');
    expect(readAvatarDraft(scope, 'configuration')).toBeUndefined();
  });
  it.each([{ accountId: 9, credential: 'synthetic-one' }, { accountId: 8, credential: 'synthetic-two' }, { accountId: null, credential: '' }])('never restores a previous scope after an identity change', (next) => {
    readAvatarDraft(scope, 'configuration');writeAvatarDraft(scope, 'configuration', archerConfiguration);
    expect(readAvatarDraft(next, 'configuration')).toBeUndefined();
    writeAvatarDraft(scope, 'configuration', archerConfiguration);
    expect(readAvatarDraft(scope, 'configuration')).toBeUndefined();
  });
  it.each([new Event(AUTH_CHANGED_EVENT), new StorageEvent('storage', { key: STORAGE_KEYS.AUTH_TOKEN }), new StorageEvent('storage', { key: null })])('clears drafts on same-tab and external auth changes while unmounted', (event) => {
    readAvatarDraft(scope, 'configuration');writeAvatarDraft(scope, 'configuration', archerConfiguration);
    window.dispatchEvent(event);
    expect(readAvatarDraft(scope, 'configuration')).toBeUndefined();
  });
});
