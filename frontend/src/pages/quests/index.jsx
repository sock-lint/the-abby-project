import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import Movement from '../Movement';
import Trials from '../trials';
import Forge from '../forge';

/**
 * Tasks brings everyday activities, projects and challenges into one hub.
 * Legacy tab IDs stay stable for saved links and notification destinations.
 */
export default function QuestsHub() {
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
        { id: 'ventures', label: 'Projects',    render: () => <Projects /> },
        { id: 'forge',    label: '3D Printing', render: () => <Forge /> },
        { id: 'trials',   label: 'Challenges',  render: () => <Trials /> },
      ]}
    />
  );
}
