export const PLAN_LIMITS = { milestones: 10, steps: 40, materials: 40, title: 200, description: 4000 };

function text(value, label, limit, required = false) {
  if (typeof value !== 'string' || value.length > limit || (required && !value.trim())) {
    throw new Error(`${label} ${required ? 'needs text and' : 'must be text and'} must be at most ${limit} characters.`);
  }
  return value.trim();
}

// Validate generated responses and reviewed edits, copying only supported plan
// fields. Model output can never carry project status, payments or progress.
export function cleanProjectPlan(value, { wire = false } = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('The AI response did not contain a usable plan. Try again.');
  for (const key of ['milestones', 'steps', 'materials']) {
    if (!Array.isArray(value[key]) || value[key].length > PLAN_LIMITS[key]) {
      throw new Error(`A plan can include at most ${PLAN_LIMITS[key]} ${key}.`);
    }
  }
  if (value.steps.length === 0) throw new Error('Keep at least one step in the reviewed plan.');
  const milestones = value.milestones.map((item, index) => ({
    title: text(item?.title, `Milestone ${index + 1} title`, PLAN_LIMITS.title, true),
    description: text(item?.description, `Milestone ${index + 1} description`, PLAN_LIMITS.description),
  }));
  const steps = value.steps.map((item, index) => {
    const milestone = item?.milestone_index;
    if (milestone !== null && (!Number.isInteger(milestone) || milestone < 0 || milestone >= milestones.length)) {
      throw new Error(`Choose an available milestone for step ${index + 1}.`);
    }
    return {
      title: text(item?.title, `Step ${index + 1} title`, PLAN_LIMITS.title, true),
      description: text(item?.description, `Step ${index + 1} description`, PLAN_LIMITS.description),
      milestone_index: milestone,
    };
  });
  const materials = value.materials.map((item, index) => {
    const cost = item?.estimated_cost;
    if (typeof cost !== 'string' || !(wire ? /^\d+\.\d{2}$/ : /^\d+(?:\.\d{1,2})?$/).test(cost)) {
      throw new Error(`Enter a nonnegative estimated cost with up to two decimal places for material ${index + 1}.`);
    }
    const [whole, fraction = ''] = cost.split('.');
    if (whole.replace(/^0+(?=\d)/, '').length > 6) {
      throw new Error(`Material ${index + 1} estimated cost must be at most 999999.99.`);
    }
    return {
      name: text(item?.name, `Material ${index + 1} name`, PLAN_LIMITS.title, true),
      description: text(item?.description, `Material ${index + 1} description`, PLAN_LIMITS.description),
      estimated_cost: `${whole.replace(/^0+(?=\d)/, '')}.${fraction.padEnd(2, '0')}`,
    };
  });
  return { milestones, steps, materials };
}

export function readProjectPlanResponse(response, existing) {
  const version = response?.plan_version;
  if (existing ? typeof version !== 'string' || !/^[a-f0-9]{64}$/.test(version) : version !== null) {
    throw new Error('The AI response could not be verified. Try again.');
  }
  return { plan: cleanProjectPlan(response.plan, { wire: true }), plan_version: version };
}

export function removePlanMilestone(plan, index) {
  return {
    ...plan,
    milestones: plan.milestones.filter((_, current) => current !== index),
    steps: plan.steps.map((step) => ({ ...step, milestone_index: step.milestone_index === index
      ? null : step.milestone_index > index ? step.milestone_index - 1 : step.milestone_index })),
  };
}
