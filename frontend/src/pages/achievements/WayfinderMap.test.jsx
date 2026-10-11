import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, within } from '../../test/render';
import { WayfinderCategoryMap, WayfinderHeading, WayfinderSubjectMap } from './WayfinderMap';

const woodworking = { id: 7, name: 'Woodworking', icon: '🪵' };
const sewing = { id: 8, name: 'Sewing & Textiles', icon: '🧵' };
const shopBasics = {
  id: 10,
  category: woodworking.id,
  name: 'Shop Basics',
  icon: '🔨',
  skills: [{ id: 101, name: 'Measuring & Marking' }, { id: 102, name: 'Hand Tools' }],
};
const advanced = {
  id: 11,
  category: woodworking.id,
  name: 'Advanced Technique',
  icon: '🪚',
  skills: [{ id: 103, name: 'Joinery' }],
};

describe('WayfinderCategoryMap', () => {
  it('opens the selected category by its actual ID and counts only its catalog entries', async () => {
    const onSelectCategory = vi.fn();
    renderWithProviders(
      <WayfinderCategoryMap
        categories={[woodworking, sewing]}
        catalog={{
          subjects: [shopBasics, advanced, { id: 12, category: '8', name: 'Hand Work' }],
          skills: [
            ...shopBasics.skills.map((skill) => ({ ...skill, category: '7' })),
            ...advanced.skills.map((skill) => ({ ...skill, category: 7 })),
            { id: 104, category: 8, name: 'Hand Sewing' },
          ],
        }}
        onSelectCategory={onSelectCategory}
      />,
    );

    const woodworkingButton = screen.getByRole('button', { name: 'Woodworking, 2 subjects · 3 skills' });
    expect(screen.getByRole('button', { name: 'Sewing & Textiles, 1 subject · 1 skill' })).toBeInTheDocument();
    await userEvent.click(woodworkingButton);
    expect(onSelectCategory).toHaveBeenCalledExactlyOnceWith(7);
  });

  it('keeps full destination names visible without inventing counts while metadata loads', () => {
    const name = 'Making & Fabrication with a deliberately long category name';
    renderWithProviders(
      <WayfinderCategoryMap
        categories={[{ id: 0, name, icon: '🔧' }]}
        catalog={null}
        onSelectCategory={vi.fn()}
      />,
    );
    const categoryButton = screen.getByRole('button', { name });
    expect(within(categoryButton).getByText(name)).toBeInTheDocument();
    expect(screen.queryByText(/0 subjects|0 skills|XP|Level/i)).not.toBeInTheDocument();
  });

  it('shows an empty category state', () => {
    renderWithProviders(<WayfinderCategoryMap categories={[]} onSelectCategory={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('No skill categories yet.');
  });
});

describe('WayfinderSubjectMap', () => {
  it('opens a real subject object and previews the actual skills in its branch', async () => {
    const onSelectSubject = vi.fn();
    renderWithProviders(
      <WayfinderSubjectMap category={woodworking} subjects={[shopBasics, advanced]} onSelectSubject={onSelectSubject} />,
    );
    expect(screen.getByRole('list', { name: 'Woodworking subjects' })).toBeInTheDocument();
    const preview = screen.getByRole('list', { name: 'Shop Basics skill preview' });
    expect(within(preview).getByText('Measuring & Marking')).toBeInTheDocument();
    expect(within(preview).getByText('Hand Tools')).toBeInTheDocument();
    expect(within(preview).queryByText('Joinery')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Advanced Technique, 1 skill' }));
    expect(onSelectSubject).toHaveBeenCalledExactlyOnceWith(advanced);
  });

  it('makes the null-ID Other branch selectable and preserves its skills', async () => {
    const other = { id: null, name: 'Other', skills: [{ id: 200, name: 'Unassigned skill' }] };
    const onSelectSubject = vi.fn();
    renderWithProviders(
      <WayfinderSubjectMap category={woodworking} subjects={[other]} onSelectSubject={onSelectSubject} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Other, 1 skill' }));
    expect(onSelectSubject).toHaveBeenCalledExactlyOnceWith(other);
    expect(screen.getByText('Unassigned skill')).toBeInTheDocument();
  });

  it('shows empty subjects honestly and supports long full subject names', () => {
    const name = 'A subject whose full name should remain available at every screen width';
    renderWithProviders(
      <WayfinderSubjectMap category={woodworking} subjects={[{ id: 90, name }]} onSelectSubject={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: `${name}, 0 skills` })).toHaveTextContent(name);
    expect(screen.getByText('No skills yet')).toBeInTheDocument();
  });

  it('handles a category without subjects', () => {
    renderWithProviders(<WayfinderSubjectMap category={woodworking} subjects={[]} onSelectSubject={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('No subjects or skills in this category yet.');
  });
});

describe('WayfinderHeading', () => {
  it('exposes the full page title as a heading and keeps the icon decorative', () => {
    renderWithProviders(
      <WayfinderHeading title="Making & Fabrication" icon="🔧" description="Making things that work" meta="3 subjects · 8 skills" />,
    );
    expect(screen.getByRole('heading', { level: 2, name: 'Making & Fabrication' })).toBeInTheDocument();
    expect(screen.getByText('Making things that work')).toBeInTheDocument();
    expect(screen.getByText('3 subjects · 8 skills')).toBeInTheDocument();
    expect(screen.getByText('🔧')).toHaveAttribute('aria-hidden', 'true');
  });
});
