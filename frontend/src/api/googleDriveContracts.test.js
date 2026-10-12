import { describe, expect, it } from 'vitest';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { getGoogleDriveConfig, resolveGoogleDriveFile, startGoogleDriveIngest } from './index';
import config from '../../../contracts/api/fixtures/google-drive-config.json';
import file from '../../../contracts/api/fixtures/google-drive-file.json';

describe('Google Drive API contracts', () => {
  it('reads public Picker configuration from the backend fixture', async () => {
    const request = spyHandler('get', '*/api/auth/google/drive/config/', config);
    server.use(request.handler);
    expect(await getGoogleDriveConfig()).toEqual(config);
    expect(request.calls).toHaveLength(1);
  });

  it('resolves a selected PDF into verified resource fields without a token in its URL', async () => {
    const request = spyHandler('post', '*/api/auth/google/drive/file/', file);
    server.use(request.handler);
    const selection = { file_id: file.id, access_token: 'synthetic-drive-token' };
    expect(await resolveGoogleDriveFile(selection)).toEqual(file);
    expect(request.calls[0].body).toEqual(selection);
    expect(request.calls[0].url).not.toContain(selection.access_token);
  });

  it('starts a Drive PDF job using the existing ingestion response shape', async () => {
    const job = { id: 'synthetic-job', source_type: 'pdf', status: 'pending', result_json: null };
    const request = spyHandler('post', '*/api/projects/ingest/google-drive/', job);
    server.use(request.handler);
    const selection = { file_id: file.id, access_token: 'synthetic-drive-token', resource_key: 'synthetic-resource-key' };
    expect(await startGoogleDriveIngest(selection)).toEqual(job);
    expect(request.calls[0].body).toEqual(selection);
    expect(request.calls[0].url).toMatch(/\/api\/projects\/ingest\/google-drive\/$/);
  });
});
