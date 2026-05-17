import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import Movement from '../Movement';
import Trials from '../trials';

/**
 * Quests — hub page consolidating all "things to do."
 *
 * Ventures (Projects) · Duties (Chores) · Study (Homework)
 * Rituals (Habits) · Movement (sessions) · Trials (boss/collection quests)
 *
 * Trials lives inside the hub now and speaks the same codex/folio/vessels
 * vocabulary as the Bestiary. The legacy /trials route redirects here.
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
        { id: 'trials',   label: 'Trials',   render: () => <Trials /> },
      ]}
    />
  );
}
