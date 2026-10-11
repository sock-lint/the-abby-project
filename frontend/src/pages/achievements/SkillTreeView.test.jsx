import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillTreeView from './SkillTreeView.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const categories = [
  { id: 1, name: 'Woodworking', icon: '🪵', description: 'Build with wood.' },
  { id: 2, name: 'Cooking', icon: '🍳', description: 'Prepare good food.' },
];
const handTools = {
  id: 100, name: 'Hand Tools', icon: '🪚', description: 'Use hand tools safely.',
  level: 2, xp_points: 450, xp_to_next_level: 150, unlocked: true,
  level_names: { 1: 'Tool Novice', 2: 'Tool Handler', 3: 'Tool Adept' }, prerequisites: [],
};
const measuring = {
  id: 101, name: 'Measuring & Marking', icon: '📏', description: 'Measure accurately.',
  level: 2, xp_points: 300, xp_to_next_level: 300, unlocked: true,
  level_names: { 1: 'Measure Novice', 2: 'Precise Marker' }, prerequisites: [],
};
const joinery = {
  id: 102, name: 'Joinery', icon: '🪵', description: 'Fit strong wooden joints.',
  level: 0, xp_points: 0, xp_to_next_level: 100, unlocked: false,
  level_names: { 1: 'Joint Novice', 2: 'Joint Builder', 3: 'Joint Artisan' },
  prerequisites: [
    { skill_id: 100, skill_name: 'Hand Tools', required_level: 3, met: false },
    { skill_id: 101, skill_name: 'Measuring & Marking', required_level: 2, met: true },
  ],
};
const knifeSkills = {
  id: 201, name: 'Knife Skills', icon: '🔪', description: 'Cut ingredients safely.',
  level: 1, xp_points: 175, xp_to_next_level: 125, unlocked: true,
  level_names: { 1: 'Kitchen Apprentice', 2: 'Kitchen Adept' }, prerequisites: [],
};
const woodTree = {
  category: categories[0], summary: { level: 2, total_xp: 750 },
  subjects: [
    {
      id: 10, name: 'Shop Basics', icon: '🛠️', description: 'Start in the workshop.',
      summary: { level: 2, total_xp: 750 }, skills: [handTools, measuring],
    },
    {
      id: 11, name: 'Advanced Technique', icon: '🪵', description: 'Build stronger projects.',
      summary: { level: 0, total_xp: 0 }, skills: [joinery],
    },
  ],
};
const cookingTree = {
  category: categories[1], summary: { level: 1, total_xp: 175 },
  subjects: [{
    id: 20, name: 'Kitchen Basics', icon: '🍳', summary: { level: 1, total_xp: 175 },
    skills: [knifeSkills],
  }],
};

function mockCatalog(trees = [woodTree, cookingTree]) {
  const subjects = trees.flatMap((tree) => tree.subjects.filter((subject) => subject.id != null)
    .map(({ id, name, icon, description }) => ({ id, name, icon, description, category: tree.category.id })));
  // Catalog metadata supplies relationships; the trees supply user progress.
  const skills = trees.flatMap((tree) => tree.subjects.flatMap((subject) => subject.skills
    .map(({ id, name, icon, description, level_names }) => ({
      id, name, icon, description, level_names, category: tree.category.id, subject: subject.id,
    }))));
  server.use(
    http.get('*/api/subjects/', () => HttpResponse.json(subjects)),
    http.get('*/api/skills/', () => HttpResponse.json(skills)),
  );
}

function mockTree(tree) {
  const handler = vi.fn(() => HttpResponse.json(tree));
  server.use(http.get(`*/api/skills/tree/${tree.category.id}/`, handler));
  return handler;
}

function mockAtlas(trees = [woodTree, cookingTree]) {
  mockCatalog(trees);
  return trees.map(mockTree);
}

function breadcrumb() {
  return screen.getByRole('navigation', { name: /breadcrumb/i });
}

function expectCurrentCrumb(name) {
  expect(breadcrumb().querySelector('[aria-current="page"]')).toHaveTextContent(name);
}

async function openJoinery(user) {
  await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
  await user.click(await screen.findByRole('button', { name: /Advanced Technique/ }));
  await user.click(await screen.findByRole('button', { name: /Joinery/ }));
  await screen.findByRole('heading', { name: 'Joinery' });
}

describe('SkillTreeView Wayfinder', () => {
  it('renders an empty state when there are no categories', () => {
    render(<SkillTreeView categories={[]} />);
    expect(screen.getByText(/no skill categories yet/i)).toBeInTheDocument();
  });

  it('starts at the category overview and ignores the obsolete remembered tome', async () => {
    const [woodRequest, cookingRequest] = mockAtlas();
    localStorage.setItem('atlas:skill-tree:active-category', '2');
    render(<SkillTreeView categories={categories} />);

    expect(await screen.findByRole('button', { name: /Woodworking/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cooking/ })).toBeInTheDocument();
    expectCurrentCrumb('All skills');
    expect(screen.queryByRole('tablist', { name: /skill categories/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Back/i })).not.toBeInTheDocument();
    expect(woodRequest).not.toHaveBeenCalled();
    expect(cookingRequest).not.toHaveBeenCalled();
  });

  it('drills through categories, subjects, and skills and returns one step at a time', async () => {
    const [woodRequest] = mockAtlas();
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);

    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    expect(await screen.findByRole('button', { name: /Shop Basics/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Advanced Technique/ })).toBeInTheDocument();
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('heading', { name: 'Woodworking' })).toHaveFocus();
    expect(screen.queryByRole('button', { name: /Joinery/ })).not.toBeInTheDocument();
    expect(woodRequest).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /Advanced Technique/ }));
    expect(await screen.findByRole('button', { name: /Joinery/ })).toBeInTheDocument();
    expectCurrentCrumb('Advanced Technique');
    expect(screen.getByRole('heading', { name: 'Advanced Technique' })).toHaveFocus();
    expect(screen.queryByRole('button', { name: /^Hand Tools/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Joinery/ }));
    expect(await screen.findByRole('heading', { name: 'Joinery' })).toBeInTheDocument();
    expectCurrentCrumb('Joinery');
    expect(screen.getByRole('heading', { name: 'Joinery' })).toHaveFocus();
    expect(breadcrumb()).toHaveTextContent(/All skills.*Woodworking.*Advanced Technique.*Joinery/);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Back/i }));
    expectCurrentCrumb('Advanced Technique');
    expect(screen.getByRole('button', { name: /Joinery/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('button', { name: /Shop Basics/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expectCurrentCrumb('All skills');
    expect(screen.getByRole('button', { name: /Cooking/ })).toBeInTheDocument();
  });

  it('uses breadcrumbs to return directly to an ancestor', async () => {
    mockAtlas();
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    await user.click(within(breadcrumb()).getByRole('button', { name: 'Woodworking' }));
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('button', { name: /Shop Basics/ })).toBeInTheDocument();
    await user.click(within(breadcrumb()).getByRole('button', { name: 'All skills' }));
    expectCurrentCrumb('All skills');
    expect(screen.getByRole('button', { name: /Cooking/ })).toBeInTheDocument();
  });

  it('shows server-confirmed locks, requirement completion, and actual level titles', async () => {
    mockAtlas();
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    expect(screen.getByText('Fit strong wooden joints.')).toBeInTheDocument();
    expect(screen.getByText('Joint Novice')).toBeInTheDocument();
    expect(screen.getByText('Joint Builder')).toBeInTheDocument();
    expect(screen.getByText('Joint Artisan')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hand Tools/ })).toHaveTextContent(/Requires Level 3 · Not yet met/);
    expect(screen.getByRole('button', { name: /Measuring & Marking/ })).toHaveTextContent(/Requires Level 2 · Met/);
    expect(screen.getByText(/locked/i)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar', { name: /Joinery.*XP/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Hand Tools/ }));
    expect(await screen.findByRole('heading', { name: 'Hand Tools' })).toBeInTheDocument();
    expectCurrentCrumb('Hand Tools');
    expect(screen.getAllByText('Tool Handler').length).toBeGreaterThan(0);
    expect(screen.getByRole('progressbar', { name: /Hand Tools.*XP/i })).toHaveAttribute('aria-valuenow', '50');
    expect(screen.getByText(/450/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expect(await screen.findByRole('heading', { name: 'Joinery' })).toBeInTheDocument();
    expectCurrentCrumb('Joinery');
  });

  it('follows a cross-category prerequisite by ID and Back returns to its origin skill', async () => {
    const tree = {
      ...woodTree,
      subjects: woodTree.subjects.map((subject) => subject.id === 11 ? {
        ...subject,
        skills: [{ ...joinery, prerequisites: [
          { skill_id: 201, skill_name: 'Knife Skills', required_level: 2, met: false },
        ] }],
      } : {
        ...subject,
        skills: [...subject.skills, {
          ...handTools, id: 103, name: 'Knife Skills', description: 'Carve wood with a knife.',
        }],
      }),
    };
    const [, cookingRequest] = mockAtlas([tree, cookingTree]);
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    await user.click(screen.getByRole('button', { name: /Knife Skills/ }));
    expect(await screen.findByRole('heading', { name: 'Knife Skills' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent(/All skills.*Cooking.*Kitchen Basics.*Knife Skills/);
    expect(screen.getByText('Cut ingredients safely.')).toBeInTheDocument();
    expect(screen.queryByText('Carve wood with a knife.')).not.toBeInTheDocument();
    expect(screen.getAllByText('Kitchen Apprentice').length).toBeGreaterThan(0);
    expect(screen.getByRole('progressbar', { name: /Knife Skills.*XP/i })).toHaveAttribute('aria-valuenow', '38');
    expect(cookingRequest).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expect(await screen.findByRole('heading', { name: 'Joinery' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent(/All skills.*Woodworking.*Advanced Technique.*Joinery/);
  });

  it('keeps a server-locked skill locked even when its requirement flags are met', async () => {
    const tree = { ...woodTree, subjects: woodTree.subjects.map((subject) => subject.id === 11 ? {
      ...subject, skills: [{ ...joinery, prerequisites: joinery.prerequisites.map((requirement) => ({ ...requirement, met: true })) }],
    } : subject) };
    mockAtlas([tree, cookingTree]);
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    expect(screen.getByText(/Locked — meet these skill requirements/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hand Tools/ })).toHaveTextContent(/Requires Level 3 · Met/);
    expect(screen.queryByRole('progressbar', { name: /Joinery.*XP/i })).not.toBeInTheDocument();
  });

  it('uses the current tree subject when a prerequisite target moved after catalog metadata loaded', async () => {
    const tree = { ...woodTree, subjects: woodTree.subjects.map((subject) => subject.id === 11 ? {
      ...subject, skills: [{ ...joinery, prerequisites: [
        { skill_id: 201, skill_name: 'Knife Skills', required_level: 2, met: false },
      ] }],
    } : subject) };
    mockAtlas([tree, cookingTree]);
    mockTree({ ...cookingTree, subjects: [{
      ...cookingTree.subjects[0], id: 21, name: 'Food Preparation',
    }] });
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    await user.click(screen.getByRole('button', { name: /Knife Skills/ }));
    expect(await screen.findByRole('heading', { name: 'Knife Skills' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent(/All skills.*Cooking.*Food Preparation.*Knife Skills/);
    expect(within(breadcrumb()).queryByText('Kitchen Basics')).not.toBeInTheDocument();
    await user.click(within(breadcrumb()).getByRole('button', { name: 'Food Preparation' }));
    expectCurrentCrumb('Food Preparation');
    expect(screen.getByRole('button', { name: /^Knife Skills/ })).toBeInTheDocument();
  });

  it('returns to the category when a prerequisite trip refreshes an origin whose subject was removed', async () => {
    const tree = { ...woodTree, subjects: woodTree.subjects.map((subject) => subject.id === 11 ? {
      ...subject, skills: [{ ...joinery, prerequisites: [
        { skill_id: 201, skill_name: 'Knife Skills', required_level: 2, met: false },
      ] }],
    } : subject) };
    mockAtlas([tree, cookingTree]);
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    await user.click(screen.getByRole('button', { name: /Knife Skills/ }));
    await screen.findByRole('heading', { name: 'Knife Skills' });
    mockTree({ ...woodTree, subjects: [woodTree.subjects[0]] });
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expect(await screen.findByRole('button', { name: /Shop Basics/ })).toBeInTheDocument();
    expectCurrentCrumb('Woodworking');
    expect(screen.queryByRole('heading', { name: 'Joinery' })).not.toBeInTheDocument();
  });

  it('filters category skills, clears an empty result, and opens the matching skill directly', async () => {
    mockAtlas();
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    const filter = await screen.findByRole('searchbox', { name: /Filter skills/i });
    await user.type(filter, 'missing skill');
    expect(await screen.findByText(/no skills match/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Clear filter/i }));
    expect(filter).toHaveValue('');
    expect(screen.getByRole('button', { name: /Shop Basics/ })).toBeInTheDocument();
    await user.type(filter, 'strong wooden');
    expect(await screen.findByRole('button', { name: /Joinery/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Hand Tools/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Joinery/ }));
    expect(await screen.findByRole('heading', { name: 'Joinery' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('searchbox', { name: /Filter skills/i })).toHaveValue('');
  });

  it('limits subject filtering to that subject and clears stale filters on navigation', async () => {
    mockAtlas();
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    await user.click(await screen.findByRole('button', { name: /Shop Basics/ }));
    const filter = screen.getByRole('searchbox', { name: /Filter skills/i });
    await user.type(filter, 'measure');
    expect(screen.getByRole('button', { name: /Measuring & Marking/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Hand Tools/ })).not.toBeInTheDocument();
    await user.clear(filter);
    await user.type(filter, 'joinery');
    expect(screen.getByText(/no skills match/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expect(screen.getByRole('searchbox', { name: /Filter skills/i })).toHaveValue('');
    expect(screen.getByRole('button', { name: /Advanced Technique/ })).toBeInTheDocument();
  });

  it('offers a retry after a category tree fails while preserving navigation', async () => {
    mockCatalog();
    let attempt = 0;
    server.use(http.get('*/api/skills/tree/1/', () => {
      attempt += 1;
      return attempt === 1
        ? HttpResponse.json({ error: 'Tree unavailable' }, { status: 500 })
        : HttpResponse.json(woodTree);
    }));
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Tree unavailable/i);
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again|retry/i }));
    expect(await screen.findByRole('button', { name: /Advanced Technique/ })).toBeInTheDocument();
    expect(attempt).toBe(2);
  });

  it('recovers from a catalog failure', async () => {
    mockAtlas();
    let unavailable = true;
    server.use(http.get('*/api/subjects/', () => unavailable
      ? HttpResponse.json({ error: 'Catalog unavailable' }, { status: 500 })
      : HttpResponse.json([{ id: 10, category: 1, name: 'Shop Basics' }])));
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/Catalog unavailable/i);
    expectCurrentCrumb('All skills');
    unavailable = false;
    await user.click(screen.getByRole('button', { name: /try again|retry/i }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Woodworking/ })).toBeInTheDocument();
  });

  it('ignores a late category response after another category is selected', async () => {
    mockCatalog();
    let release;
    const started = vi.fn();
    server.use(
      http.get('*/api/skills/tree/1/', async () => {
        started();
        await new Promise((resolve) => { release = resolve; });
        return HttpResponse.json(woodTree);
      }),
      http.get('*/api/skills/tree/2/', () => HttpResponse.json(cookingTree)),
    );
    const user = userEvent.setup();
    render(<SkillTreeView categories={categories} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    await waitFor(() => expect(started).toHaveBeenCalled());
    expectCurrentCrumb('Woodworking');
    await user.click(screen.getByRole('button', { name: /Back/i }));
    await user.click(screen.getByRole('button', { name: /Cooking/ }));
    expect(await screen.findByRole('button', { name: /Kitchen Basics/ })).toBeInTheDocument();

    let responseReceived;
    const response = new Promise((resolve) => { responseReceived = resolve; });
    const onResponse = ({ request }) => {
      if (new URL(request.url).pathname === '/api/skills/tree/1/') responseReceived();
    };
    server.events.on('response:mocked', onResponse);
    try {
      await act(async () => { release(); await response; });
    } finally {
      server.events.removeListener('response:mocked', onResponse);
    }
    expectCurrentCrumb('Cooking');
    expect(screen.getByRole('button', { name: /Kitchen Basics/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Advanced Technique/ })).not.toBeInTheDocument();
  });

  it('opens the backend Other subject even though its ID is null', async () => {
    const orphanTree = { ...woodTree, subjects: [{
      id: null, name: 'Other', icon: '', summary: { level: 2, total_xp: 450 }, skills: [handTools],
    }] };
    mockAtlas([orphanTree]);
    const user = userEvent.setup();
    render(<SkillTreeView categories={[categories[0]]} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    await user.click(await screen.findByRole('button', { name: /Other/ }));
    expectCurrentCrumb('Other');
    await user.click(screen.getByRole('button', { name: /Hand Tools/ }));
    expect(await screen.findByRole('heading', { name: 'Hand Tools' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent(/Woodworking.*Other.*Hand Tools/);
  });

  it('returns to the overview when the selected category is removed', async () => {
    mockAtlas();
    const user = userEvent.setup();
    const { rerender } = render(<SkillTreeView categories={categories} />);
    await openJoinery(user);
    rerender(<SkillTreeView categories={[categories[1]]} />);
    await waitFor(() => expectCurrentCrumb('All skills'));
    expect(screen.getByRole('button', { name: /Cooking/ })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Joinery' })).not.toBeInTheDocument();
  });

  it('renders an empty category without invented subjects', async () => {
    mockAtlas([{ ...woodTree, subjects: [] }]);
    const user = userEvent.setup();
    render(<SkillTreeView categories={[categories[0]]} />);
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    expect(await screen.findByText(/no subjects/i)).toBeInTheDocument();
    expectCurrentCrumb('Woodworking');
    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument();
  });
});
