import ChapterHub from '../../components/layout/ChapterHub';
import Projects from '../Projects';
import Chores from '../Chores';
import Homework from '../Homework';
import Habits from '../Habits';
import Movement from '../Movement';
import Trials from '../trials';
import Forge from '../forge';

/**
 * Quests — hub page consolidating all "things to do."
 *
 * Tab order runs daily-cadence first → multi-day → aspirational:
 *   Study (Homework) · Duties (Chores) · Rituals (Habits) · Movement
 *   · Ventures (Projects) · Forge (3D print requests)
 *   · Trials (boss/collection quests)
 *
 * Slugs are stable — only the visual ordering and default landing tab
 * changed, so deep links like /quests?tab=ventures still work. Trials
 * lives inside the hub and speaks the same codex/folio/vessels vocabulary
 * as the Bestiary; the legacy /trials route redirects here.
 *
 * Forge sits after Ventures: a print request is a thing you ask for and
 * then wait on, which puts it past the daily cadence but short of a
 * multi-week campaign. Its slug is the binding contract for the seven
 * print_* notification types, which all deep-link to /quests?tab=forge.
 */
export default function QuestsHub() {
  return (
    <ChapterHub
      title="Quests"
      kicker="Chapter II · The Call to Adventure"
      glyph="sheikah-eye"
      defaultTabId="study"
      tabs={[
        { id: 'study',    label: 'Study',    render: () => <Homework /> },
        { id: 'duties',   label: 'Duties',   render: () => <Chores /> },
        { id: 'rituals',  label: 'Rituals',  render: () => <Habits /> },
        { id: 'movement', label: 'Movement', render: () => <Movement /> },
        { id: 'ventures', label: 'Ventures', render: () => <Projects /> },
        { id: 'forge',    label: 'Forge',    render: () => <Forge /> },
        { id: 'trials',   label: 'Trials',   render: () => <Trials /> },
      ]}
    />
  );
}
