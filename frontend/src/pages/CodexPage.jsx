import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';
import CodexSection from './manage/CodexSection';

export default function CodexPage() {
  return (
    <PageShell rhythm="loose">
      <PageHeader
        title="Codex"
        kicker="stewardship · content catalog"
      />
      <CodexSection />
    </PageShell>
  );
}
