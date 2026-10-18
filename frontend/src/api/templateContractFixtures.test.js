import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import template from '../../../contracts/api/fixtures/template-skills.json';
import { server } from '../test/server';
import { getTemplate } from './index';

describe('template learning tags through the React API client', () => {
  it('preserves weighted project XP and fixed milestone XP in the real server response', async () => {
    server.use(http.get('*/api/templates/1/', () => HttpResponse.json(template)));
    const saved = await getTemplate(1);
    expect(saved).toEqual(template);
    expect(saved.skill_tags).toEqual([{ skill_id: 22, xp_weight: 3 }]);
    expect(saved.milestones[0].skill_tags).toEqual([{ skill_id: 22, xp_amount: 27 }]);
  });
});
