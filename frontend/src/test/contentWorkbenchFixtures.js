export const draftId = 'd0000000-0000-4000-8000-000000000001';
export const values = {
  name: 'Forest reading', description: 'Read across five days.', icon: '🌲', sprite_key: '',
  quest_type: 'collection', target_value: 5, duration_days: 14, coin_reward: 10, xp_reward: 20,
  is_repeatable: false, trigger_filter: { allowed_triggers: ['reading_logged'] }, required_badge: null,
  reward_items: [{ item_id: 7, quantity: 1 }], skill_tags: [{ skill_id: 4, xp_weight: 1 }],
};
export const itemValues = { name: 'Forest snack', description: 'A companion treat.', icon: '🍓', sprite_key: '', rarity: 'common', coin_value: 2, metadata: { growth: 5 } };
export const quest = { ...values, values, id: 9, editable: true };
export const item = { ...itemValues, values: itemValues, slug: 'forest-snack', item_type: 'food', id: 7, editable: true, runtime_available: true,
  used_by: { quests: [{ id: 9, name: values.name, quantity: 1 }], drops: [{ id: 3, trigger_type: 'reading_logged', weight: 1, min_level: 1 }], shop_offers: [{ id: 5, name: 'Snack offer', cost_coins: 12, is_active: true }] } };
export const config = { horizon_days: 90, trials: 2, seed: 42, active_days_per_week: 5, reading_minutes: 10, journal_per_day: true };
export const draft = { id: draftId, name: 'Forest balance', revision: 1, changes: [], published_at: null, preview: null };
export const change = { section: 'quests', key: 'quests-9', object_id: 9, values: { ...values, coin_reward: 25 } };
export const plan = { preview_id: 'plan-1', content_digest: 'abc123', changes: [{ object: 'quests:9', action: 'update', before: values, after: change.values }], audits: { findings: [{ severity: 'warning', code: 'unsupported_reward', detail: 'Some retained rewards have no new acquisition path.' }], incomplete: false } };
export const saved = { ...draft, revision: 2, changes: [change] };
export const previewed = { ...saved, preview: plan };
export const metadata = {
  catalog: { items: [item], quests: [quest], skills: [{ id: 4, name: 'Reading', category_name: 'Learning' }], badges: [{ id: 6, name: 'First page' }] },
  rules: { item_types: ['food', 'coin_pouch', 'consumable'], rarities: ['common', 'rare'], triggers: ['reading_logged', 'chore_complete'] },
  drafts: [draft], audits: { findings: [] },
  simulation: { defaults: config, limits: { horizon_days: { choices: [30, 90] }, trials: { min: 1, max: 20 }, seed: { min: 0, max: 10000 } }, presets: [] },
};
export const report = {
  config, engine_version: 'test-v1', rules_fingerprint: 'rules-fixture', catalog: { fingerprint: 'catalog-fixture' },
  summary: { finite_content_total: 4, finite_remaining_p50: 3, longest_novelty_gap_p50: 20, expired_oneoff_challenges_p50: 0 },
  milestones: [{ key: 'pet', label: 'First companion', completion_rate: 0, p50_days: null }],
  trace: [{ day: 90, coins_p50: 100, total_xp_p50: 200 }],
  coverage: { modeled: ['Reading activity'], excluded: ['Private family shop decisions'], assumptions: ['Approvals complete'] },
  flows: { sources: [{ source: 'reading_logged', coins: 20, xp: 100, items: 3 }] },
};
export const comparison = { preview_id: plan.preview_id, revision: saved.revision, baseline: report, proposed: { ...report, catalog: { fingerprint: 'draft-catalog' }, trace: [{ day: 90, coins_p50: 150, total_xp_p50: 200 }] } };
