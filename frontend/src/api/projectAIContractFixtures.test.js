import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import newDraft from '../../../contracts/api/fixtures/project-ai-plan-new.json';
import existingDraft from '../../../contracts/api/fixtures/project-ai-plan-existing.json';
import appliedPlan from '../../../contracts/api/fixtures/project-ai-plan-applied.json';
import { server } from '../test/server';
import { applyProjectPlan, createProject, draftExistingProjectPlan, draftProjectPlan } from './index';

describe('reviewable project plans through the shared React API client', () => {
  it('drafts a new project from its description and creates it with reviewed plan content', async () => {
    const requests = [];
    server.use(
      http.post('*/api/projects/plan/', async ({ request }) => {
        requests.push({ path: new URL(request.url).pathname, body: await request.json() });
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(newDraft);
      }),
      http.post('*/api/projects/', async ({ request }) => {
        requests.push({ path: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json({ id: 402 }, { status: 201 });
      }),
    );
    const request = {
      title: 'Build a bird feeder', description: 'Make a simple feeder together.',
      difficulty: 2, guidance: 'Keep the steps short.',
    };
    const draft = await draftProjectPlan(request);
    expect(draft).toEqual(newDraft);
    expect(draft.plan_version).toBeNull();
    expect(draft.plan.steps.map((step) => step.milestone_index)).toEqual([0, null]);
    const reviewed = structuredClone(draft.plan);
    reviewed.materials[0].estimated_cost = '6.25';
    const creation = { title: 'Our reviewed bird feeder', difficulty: 2, assigned_to: 702, plan_create: reviewed };
    expect(await createProject(creation)).toEqual({ id: 402 });
    expect(requests).toEqual([
      { path: '/api/projects/plan/', body: request },
      { path: '/api/projects/', body: creation },
    ]);
    expect(newDraft.plan.materials[0].estimated_cost).toBe('0.00');
  });

  it('passes the existing project version back with a reviewed plan and preserves confirmed application', async () => {
    const requests = [];
    server.use(
      http.post('*/api/projects/:projectId/plan/', async ({ request, params }) => {
        requests.push({ path: new URL(request.url).pathname, id: params.projectId, body: await request.json() });
        return HttpResponse.json(existingDraft);
      }),
      http.post('*/api/projects/:projectId/apply-plan/', async ({ request, params }) => {
        requests.push({ path: new URL(request.url).pathname, id: params.projectId, body: await request.json() });
        return HttpResponse.json(appliedPlan);
      }),
    );
    const guidance = { guidance: 'Keep the existing sketch.' };
    const draft = await draftExistingProjectPlan(401, guidance);
    expect(draft).toEqual(existingDraft);
    expect(draft.plan_version).toMatch(/^[a-f0-9]{64}$/);
    const reviewed = structuredClone(draft.plan);
    reviewed.materials[0].estimated_cost = '6.25';
    const application = { plan: reviewed, plan_version: draft.plan_version };
    expect(await applyProjectPlan(401, application)).toEqual(appliedPlan);
    expect(requests).toEqual([
      { path: '/api/projects/401/plan/', id: '401', body: guidance },
      { path: '/api/projects/401/apply-plan/', id: '401', body: application },
    ]);
  });

  it('keeps a stale-plan rejection available to the caller without replaying the write', async () => {
    const requests = [];
    const rejection = { error: 'The project changed. Generate a fresh plan before applying it.' };
    server.use(http.post('*/api/projects/:projectId/apply-plan/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(rejection, { status: 409 });
    }));
    const payload = { plan: existingDraft.plan, plan_version: existingDraft.plan_version };
    await expect(applyProjectPlan(401, payload)).rejects.toMatchObject({ status: 409, response: rejection });
    expect(requests).toEqual([payload]);
  });
});
