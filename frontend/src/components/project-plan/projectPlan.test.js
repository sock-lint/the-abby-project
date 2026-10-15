import { describe, expect, it } from 'vitest';
import { cleanProjectPlan, readProjectPlanResponse, removePlanMilestone } from './projectPlan';

const plan = {
  milestones: [{ title: 'Prepare', description: '' }, { title: 'Build', description: '' }],
  steps: [{ title: 'Measure', description: '', milestone_index: 0 }, { title: 'Assemble', description: '', milestone_index: 1 }],
  materials: [{ name: 'Wood', description: '', estimated_cost: '5.00' }],
};

describe('reviewed project plan validation', () => {
  it('requires at least one reviewed step', () => {
    expect(() => cleanProjectPlan({ ...plan, steps: [] })).toThrow(/at least one step/i);
  });

  it('bounds estimated costs to the API decimal range', () => {
    expect(() => cleanProjectPlan({ ...plan, materials: [{ ...plan.materials[0], estimated_cost: '1000000.00' }] })).toThrow(/999999.99/);
    expect(cleanProjectPlan({ ...plan, materials: [{ ...plan.materials[0], estimated_cost: '999999.99' }] }).materials[0].estimated_cost).toBe('999999.99');
  });

  it('copies supported review fields and formats an edited cost without floating point rounding', () => {
    expect(cleanProjectPlan({ ...plan, status: 'completed', bonus_amount: '99',
      materials: [{ ...plan.materials[0], estimated_cost: '12.5', is_purchased: true }],
    })).toEqual({ ...plan, materials: [{ ...plan.materials[0], estimated_cost: '12.50' }] });
  });

  it('rejects malformed versions, oversized lists, invalid links and oversized text', () => {
    for (const malformed of [
      { ...plan, milestones: Array.from({ length: 11 }, () => plan.milestones[0]) },
      { ...plan, steps: Array.from({ length: 41 }, () => plan.steps[0]) },
      { ...plan, materials: Array.from({ length: 41 }, () => plan.materials[0]) },
      { ...plan, steps: [{ ...plan.steps[0], milestone_index: 2 }] },
      { ...plan, steps: [{ ...plan.steps[0], title: 'x'.repeat(201) }] },
      { ...plan, materials: [{ ...plan.materials[0], description: 'x'.repeat(4001) }] },
      { ...plan, materials: [{ ...plan.materials[0], estimated_cost: '-1.00' }] },
    ]) expect(() => cleanProjectPlan(malformed)).toThrow();
    expect(() => readProjectPlanResponse({ plan, plan_version: null }, true)).toThrow(/verified/);
    expect(() => readProjectPlanResponse({ plan, plan_version: 'a'.repeat(64) }, false)).toThrow(/verified/);
    expect(readProjectPlanResponse({ plan, plan_version: 'a'.repeat(64) }, true).plan).toEqual(plan);
    expect(readProjectPlanResponse({ plan, plan_version: null }, false).plan).toEqual(plan);
  });

  it('removes a milestone while detaching its steps and shifting later links', () => {
    expect(removePlanMilestone(plan, 0)).toEqual({ ...plan, milestones: [plan.milestones[1]],
      steps: [{ ...plan.steps[0], milestone_index: null }, { ...plan.steps[1], milestone_index: 0 }],
    });
  });
});
