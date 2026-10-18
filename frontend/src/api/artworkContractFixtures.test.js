import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getAchievementsSummary, getBadges, getCategories, getCharacterProfile, getDashboard,
  getSkillCatalog, getSkillProgress, getSkillTree } from './index';
import categories from '../../../contracts/api/fixtures/artwork-categories.json';
import subjects from '../../../contracts/api/fixtures/artwork-subjects.json';
import skills from '../../../contracts/api/fixtures/artwork-skills.json';
import tree from '../../../contracts/api/fixtures/artwork-tree.json';
import progress from '../../../contracts/api/fixtures/artwork-progress.json';
import badges from '../../../contracts/api/fixtures/artwork-badges.json';
import summary from '../../../contracts/api/fixtures/artwork-summary.json';
import character from '../../../contracts/api/fixtures/artwork-character.json';
import dashboard from '../../../contracts/api/fixtures/artwork-dashboard.json';

describe('Artwork API response contracts', () => {
  it('preserves scoped category, subject and skill references through the paginated skill catalog and progress tree', async () => {
    server.use(
      http.get('*/api/categories/', () => HttpResponse.json(categories)),
      http.get('*/api/subjects/', () => HttpResponse.json(subjects)),
      http.get('*/api/skills/', () => HttpResponse.json(skills)),
      http.get('*/api/skills/tree/101/', () => HttpResponse.json(tree)),
    );
    expect(await getCategories()).toEqual(categories);
    const catalog = await getSkillCatalog();
    expect(catalog.subjects).toEqual(subjects.results);
    expect(catalog.skills).toEqual(skills.results);
    expect(catalog.skills.filter((skill) => skill.name === 'Python').map((skill) => skill.catalog_icon))
      .toEqual(['skill-coding-python', null]);
    expect(catalog.subjects.filter((subject) => subject.name === 'Languages & Apps').map((subject) => subject.catalog_icon))
      .toEqual(['subject-coding-languages-apps', null]);
    expect(await getSkillTree(101)).toEqual(tree);
    expect(tree.subjects[0].skills[0]).toMatchObject({ catalog_icon: 'skill-coding-python', xp_points: 150, level: 1, unlocked: true });
  });

  it('retains badge art, custom glyph fallbacks and flattened progress and dashboard identities without changing saved awards', async () => {
    server.use(
      http.get('*/api/badges/', () => HttpResponse.json(badges)),
      http.get('*/api/skill-progress/', () => HttpResponse.json(progress)),
      http.get('*/api/achievements/summary/', () => HttpResponse.json(summary)),
      http.get('*/api/character/', () => HttpResponse.json(character)),
      http.get('*/api/dashboard/', () => HttpResponse.json(dashboard)),
    );
    expect(await getBadges()).toEqual(badges);
    expect(badges.results[1]).toMatchObject({ name: '25-Hour Club', icon: 'CUSTOM BADGE', catalog_icon: null });
    expect(await getSkillProgress()).toEqual(progress);
    expect(progress.results[0].skill_catalog_icon).toBe('skill-coding-python');
    expect(await getAchievementsSummary()).toEqual(summary);
    expect(summary.badges_earned[0].badge.catalog_icon).toBe('badge-10-hour-club');
    expect(await getCharacterProfile()).toEqual(character);
    expect(character.active_trophy_badge.catalog_icon).toBe('badge-10-hour-club');
    expect(await getDashboard()).toEqual(dashboard);
    expect(dashboard.recent_badges[0].badge__catalog_icon).toBe('badge-10-hour-club');
  });
});
