import { http, HttpResponse } from 'msw';

// Permissive defaults: every /api endpoint returns an empty-but-valid shape
// so a test that mounts a page without caring about its network state still
// renders past the loading spinner. Per-test `server.use(...)` overrides the
// specific routes that matter for each case.

const empty = () => HttpResponse.json([]);
const ok = () => HttpResponse.json({ ok: true });
const nullBody = () => new HttpResponse(null, { status: 204 });

// Order matters inside MSW — more specific paths first.
export const handlers = [
  // Auth
  http.post('*/api/auth/', ok),
  http.get('*/api/auth/me/', () =>
    HttpResponse.json({ detail: 'Authentication credentials were not provided.' }, { status: 401 }),
  ),
  http.patch('*/api/auth/me/', ok),
  http.get('*/api/auth/google/', () => HttpResponse.json({ authorization_url: '' })),
  http.get('*/api/auth/google/login/', () => HttpResponse.json({ authorization_url: '' })),
  http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
  http.delete('*/api/auth/google/account/', nullBody),
  http.get('*/api/auth/google/calendar/', () => HttpResponse.json({ sync_enabled: false })),
  http.patch('*/api/auth/google/calendar/', ok),
  http.post('*/api/auth/google/calendar/sync/', ok),

  // Dashboard / Balance
  http.get('*/api/dashboard/', () => HttpResponse.json({ next_actions: [] })),
  http.get('*/api/balance/', () => HttpResponse.json({ balance: 0, breakdown: {} })),

  // Projects
  http.get('*/api/projects/', empty),
  http.post('*/api/projects/', ok),
  http.get('*/api/projects/suggestions/', empty),
  http.get(/\/api\/projects\/\d+\/$/, () => HttpResponse.json({ id: 1 })),
  http.patch(/\/api\/projects\/\d+\/$/, ok),
  http.post(/\/api\/projects\/\d+\/(activate|submit|approve|request-changes)\/$/, ok),

  // Ingest
  http.post('*/api/projects/ingest/', ok),
  http.get(/\/api\/projects\/ingest\/[^/]+\/$/, () =>
    HttpResponse.json({ status: 'pending', result_json: {} }),
  ),
  http.patch(/\/api\/projects\/ingest\/[^/]+\/$/, ok),
  http.post(/\/api\/projects\/ingest\/[^/]+\/commit\/$/, ok),
  http.delete(/\/api\/projects\/ingest\/[^/]+\/$/, nullBody),

  // Milestones, Steps, Resources, Materials (project-scoped)
  http.get(/\/api\/projects\/\d+\/(milestones|steps|resources|materials|collaborators)\//, empty),
  http.post(/\/api\/projects\/\d+\/(milestones|steps|resources|materials|collaborators)\//, ok),
  http.patch(/\/api\/projects\/\d+\/(milestones|steps|resources|materials)\/\d+\/$/, ok),
  http.delete(/\/api\/projects\/\d+\/(milestones|steps|resources|materials)\/\d+\/$/, nullBody),
  http.post(/\/api\/projects\/\d+\/milestones\/\d+\/complete\/$/, ok),
  http.post(/\/api\/projects\/\d+\/steps\/\d+\/(complete|uncomplete)\/$/, ok),
  http.post(/\/api\/projects\/\d+\/steps\/reorder\/$/, ok),
  http.post(/\/api\/projects\/\d+\/materials\/\d+\/mark-purchased\/$/, ok),
  http.get(/\/api\/projects\/\d+\/qr\/$/, () => new HttpResponse('png-bytes')),

  // Clock / Time Entries / Timecards
  http.get('*/api/clock/', () => HttpResponse.json({ active: null })),
  http.post('*/api/clock/', ok),
  http.get('*/api/time-entries/', empty),
  http.post(/\/api\/time-entries\/\d+\/void\/$/, ok),
  http.get('*/api/timecards/', empty),
  http.get(/\/api\/timecards\/\d+\/$/, () => HttpResponse.json({ id: 1, entries: [] })),
  http.post(/\/api\/timecards\/\d+\/(approve|dispute|mark-paid)\/$/, ok),

  // Payments
  http.get('*/api/payments/', empty),
  http.post('*/api/payments/payout/', ok),
  http.post('*/api/payments/adjust/', ok),

  // Achievements
  http.get('*/api/badges/', empty),
  http.post('*/api/badges/', ok),
  http.patch(/\/api\/badges\/\d+\/$/, ok),
  http.delete(/\/api\/badges\/\d+\/$/, nullBody),
  http.get('*/api/badges/earned/', empty),
  http.get('*/api/subjects/', empty),
  http.post('*/api/subjects/', ok),
  http.patch(/\/api\/subjects\/\d+\/$/, ok),
  http.delete(/\/api\/subjects\/\d+\/$/, nullBody),
  http.get('*/api/skills/', empty),
  http.post('*/api/skills/', ok),
  http.patch(/\/api\/skills\/\d+\/$/, ok),
  http.delete(/\/api\/skills\/\d+\/$/, nullBody),
  http.get(/\/api\/skills\/tree\/\d+\/$/, () =>
    HttpResponse.json({ subjects: [], skills: [] }),
  ),
  http.get('*/api/skill-progress/', empty),
  http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: 0 })),

  // Rewards / Coins
  http.get('*/api/rewards/', empty),
  http.post('*/api/rewards/', ok),
  http.patch(/\/api\/rewards\/\d+\/$/, ok),
  http.delete(/\/api\/rewards\/\d+\/$/, nullBody),
  http.post(/\/api\/rewards\/\d+\/redeem\/$/, ok),
  http.get('*/api/redemptions/', empty),
  http.post(/\/api\/redemptions\/\d+\/(approve|reject)\/$/, ok),
  http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
  http.post('*/api/coins/adjust/', ok),
  http.get('*/api/coins/exchange/rate/', () =>
    HttpResponse.json({ coins_per_dollar: 10 }),
  ),
  http.post('*/api/coins/exchange/', ok),
  http.get('*/api/coins/exchange/list/', empty),
  http.post(/\/api\/coins\/exchange\/\d+\/(approve|reject)\/$/, ok),

  // Portfolio / Photos
  http.get('*/api/portfolio/', () => HttpResponse.json({ projects: [] })),
  http.get('*/api/photos/', empty),
  http.post('*/api/photos/', ok),

  // Categories
  http.get('*/api/categories/', empty),
  http.post('*/api/categories/', ok),
  http.patch(/\/api\/categories\/\d+\/$/, ok),
  http.delete(/\/api\/categories\/\d+\/$/, nullBody),

  // Notifications
  http.get('*/api/notifications/', empty),
  http.get('*/api/notifications/unread_count/', () =>
    HttpResponse.json({ unread: 0 }),
  ),
  http.post('*/api/notifications/mark_all_read/', ok),
  http.post(/\/api\/notifications\/\d+\/mark_read\/$/, ok),

  // Instructables
  http.get('*/api/instructables/preview/', () =>
    HttpResponse.json({ title: '', description: '' }),
  ),

  // Templates
  http.get('*/api/templates/', empty),
  http.get(/\/api\/templates\/\d+\/$/, () => HttpResponse.json({ id: 1 })),
  http.patch(/\/api\/templates\/\d+\/$/, ok),
  http.delete(/\/api\/templates\/\d+\/$/, nullBody),
  http.post(/\/api\/templates\/\d+\/create-project\/$/, ok),
  http.post('*/api/templates/from-project/', ok),

  // Savings Goals
  http.get('*/api/savings-goals/', empty),
  http.post('*/api/savings-goals/', ok),
  http.delete(/\/api\/savings-goals\/\d+\/$/, nullBody),
  http.post(/\/api\/savings-goals\/\d+\/update_amount\/$/, ok),

  // Children
  http.get('*/api/children/', empty),
  http.patch(/\/api\/children\/\d+\/$/, ok),

  // Chores
  http.get('*/api/chores/', empty),
  http.post('*/api/chores/', ok),
  http.get(/\/api\/chores\/\d+\/$/, () => HttpResponse.json({ id: 1 })),
  http.patch(/\/api\/chores\/\d+\/$/, ok),
  http.delete(/\/api\/chores\/\d+\/$/, nullBody),
  http.post(/\/api\/chores\/\d+\/complete\/$/, ok),
  http.get('*/api/chore-completions/', empty),
  http.post(/\/api\/chore-completions\/\d+\/(approve|reject)\/$/, ok),

  // Greenlight
  http.post('*/api/greenlight/import/', ok),

  // Homework
  http.get('*/api/homework/dashboard/', () => HttpResponse.json({ assignments: [] })),
  http.get('*/api/homework/', empty),
  http.post('*/api/homework/', ok),
  http.get(/\/api\/homework\/\d+\/$/, () => HttpResponse.json({ id: 1 })),
  http.patch(/\/api\/homework\/\d+\/$/, ok),
  http.delete(/\/api\/homework\/\d+\/$/, nullBody),
  http.post(/\/api\/homework\/\d+\/submit\/$/, ok),
  http.post(/\/api\/homework\/\d+\/save-template\/$/, ok),
  http.post(/\/api\/homework\/\d+\/plan\/$/, ok),
  http.get('*/api/homework-submissions/', empty),
  http.post(/\/api\/homework-submissions\/\d+\/(approve|reject)\/$/, ok),
  http.get('*/api/homework-templates/', empty),
  http.post('*/api/homework-templates/', ok),
  http.delete(/\/api\/homework-templates\/\d+\/$/, nullBody),
  http.post(/\/api\/homework-templates\/\d+\/create-assignment\/$/, ok),

  // RPG
  http.get('*/api/character/', () => HttpResponse.json({ login_streak: 0 })),
  http.post('*/api/character/equip/', ok),
  http.post('*/api/character/unequip/', ok),
  http.get('*/api/streaks/', () => HttpResponse.json({ streak: 0 })),
  http.get('*/api/habits/', empty),
  http.post('*/api/habits/', ok),
  http.patch(/\/api\/habits\/\d+\/$/, ok),
  http.delete(/\/api\/habits\/\d+\/$/, nullBody),
  http.post(/\/api\/habits\/\d+\/log\/$/, ok),
  http.get('*/api/inventory/', empty),
  http.get('*/api/drops/recent/', empty),
  http.get('*/api/cosmetics/', empty),
  http.get('*/api/items/catalog/', empty),
  http.get('*/api/pets/species/catalog/', empty),
  http.get('*/api/quests/catalog/', empty),

  // Pets
  http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
  http.post('*/api/pets/hatch/', ok),
  http.post(/\/api\/pets\/\d+\/feed\/$/, ok),
  http.post(/\/api\/pets\/\d+\/activate\/$/, ok),
  http.get('*/api/mounts/', empty),
  http.post(/\/api\/mounts\/\d+\/activate\/$/, ok),

  // Quests
  http.get('*/api/quests/active/', () => HttpResponse.json(null)),
  http.get('*/api/quests/available/', empty),
  http.post('*/api/quests/start/', ok),
  http.get('*/api/quests/history/', empty),
  http.post('*/api/quests/', ok),
  http.post(/\/api\/quests\/\d+\/assign\/$/, ok),
  http.get('*/api/quests/family/', empty),

  // Activity log (parent-only)
  http.get('*/api/activity/', () =>
    HttpResponse.json({ results: [], next: null, previous: null })),

  // Sprites
  http.get('*/api/sprites/catalog/', () =>
    HttpResponse.json({ sprites: {}, etag: 'test-default-empty' }),
  ),
];
