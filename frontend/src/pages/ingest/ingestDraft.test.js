import { describe, expect, it, vi } from 'vitest';
import { clearIngestDraft, DEFAULT_OVERRIDES, ingestDraftKey, readIngestDraft, storeIngestDraft } from './ingestDraft';

const snapshot = {
  jobId: 'import-1', draft: { title: 'Custom feeder' }, overrides: DEFAULT_OVERRIDES,
  sourceTab: 'url', url: 'https://example.com/tutorial', pendingCommit: true,
};

describe('import device drafts', () => {
  it('restores an unfinished creation only for its author and rehydrates editor arrays', () => {
    expect(storeIngestDraft(99, snapshot)).toBe(true);
    expect(readIngestDraft(98)).toBeNull();
    expect(readIngestDraft(99)).toEqual({
      ...snapshot, draft: { title: 'Custom feeder', milestones: [], materials: [], steps: [], resources: [] },
    });
  });

  it('does not clear a newer import when an older response finishes', () => {
    storeIngestDraft(99, snapshot);
    clearIngestDraft(99, 'older-import');
    expect(readIngestDraft(99)).not.toBeNull();
    clearIngestDraft(99, snapshot.jobId);
    expect(readIngestDraft(99)).toBeNull();
  });

  it('ignores corrupt and malformed saved captures', () => {
    localStorage.setItem(ingestDraftKey(99), 'broken json');
    expect(readIngestDraft(99)).toBeNull();
    localStorage.setItem(ingestDraftKey(99), JSON.stringify({ version: 1, ...snapshot, pendingCommit: 'yes' }));
    expect(readIngestDraft(99)).toBeNull();
    expect(storeIngestDraft(null, snapshot)).toBe(false);
  });

  it('reports unavailable storage instead of claiming that a draft was kept', () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota exceeded'); });
    try {
      expect(storeIngestDraft(99, snapshot)).toBe(false);
    } finally {
      storage.mockRestore();
    }
  });
});
