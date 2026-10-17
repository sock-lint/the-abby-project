import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import Movement from '../Movement';
import Reading from '../reading';
import Trials from '../trials';

/**
 * Tasks brings everyday activities, projects and challenges into one hub.
 * Legacy tab IDs stay stable for saved links and notification destinations.
 */
export default function QuestsHub() {
  const [params] = useSearchParams();
  // Saved notifications and bookmarks keep working without carrying unrelated
  // query parameters into the new home.
  if (params.get('tab') === 'forge') {
    return <Navigate replace to={`/treasury?tab=forge${params.get('new') === '1' ? '&new=1' : ''}`} />;
  }
  return (
    <ChapterHub
      title="Tasks"
      kicker="Plan your day and track your progress"
      glyph="sheikah-eye"
      defaultTabId="study"
      tabs={[
        { id: 'study',    label: 'Homework',    render: () => <Homework /> },
        { id: 'duties',   label: 'Chores',      render: () => <Chores /> },
        { id: 'rituals',  label: 'Habits',      render: () => <Habits /> },
        { id: 'movement', label: 'Movement',    render: () => <Movement /> },
        { id: 'reading',  label: 'Reading',     render: () => <Reading /> },
        { id: 'ventures', label: 'Projects',    render: () => <Projects /> },
        { id: 'trials',   label: 'Challenges',  render: () => <Trials /> },
      ]}
    />
  );
}
import { Navigate, useSearchParams } from 'react-router-dom';
