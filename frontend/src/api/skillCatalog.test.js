import { beforeEach, describe, expect, it } from 'vitest';
import { waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getAllSkills, getSkillCatalog } from './index';

const subjects = [
  { id: 1, name: 'Shop Basics', category: 7 },
  { id: 2, name: 'Advanced Technique', category: 7 },
];
const skills = [
  { id: 10, name: 'Hand Tools', category: 7, subject: 1 },
  { id: 11, name: 'Measuring & Marking', category: 7, subject: 1 },
  { id: 12, name: 'Joinery', category: 7, subject: 2 },
];

beforeEach(() => {
  localStorage.removeItem('abby_auth_token');
});

describe('getAllSkills', () => {
  it('binds a paginated picker read to its captured token and stops when its owner aborts', async () => {
    const controller = new AbortController();
    const requests = [];
    let finish;
    server.use(http.get('*/api/skills/', ({ request }) => {
      requests.push({ authorization: request.headers.get('Authorization'), page: new URL(request.url).searchParams.get('page') });
      return new Promise((resolve) => { finish = () => resolve(HttpResponse.json({ next: '/api/skills/?page=2', results: skills.slice(0, 1) })); });
    }));
    localStorage.setItem('abby_auth_token', 'original-session');
    const pending = getAllSkills({ token: 'original-session', signal: controller.signal });
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    await waitFor(() => expect(requests).toHaveLength(1));
    localStorage.setItem('abby_auth_token', 'replacement-session');
    controller.abort();
    finish();
    await rejected;
    expect(requests).toEqual([{ authorization: 'Token original-session', page: null }]);
  });

  it('loads every skill page without requesting unused subjects', async () => {
    const paths = [];
    let subjectRequests = 0;
    server.use(
      http.get('*/api/subjects/', () => {
        subjectRequests += 1;
        return HttpResponse.json([]);
      }),
      http.get('*/api/skills/', ({ request }) => {
        const url = new URL(request.url);
        paths.push(url.pathname + url.searchParams.get('page'));
        return HttpResponse.json(url.searchParams.has('page')
          ? { next: null, results: skills.slice(1) }
          : { next: 'https://catalog-proxy.example/api/skills/?page=2', results: skills.slice(0, 1) });
      }),
    );

    await expect(getAllSkills()).resolves.toEqual(skills);
    expect(paths).toEqual(['/api/skills/null', '/api/skills/2']);
    expect(subjectRequests).toBe(0);
  });
});

describe('getSkillCatalog', () => {
  it('starts both lists independently and accepts raw arrays', async () => {
    const started = [];
    let releaseSubjects;
    const subjectsReady = new Promise((resolve) => { releaseSubjects = resolve; });
    server.use(
      http.get('*/api/subjects/', async () => {
        started.push('subjects');
        await subjectsReady;
        return HttpResponse.json(subjects);
      }),
      http.get('*/api/skills/', () => {
        started.push('skills');
        return HttpResponse.json(skills);
      }),
    );

    const pending = getSkillCatalog();
    await waitFor(() => expect(started).toEqual(expect.arrayContaining(['subjects', 'skills'])));
    releaseSubjects();
    await expect(pending).resolves.toEqual({ subjects, skills });
  });

  it('collects every page through the same API origin with the current read namespace', async () => {
    const requests = [];
    server.use(
      http.get('*/api/subjects/', ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        return HttpResponse.json(url.searchParams.get('page') === '2'
          ? { count: 2, next: null, results: [subjects[1]] }
          : {
            count: 2,
            next: 'https://catalog-proxy.example/api/subjects/?page=2&_abby_session=echoed-read-key',
            results: [subjects[0]],
          });
      }),
      http.get('*/api/skills/', ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        const page = Number(url.searchParams.get('page') || 1);
        return HttpResponse.json({
          count: 3,
          next: page < 3 ? `/api/skills/?page=${page + 1}&_abby_session=echoed-read-key` : null,
          results: [skills[page - 1]],
        });
      }),
    );

    await expect(getSkillCatalog()).resolves.toEqual({ subjects, skills });
    expect(requests).toHaveLength(5);
    expect(requests.every((url) => url.origin === window.location.origin)).toBe(true);
    const namespaces = requests.map((url) => url.searchParams.get('_abby_session'));
    expect(namespaces.every(Boolean)).toBe(true);
    expect(new Set(namespaces).size).toBe(1);
    expect(namespaces).not.toContain('echoed-read-key');
    expect(requests.filter((url) => url.pathname === '/api/skills/')
      .map((url) => url.searchParams.get('page'))).toEqual([null, '2', '3']);
  });

  it.each([
    ['null', null],
    ['missing results', { next: null }],
    ['non-array results', { results: {}, next: null }],
    ['missing next', { results: [] }],
    ['non-string next', { results: [], next: 2 }],
    ['empty next', { results: [], next: '' }],
  ])('rejects a later page with %s instead of returning an incomplete catalog', async (_label, malformedPage) => {
    server.use(
      http.get('*/api/subjects/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.has('page')
          ? malformedPage
          : { results: [subjects[0]], next: '/api/subjects/?page=2' },
      )),
      http.get('*/api/skills/', () => HttpResponse.json(skills)),
    );

    await expect(getSkillCatalog()).rejects.toThrow('Unexpected skill catalog response.');
  });

  it.each([
    '/api/skills/?page=2',
    '/api/subjects/1/?page=2',
    '/api/chronicle/?page=2',
    'javascript:invalid',
    'http://[invalid',
    '/api/subjects/?page=2#fragment',
  ])('rejects a continuation outside its list route: %s', async (next) => {
    let subjectRequests = 0;
    server.use(
      http.get('*/api/subjects/', () => {
        subjectRequests += 1;
        return HttpResponse.json({ results: subjects, next });
      }),
      http.get('*/api/skills/', () => HttpResponse.json(skills)),
    );

    await expect(getSkillCatalog()).rejects.toThrow('Unexpected skill catalog pagination link.');
    expect(subjectRequests).toBe(1);
  });

  it.each([
    ['the initial page', '/api/subjects/?_abby_session=another-read-key'],
    ['the second page with reordered query parameters', '/api/subjects/?sort=name&page=2&_abby_session=another-read-key'],
  ])('rejects a cycle back to %s before fetching it again', async (_label, repeatedPage) => {
    let subjectRequests = 0;
    server.use(
      http.get('*/api/subjects/', ({ request }) => {
        subjectRequests += 1;
        const page = new URL(request.url).searchParams.get('page');
        return HttpResponse.json({
          results: [page ? subjects[1] : subjects[0]],
          next: page ? repeatedPage : '/api/subjects/?page=2&sort=name',
        });
      }),
      http.get('*/api/skills/', () => HttpResponse.json(skills)),
    );

    await expect(getSkillCatalog()).rejects.toThrow('Repeated skill catalog page.');
    expect(subjectRequests).toBe(2);
  });
});
