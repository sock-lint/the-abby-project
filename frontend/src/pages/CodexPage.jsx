import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';
import CodexSection from './manage/CodexSection';

/**
 * /codex — the parent-facing RPG content catalog (items, creatures, mounts,
 * adventures, sprites).
 *
 * Titled "Content Catalog" rather than "Codex": the Bestiary hub already
 * ships a kid-facing "Codex" tab for species, so a bare "Codex" heading named
 * two unrelated surfaces. This page administers none of the Lorebook — that
 * lives under Manage → Guide.
 */
export default function CodexPage() {
  return (
    <PageShell rhythm="loose">
      <PageHeader
        title="Content Catalog"
        kicker="stewardship · items, creatures, mounts, adventures, sprites"
      />
      <CodexSection />
    </PageShell>
  );
}
