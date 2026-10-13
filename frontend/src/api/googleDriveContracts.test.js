import { describe, expect, it } from 'vitest';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import {
  getGoogleDriveConfig, getGoogleDriveSources, resolveGoogleDriveFile,
  startGoogleDriveIngest, uploadAbbyFileToGoogleDrive,
} from './index';
import config from '../../../contracts/api/fixtures/google-drive-config.json';
import file from '../../../contracts/api/fixtures/google-drive-file.json';
import sources from '../../../contracts/api/fixtures/google-drive-sources-page-1.json';
import secondPage from '../../../contracts/api/fixtures/google-drive-sources-page-2.json';
import emptySources from '../../../contracts/api/fixtures/google-drive-sources-empty.json';
import uploadedFile from '../../../contracts/api/fixtures/google-drive-uploaded-file.json';

describe('Google Drive API contracts', () => {
  it('reads categorized source pages without fetching storage URLs', async () => {
    const request = spyHandler('get', '*/api/auth/google/drive/sources/', sources);
    server.use(request.handler);
    expect(await getGoogleDriveSources('project_photo')).toEqual(sources);
    expect(new URL(request.calls[0].url).searchParams.get('source_type')).toBe('project_photo');
    expect(new URL(request.calls[0].url).searchParams.get('page')).toBe('1');
    const next = spyHandler('get', '*/api/auth/google/drive/sources/', secondPage);
    server.use(next.handler);
    expect(await getGoogleDriveSources('project_photo', 2)).toEqual(secondPage);
    expect(new URL(next.calls[0].url).searchParams.get('page')).toBe('2');
    const empty = spyHandler('get', '*/api/auth/google/drive/sources/', emptySources);
    server.use(empty.handler);
    expect(await getGoogleDriveSources('ingestion_pdf')).toEqual(emptySources);
  });

  it('sends only an Abby record identity and transient token to create a Drive copy', async () => {
    const request = spyHandler('post', '*/api/auth/google/drive/upload/', uploadedFile);
    server.use(request.handler);
    const body = { source_type: 'project_photo', source_id: '301', access_token: 'synthetic-drive-export-token' };
    expect(await uploadAbbyFileToGoogleDrive(body)).toEqual(uploadedFile);
    expect(request.calls).toHaveLength(1);
    expect(request.calls[0].body).toEqual(body);
    expect(request.calls[0].url).not.toContain(body.access_token);
    expect(request.calls[0].body).not.toHaveProperty('url');
  });

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
