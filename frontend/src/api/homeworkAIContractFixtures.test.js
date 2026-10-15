import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import disconnectedSettings from '../../../contracts/api/fixtures/homework-ai-default.json';
import openaiSettings from '../../../contracts/api/fixtures/homework-ai-openai.json';
import anthropicSettings from '../../../contracts/api/fixtures/homework-ai-anthropic.json';
import { server } from '../test/server';
import { deleteHomeworkAISettings, getHomeworkAISettings, updateHomeworkAISettings } from './index';

describe('homework AI settings through the shared React API client', () => {
  it.each([disconnectedSettings, openaiSettings, anthropicSettings])('reads $provider settings without exposing a saved credential', async (settings) => {
    const requests = [];
    server.use(http.get('*/api/homework/ai-settings/', ({ request }) => {
      requests.push({ path: new URL(request.url).pathname, token: request.headers.get('Authorization') });
      return HttpResponse.json(settings);
    }));
    expect(await getHomeworkAISettings()).toEqual(settings);
    expect(requests).toEqual([{ path: '/api/homework/ai-settings/', token: 'Token test-session' }]);
    expect(Object.keys(settings).sort()).toEqual(['has_api_key', 'model', 'provider']);
  });

  it.each([openaiSettings, anthropicSettings])('saves $provider and can update its model without resending the saved key', async (settings) => {
    const requests = [];
    server.use(http.put('*/api/homework/ai-settings/', async ({ request }) => {
      requests.push({
        path: new URL(request.url).pathname,
        token: request.headers.get('Authorization'),
        body: await request.json(),
      });
      return HttpResponse.json(settings);
    }));
    const selection = { provider: settings.provider, model: settings.model };
    const keyedSelection = { ...selection, api_key: 'synthetic-provider-key' };
    expect(await updateHomeworkAISettings(keyedSelection)).toEqual(settings);
    expect(await updateHomeworkAISettings(selection)).toEqual(settings);
    expect(requests).toEqual([keyedSelection, selection].map((body) => ({
      path: '/api/homework/ai-settings/', token: 'Token test-session', body,
    })));
  });

  it('removes the connection with an empty DELETE and returns the disconnected sentinel', async () => {
    const requests = [];
    server.use(http.delete('*/api/homework/ai-settings/', async ({ request }) => {
      requests.push({ path: new URL(request.url).pathname, body: await request.text() });
      return HttpResponse.json(disconnectedSettings);
    }));
    expect(await deleteHomeworkAISettings()).toEqual(disconnectedSettings);
    expect(requests).toEqual([{ path: '/api/homework/ai-settings/', body: '' }]);
  });
});
