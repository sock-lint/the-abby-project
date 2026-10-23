import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import newDraft from '../../../contracts/api/fixtures/project-ai-plan-new.json';
import existingDraft from '../../../contracts/api/fixtures/project-ai-plan-existing.json';
import appliedPlan from '../../../contracts/api/fixtures/project-ai-plan-applied.json';
import homeworkPlan from '../../../contracts/api/fixtures/homework-plan-detail.json';
import homeworkAssignment from '../../../contracts/api/fixtures/homework-with-plan.json';
import homeworkClockDenied from '../../../contracts/api/fixtures/homework-plan-clock-denied.json';
import projectWork from '../../../contracts/api/fixtures/project-work-detail.json';
import projectList from '../../../contracts/api/fixtures/projects-with-homework-plan.json';
import projectIdentity from '../../../contracts/api/fixtures/project-earned-identity.json';
import pulseIdentity from '../../../contracts/api/fixtures/pulse-earned-identity.json';
import dashboardIdentity from '../../../contracts/api/fixtures/dashboard-earned-identity.json';
import { server } from '../test/server';
import {
  applyProjectPlan, clockIn, createProject, draftExistingProjectPlan, draftProjectPlan,
  getDashboard, getHomeworkDetail, getProject, getProjects, getPulse,
} from './index';

describe('reviewable project plans through the shared React API client', () => {
  it('preserves the same saved maker cosmetics through project, pulse and Today reads', async () => {
    server.use(
      http.get('*/api/projects/:projectId/', () => HttpResponse.json(projectIdentity)),
      http.get('*/api/pulse/', () => HttpResponse.json(pulseIdentity)),
      http.get('*/api/dashboard/', () => HttpResponse.json(dashboardIdentity)),
    );
    const project = await getProject(projectIdentity.id);
    const pulse = await getPulse();
    const dashboard = await getDashboard();
    expect(project.maker_signature).toEqual(pulse.identity);
    expect(dashboard.rpg.identity).toEqual(pulse.identity);
    expect(pulse.header.level).toBe(0);
    expect(pulse.identity).toMatchObject({
      id: 702, username: 'project-ai-fixture-child', avatar: 'http://testserver/media/avatars/synthetic-maker.png',
      active_frame: { slug: 'frame-laurel', metadata: { style: 'laurel', color: '#22c55e' } },
      active_title: { slug: 'title-master-crafter', metadata: { title_text: 'Master Crafter' } },
      active_trophy_badge: { name: 'Fixture maker', description: 'Built a thoughtful synthetic project.' },
    });
    expect(project.created_by.id).not.toBe(project.maker_signature.id);
  });

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

  it('reads homework plan identity and its assignment without adding the plan to paid projects', async () => {
    const paths = [];
    server.use(
      http.get('*/api/projects/', ({ request }) => {
        paths.push(new URL(request.url).pathname);
        return HttpResponse.json(projectList);
      }),
      http.get('*/api/projects/:projectId/', ({ request, params }) => {
        paths.push(new URL(request.url).pathname);
        return HttpResponse.json(Number(params.projectId) === homeworkPlan.id ? homeworkPlan : projectWork);
      }),
      http.get('*/api/homework/:assignmentId/', ({ request }) => {
        paths.push(new URL(request.url).pathname);
        return HttpResponse.json(homeworkAssignment);
      }),
    );

    const projects = await getProjects();
    expect(projects).toEqual(projectList);
    expect(projects.results.map((project) => project.id)).toEqual([projectWork.id]);
    const plan = await getProject(homeworkPlan.id);
    expect(plan.is_homework_plan).toBe(true);
    expect(plan.homework_assignment_id).toBe(homeworkAssignment.id);
    expect(plan.steps[0].title).toBe('Outline the presentation');
    expect(await getHomeworkDetail(plan.homework_assignment_id)).toEqual(homeworkAssignment);
    expect(homeworkAssignment.project).toBe(plan.id);
    const work = await getProject(projectWork.id);
    expect(work.is_homework_plan).toBe(false);
    expect(work.homework_assignment_id).toBeNull();
    expect(paths).toEqual(['/api/projects/', '/api/projects/402/', '/api/homework/801/', '/api/projects/401/']);
  });

  it('propagates a homework clock-in rejection without retrying the write', async () => {
    const requests = [];
    server.use(http.post('*/api/clock/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(homeworkClockDenied, { status: 400 });
    }));

    await expect(clockIn(homeworkPlan.id)).rejects.toMatchObject({
      status: 400, response: homeworkClockDenied,
    });
    expect(requests).toEqual([{ action: 'in', project_id: homeworkPlan.id }]);
  });
});
