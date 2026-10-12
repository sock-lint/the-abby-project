// Synthetic examples for /__design. Catalog relationships and sample progress
// are separate so catalog counts never masquerade as personal completion.
export const SKILL_CATEGORIES = [
  { id: 1, name: 'Woodworking', icon: '🪵', description: 'Build useful things with wood.' },
  { id: 2, name: 'Art & Crafts', icon: '🎨', description: 'Explore materials, colour, and creative techniques.' },
  { id: 3, name: 'Cooking', icon: '🍳', description: 'Prepare food and discover new flavours.' },
];

export const SKILL_CATALOG = {
  subjects: [
    { id: 10, category: 1, name: 'Workshop foundations', icon: '🛠️', description: 'Start with safe tools and careful measurements.' },
    { id: 11, category: 1, name: 'Finishing & decorative techniques', icon: '✨', description: 'Bring a personal touch to a finished piece.' },
    { id: 20, category: 2, name: 'Surface decoration', icon: '🖌️', description: 'Add colour, texture, and a little shimmer.' },
    { id: 30, category: 3, name: 'Kitchen basics', icon: '🥣', description: 'Practice everyday kitchen techniques.' },
  ],
  skills: [
    { id: 100, category: 1, subject: 10, name: 'Measure & Mark', icon: '📏', description: 'Measure twice and make clear, accurate marks.' },
    { id: 101, category: 1, subject: 10, name: 'Read a Plan', icon: '📐', description: 'Turn a drawing into a practical building plan.' },
    { id: 110, category: 1, subject: 11, name: 'Inlay Work', icon: '✨', description: 'Create decorative patterns with contrasting materials.' },
    { id: 111, category: 1, subject: 11, name: 'Wood Finishing', icon: '🪵', description: 'Choose and apply a finish that protects your work.' },
    { id: 200, category: 2, subject: 20, name: 'Gilding', icon: '🌟', description: 'Apply thin metal leaf to a prepared surface.' },
    { id: 201, category: 2, subject: 20, name: 'Colour Mixing', icon: '🎨', description: 'Mix a palette and notice how colours work together.' },
    { id: 300, category: 3, subject: 30, name: 'Knife Skills', icon: '🥕', description: 'Practice safe, consistent cuts.' },
    { id: 301, category: 3, subject: 30, name: 'Follow a Recipe', icon: '📋', description: 'Read the steps, prepare ingredients, and taste as you go.' },
  ],
};

export const SKILL_PROGRESS = {
  100: { level: 3, xp_points: 780, unlocked: true, level_names: { 1: 'First marks', 2: 'Careful measurer', 3: 'Precise planner', 4: 'Workshop guide', 5: 'Expert planner', 6: 'Master measurer' }, prerequisites: [] },
  101: { level: 1, xp_points: 220, unlocked: true, level_names: { 1: 'Plan reader', 2: 'Plan maker' }, prerequisites: [{ skill_id: 100, skill_name: 'Measure & Mark', required_level: 2, met: true }] },
  110: { level: 0, xp_points: 0, unlocked: false, level_names: { 1: 'Pattern beginner', 2: 'Pattern builder' }, prerequisites: [{ skill_id: 100, skill_name: 'Measure & Mark', required_level: 2, met: true }, { skill_id: 200, skill_name: 'Gilding', required_level: 3, met: false }] },
  111: { level: 6, xp_points: 2500, unlocked: true, level_names: { 6: 'Master finisher' }, prerequisites: [] },
  200: { level: 2, xp_points: 450, unlocked: true, level_names: { 1: 'Leaf learner', 2: 'Surface artist', 3: 'Gilding artisan' }, prerequisites: [] },
  201: { level: 0, xp_points: 40, unlocked: true, level_names: {}, prerequisites: [] },
  300: { level: 1, xp_points: 175, unlocked: true, level_names: { 1: 'Kitchen apprentice', 2: 'Confident cook' }, prerequisites: [] },
  301: { level: 0, xp_points: 0, unlocked: true, level_names: {}, prerequisites: [] },
};

export const BADGE_COLLECTIONS = [
  {
    id: 'everyday', name: 'Everyday adventures & discoveries', icon: '🧭',
    description: 'Small beginnings and moments of curiosity.',
    entries: [{ name: 'First adventure', earned: true }, { name: 'Curious explorer', earned: true }, { name: 'Trail companion', earned: false }],
  },
  {
    id: 'maker', name: 'Making & learning', icon: '🛠️',
    description: 'Recognise practice and finished creations.',
    entries: [{ name: 'First creation', earned: true }, { name: 'Careful craftsperson', earned: false }, { name: 'Creative collaborator', earned: false }, { name: 'Workshop mentor', earned: false }],
  },
  {
    id: 'kindness', name: 'Kindness & helpful habits', icon: '🌱',
    description: 'Celebrate the ways you care for your community.',
    entries: [{ name: 'Helping hand', earned: false }, { name: 'Steady friend', earned: false }],
  },
  {
    id: 'collection', name: 'Treasures collected', icon: '✨',
    description: 'Keep track of the discoveries you have gathered.',
    entries: [{ name: 'Treasure keeper', earned: true }, { name: 'Collection complete', earned: true }],
  },
];

export const LOREBOOK_TOPICS = [
  {
    id: 'beginning', name: 'Getting started in your Meadow', icon: '🌼',
    entries: ['Your first visit', 'Finding your next adventure', 'Keeping a little piece of today'],
  },
  {
    id: 'progress', name: 'Skills, experience & growing at your own pace', icon: '🧭',
    entries: ['How skill experience works', 'Following a prerequisite path'],
  },
  {
    id: 'companions', name: 'Companions & their favourite treats', icon: '🐣',
    entries: ['Meeting a companion', 'Food and happiness', 'Growing together', 'Exploring with a mount'],
  },
  {
    id: 'rewards', name: 'Coins, rewards & saving for something special', icon: '🪙',
    entries: ['Earning coins', 'Planning a savings goal', 'Choosing a reward'],
  },
];

export const INVENTORY_ITEMS = [
  { id: 'egg', kind: 'eggs', name: 'Meadow egg', quantity: 4 },
  { id: 'mint', kind: 'potions', name: 'Mint potion', quantity: 42 },
  { id: 'apple', kind: 'food', name: 'Apple treats', quantity: 12 },
  { id: 'frame', kind: 'frames', name: 'Flower portrait frame', quantity: 3 },
  { id: 'scroll', kind: 'scrolls', name: 'Discovery quest scroll', quantity: 2 },
  { id: 'pouch', kind: 'pouches', name: 'Little coin pouch', quantity: 5 },
];

export const INVENTORY_FILTERS = [
  { id: 'all', name: 'All treasures', icon: '✨' },
  { id: 'eggs', name: 'Eggs', icon: '🥚' },
  { id: 'potions', name: 'Potions', icon: '🧪' },
  { id: 'food', name: 'Food & treats', icon: '🍎' },
  { id: 'frames', name: 'Avatar frames & accessories', icon: '🖼️' },
  { id: 'scrolls', name: 'Quest scrolls', icon: '📜' },
  { id: 'pouches', name: 'Coin pouches', icon: '🪙' },
];
