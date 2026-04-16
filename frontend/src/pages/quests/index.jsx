import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import LegacyQuests from '../Quests';

/**
 * Quests — hub page consolidating all "things to do."
 *
 * Ventures (Projects) · Duties (Chores) · Study (Homework)
 * Trials   (RPG Quests) · Rituals (Habits)
 */
export default function QuestsHub() {
  return (
    <ChapterHub
      title="Quests"
      kicker="Chapter II · The Call to Adventure"
      glyph="sheikah-eye"
      defaultTabId="ventures"
      tabs={[
        { id: 'ventures', label: 'Ventures', render: () => <Projects /> },
        { id: 'duties',   label: 'Duties',   render: () => <Chores /> },
        { id: 'study',    label: 'Study',    render: () => <Homework /> },
        { id: 'trials',   label: 'Trials',   render: () => <LegacyQuests /> },
        { id: 'rituals',  label: 'Rituals',  render: () => <Habits /> },
      ]}
    />
  );
}
