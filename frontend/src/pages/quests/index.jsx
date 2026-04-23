import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import Movement from '../Movement';

/**
 * Quests — hub page consolidating all "things to do."
 *
 * Ventures (Projects) · Duties (Chores) · Study (Homework)
 * Rituals (Habits) · Movement (sessions)
 *
 * Trials — the adventure overlay (time-boxed boss/collection quests) —
 * lives at /trials, reached via the active-trial HeaderProgressBand,
 * the QuickActions "Start a quest" shortcut, and the Sigil page.
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
        { id: 'rituals',  label: 'Rituals',  render: () => <Habits /> },
        { id: 'movement', label: 'Movement', render: () => <Movement /> },
      ]}
    />
  );
}
