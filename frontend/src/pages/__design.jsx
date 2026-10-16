import { useState } from 'react';
import { MemoryRouter, useInRouterContext } from 'react-router-dom';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import QuestLogEntry from '../components/journal/QuestLogEntry';
import StreakFlame from '../components/journal/StreakFlame';
import PartyCard from '../components/journal/PartyCard';
import RuneBand from '../components/journal/RuneBand';
import DeckleDivider from '../components/journal/DeckleDivider';
import {
  TodayIcon, QuestsIcon, BestiaryIcon, TreasuryIcon, AtlasIcon, ChronicleIcon,
  ClockFabIcon, InkwellIcon, ScrollIcon, EggIcon, CoinIcon, DragonIcon,
} from '../components/icons/JournalIcons';
import { headingDisplay, headingScript } from '../constants/styles';
import Button from '../components/Button';
import { TextField, SelectField, TextAreaField } from '../components/form';
import IlluminatedVersal from '../components/atlas/IlluminatedVersal';
import AccordionSection from '../components/dashboard/AccordionSection';
import SectionHeader from '../components/SectionHeader';
import { PROGRESS_TIER } from '../components/atlas/mastery.constants';
import SkillsShowcase from './design/SkillsShowcase';
import CollectionsShowcase from './design/CollectionsShowcase';
import DesignEnvironment from './design/DesignEnvironment';
import PatternLibrary from './design/PatternLibrary';
import TasksShowcase from './design/TasksShowcase';
import DropdownShowcase from './design/DropdownShowcase';

export default function DesignShowcase() {
  const hasRouter = useInRouterContext();
  return hasRouter ? <DesignShowcaseContent /> : <MemoryRouter><DesignShowcaseContent /></MemoryRouter>;
}

function DesignShowcaseContent() {
  const [interaction, setInteraction] = useState('');
  return (
    <DesignEnvironment><div id="design-foundations" className="max-w-5xl mx-auto py-8 space-y-10 min-w-0">
      {/* Header */}
      <header>
        <div className={headingScript + ' text-lg'}>
          Meadow · Shared UI foundations
        </div>
        <h1 className={headingDisplay + ' text-4xl md:text-5xl font-bold'}>
          Design Showcase
        </h1>
        <p className="font-body text-ink-secondary mt-2 max-w-prose">
          A visual QA page for our Meadow components. Navigate to{' '}
          <code className="font-rune text-sm">/__design</code> in dev to inspect
          typography, controls, Task folios, collection navigation and progress states.
        </p>
        <nav aria-label="Showcase sections" className="mt-3 font-body text-body">
          <a href="#task-folio" className="inline-flex min-h-11 items-center text-sheikah-teal-deep underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sheikah-teal">Task folio</a>
        </nav>
      </header>

      <DeckleDivider glyph="compass-rose" label="Typography" />

      <section className="grid md:grid-cols-2 gap-6">
        <ParchmentCard flourish>
          <h2 className="font-display text-2xl font-bold mb-1">Nunito headings</h2>
          <p className="font-script text-ink-whisper text-sm">One bundled family, with real weights for every surface</p>
          <p className="font-body text-base mt-3">
            Keep a little piece of today. <span className="font-normal">Regular body copy</span>,{' '}
            <span className="font-semibold">semibold labels</span>, and <strong>bold headings</strong>.
          </p>
        </ParchmentCard>
        <ParchmentCard>
          <h2 className="font-script text-3xl font-bold text-ink-primary">Clear labels and tallies</h2>
          <p className="font-body text-base mt-1 text-ink-secondary">
            Friendly, readable dates, counts and supporting text.
          </p>
          <div className="font-rune text-sm mt-3 text-ember-deep">
            02:47:13 · $24.50 · 120🪙
          </div>
          <p className="font-script text-xs text-ink-whisper mt-1">
            Nunito with tabular numbers keeps balances and timers aligned.
          </p>
        </ParchmentCard>
      </section>

      <DeckleDivider glyph="rune-orb" label="Palette" />

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ['ink-page', 'ink-primary'],
          ['ink-page-aged', 'ink-primary'],
          ['ink-page-shadow', 'ink-primary'],
          ['sheikah-teal', 'ink-page-rune-glow'],
          ['sheikah-teal-deep', 'ink-page-rune-glow'],
          ['moss', 'ink-page-rune-glow'],
          ['ember', 'ink-page-rune-glow'],
          ['ember-deep', 'ink-page-rune-glow'],
          ['royal', 'ink-page-rune-glow'],
          ['gold-leaf', 'ink-page-rune-glow'],
        ].map(([bg, fg]) => (
          <div
            key={bg}
            className="rounded-lg border border-ink-page-shadow p-3 text-center"
            style={{ backgroundColor: `var(--color-${bg})`, color: `var(--color-${fg})` }}
          >
            <div className="font-rune text-xs">{bg}</div>
          </div>
        ))}
      </section>

      <DeckleDivider glyph="flourish-corner" label="Buttons" />

      <section className="flex flex-wrap gap-3">
        <Button size="sm">Primary action</Button>
        <Button variant="success" size="sm">Confirm action</Button>
        <Button variant="secondary" size="sm">Secondary action</Button>
        <Button variant="danger" size="sm">Destructive action</Button>
        <Button variant="ghost" size="sm">Ghost action</Button>
      </section>

      <DeckleDivider glyph="sheikah-eye" label="RuneBadge tones" />

      <section className="flex flex-wrap gap-2">
        <RuneBadge tone="teal">active</RuneBadge>
        <RuneBadge tone="moss">approved</RuneBadge>
        <RuneBadge tone="ember">pending</RuneBadge>
        <RuneBadge tone="royal">epic</RuneBadge>
        <RuneBadge tone="gold">legendary</RuneBadge>
        <RuneBadge tone="rose">favorite</RuneBadge>
        <RuneBadge tone="ink">archived</RuneBadge>
        <RuneBadge tone="teal" variant="outlined">outlined</RuneBadge>
        <RuneBadge tone="teal" size="md">medium</RuneBadge>
      </section>

      <DeckleDivider glyph="dragon-crest" label="Cards" />

      <section className="grid md:grid-cols-3 gap-4">
        <ParchmentCard variant="plain">
          <div className="font-script text-ink-whisper text-xs">variant: plain</div>
          <h3 className="font-display text-lg mt-1">Standard panel</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Rounded Meadow panel with a quiet border.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" flourish>
          <div className="font-script text-ink-whisper text-xs">flourish</div>
          <h3 className="font-display text-lg mt-1">Decorated panel</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Optional soft sparkles in the corners.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" seal>
          <div className="font-script text-ink-whisper text-xs">seal</div>
          <h3 className="font-display text-lg mt-1">Flower accent</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Optional decorative flower in the corner.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" tone="bright">
          <div className="font-script text-ink-whisper text-xs">tone: bright</div>
          <h3 className="font-display text-lg mt-1">Bright panel</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Lighter tone — use for hero/spotlight panels.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" tone="deep">
          <div className="font-script text-ink-whisper text-xs">tone: deep</div>
          <h3 className="font-display text-lg mt-1">Deep panel</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Deeper tone — for nested / quieter panels.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="deckle">
          <div className="font-script text-ink-whisper text-xs">variant: deckle</div>
          <h3 className="font-display text-lg mt-1">Rounded compatibility variant</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            The retained deckle prop uses the current rounded panel treatment.
          </p>
        </ParchmentCard>
      </section>

      <DeckleDivider glyph="compass-rose" label="QuestLogEntry" />

      <ParchmentCard>
        <ul className="space-y-2">
          <QuestLogEntry
            title="Make bed"
            meta="Chore · due today"
            reward="$0.50 · 3🪙"
            kind="duty"
            tone="moss"
            status="pending"
            icon={<InkwellIcon size={16} />}
          />
          <QuestLogEntry
            title="Math chapter 7 practice"
            meta="Due Wed · effort ★★★"
            reward="$2.50 · 12🪙"
            kind="study"
            tone="teal"
            status="pending"
            icon={<ScrollIcon size={16} />}
          />
          <QuestLogEntry
            title="Mount Yamatori — 120 HP remaining"
            meta="Challenge · ends in 2 days"
            reward="+25 XP · egg"
            kind="trial"
            tone="royal"
            status="pending"
            icon={<DragonIcon size={16} />}
          />
          <QuestLogEntry
            title="Sketch a dragon in under 10 min"
            meta="Habit · strength 4"
            reward="Progress from saved activity"
            kind="virtue"
            tone="gold"
            status="done"
          />
          <QuestLogEntry
            title="Art history essay"
            meta="Was due yesterday"
            reward="$1.00 · 5🪙"
            kind="study"
            tone="ember"
            status="overdue"
          />
          <QuestLogEntry
            title="Level 10 unlocks this quest"
            meta="Currently level 8"
            kind="trial"
            tone="ink"
            status="locked"
          />
        </ul>
      </ParchmentCard>

      <DeckleDivider glyph="flourish-corner" label="Hero widgets" />

      <section className="grid md:grid-cols-3 gap-4">
        <ParchmentCard tone="bright">
          <StreakFlame streak={12} longest={30} multiplier="1.84" />
        </ParchmentCard>
        <ParchmentCard tone="bright">
          <StreakFlame streak={0} longest={30} />
        </ParchmentCard>
        <ParchmentCard tone="bright">
          <StreakFlame streak={45} longest={60} multiplier="2.0" />
        </ParchmentCard>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <PartyCard
          pet={{ species_name: 'Ember Drake', potion_variant: 'fire', growth_points: 62 }}
          variant="compact"
        />
        <PartyCard
          pet={{ species_name: 'Tidebloom', potion_variant: 'water', growth_points: 18 }}
          variant="full"
          onFeed={() => setInteraction('Example feed action selected. No pet or reward changed.')}
        />
        <PartyCard pet={null} />
      </section>

      {interaction && <p role="status" className="font-body text-body text-ink-secondary">{interaction}</p>}

      <RuneBand projectTitle="Stained-glass dragon lantern" elapsedLabel="00:42:17" />

      <DeckleDivider glyph="rune-orb" label="Chapter icons" />

      <section className="flex flex-wrap gap-6 items-center text-ink-primary">
        <Labeled label="Today"><TodayIcon size={32} /></Labeled>
        <Labeled label="Tasks"><QuestsIcon size={32} /></Labeled>
        <Labeled label="Pets"><BestiaryIcon size={32} /></Labeled>
        <Labeled label="Rewards"><TreasuryIcon size={32} /></Labeled>
        <Labeled label="Progress"><AtlasIcon size={32} /></Labeled>
        <Labeled label="Memories"><ChronicleIcon size={32} /></Labeled>
        <div className="w-px h-10 bg-ink-page-shadow" />
        <Labeled label="Clock">
          <span className="text-sheikah-teal-deep"><ClockFabIcon size={32} /></span>
        </Labeled>
        <Labeled label="Inkwell"><InkwellIcon size={28} /></Labeled>
        <Labeled label="Scroll"><ScrollIcon size={28} /></Labeled>
        <Labeled label="Egg"><EggIcon size={28} /></Labeled>
        <Labeled label="Coin"><CoinIcon size={28} /></Labeled>
        <Labeled label="Dragon"><DragonIcon size={28} /></Labeled>
      </section>

      <section className="space-y-4">
        <SectionHeader title="Meadow markers" index={1} kicker="rounded chapter waypoints" />
        <AccordionSection
          title="Rewards"
          index={0}
          kicker="this week at a glance"
          icon={<TreasuryIcon size={18} />}
          tone="gold"
          peek={<span className="inline-flex items-center gap-1"><CoinIcon size={14} />24 coins · $12.00 earned</span>}
        >
          <p className="font-body text-body text-ink-secondary">Shared symbols follow your Meadow cover.</p>
        </AccordionSection>
      </section>

      <DeckleDivider glyph="sheikah-eye" label="Form primitives" />

      <ParchmentCard className="space-y-4">
        <TextField
          id="demo-text"
          label="Activity name"
          placeholder="Sketch a picture, plan a project, write a letter…"
          helpText="TextField — labeled input with helpText slot."
        />
        <SelectField
          id="demo-select"
          label="Choose an activity"
          helpText="SelectField — themed dropdown; pass <option> children directly."
        >
          <option value="">Choose…</option>
          <option value="dragon">Draw a dragon</option>
          <option value="forge">Build a model</option>
          <option value="map">Make a map</option>
        </SelectField>
        <TextAreaField
          id="demo-textarea"
          label="Activity notes"
          rows={3}
          placeholder="What would help you get started?"
          helpText="TextAreaField — labeled textarea; rows defaults to 3."
        />
        <TextField
          id="demo-error"
          label="Field with error"
          defaultValue="invalid-input"
          error="This field has an error message wired through aria-describedby."
        />
      </ParchmentCard>

      <DropdownShowcase />

      <DeckleDivider glyph="compass-rose" label="Task folio" />

      <TasksShowcase />

      <DeckleDivider glyph="dragon-crest" label="Skills · Wayfinder" />

      <SkillsShowcase />

      <DeckleDivider glyph="compass-rose" label="Collection navigation" />

      <CollectionsShowcase />

      <DeckleDivider glyph="rune-orb" label="Shared progress states" />

      <section aria-label="Shared progress states" className="space-y-4">
        <h2 className="font-display text-2xl font-bold text-ink-primary">Progress markers</h2>
        <p className="font-body text-body text-ink-secondary">Synthetic states for the shared progress primitive.</p>
        <div className="flex items-center gap-6 flex-wrap">
          <Labeled label="locked"><IlluminatedVersal letter="L" progressPct={0} tier={PROGRESS_TIER.locked} /></Labeled>
          <Labeled label="nascent 10%"><IlluminatedVersal letter="N" progressPct={10} tier={PROGRESS_TIER.nascent} /></Labeled>
          <Labeled label="rising 45%"><IlluminatedVersal letter="R" progressPct={45} tier={PROGRESS_TIER.rising} /></Labeled>
          <Labeled label="cresting 75%"><IlluminatedVersal letter="C" progressPct={75} tier={PROGRESS_TIER.cresting} /></Labeled>
          <Labeled label="gilded 100%"><IlluminatedVersal letter="G" progressPct={100} tier={PROGRESS_TIER.gilded} /></Labeled>
        </div>
      </section>

      <PatternLibrary />

      <DeckleDivider glyph="dragon-crest" />

      <footer className="text-center font-script text-ink-whisper text-sm pt-2 pb-8">
        End of entry · {new Date().toLocaleDateString()}
      </footer>
    </div></DesignEnvironment>
  );
}

function Labeled({ label, children }) {
  return (
    <div className="flex flex-col items-center gap-1">
      {children}
      <span className="font-script text-xs text-ink-secondary">{label}</span>
    </div>
  );
}
