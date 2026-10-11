import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { getCategories } from '../src/api';
import { useApi } from '../src/hooks/useApi';
import { normalizeList } from '../src/utils/api';
import Loader from '../src/components/Loader';
import ErrorAlert from '../src/components/ErrorAlert';
import SkillTreeView from '../src/pages/achievements/SkillTreeView';
import { applyTheme } from '../src/themes';

const theme = new URLSearchParams(window.location.search).get('theme');
applyTheme(theme === 'vigil' ? 'vigil' : 'hyrule');

export default function Fixture() {
  const { data, loading, error } = useApi(getCategories);
  return (
    <main className="p-4 max-w-3xl mx-auto">
      {loading ? <Loader /> : error ? <ErrorAlert message={error} /> : <SkillTreeView categories={normalizeList(data)} />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<Fixture />);
