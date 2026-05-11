import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import QuestLogEntry from '../components/journal/QuestLogEntry';
import StreakFlame from '../components/journal/StreakFlame';
import PartyCard from '../components/journal/PartyCard';
import RuneBand from '../components/journal/RuneBand';
import DeckleDivider from '../components/journal/DeckleDivider';
import {
  TodayIcon, QuestsIcon, BestiaryIcon, TreasuryIcon, AtlasIcon,
  ClockFabIcon, InkwellIcon, ScrollIcon, EggIcon, CoinIcon, DragonIcon,
} from '../components/icons/JournalIcons';
import { headingDisplay, headingScript } from '../constants/styles';
import Button from '../components/Button';
import { TextField, SelectField, TextAreaField } from '../components/form';
import TomeShelf from '../components/atlas/TomeShelf';
import FolioSpread from './achievements/FolioSpread';
import IlluminatedVersal from '../components/atlas/IlluminatedVersal';
import { PROGRESS_TIER, tierForProgress } from '../components/atlas/mastery.constants';
import { XP_THRESHOLDS } from './achievements/skillTree.constants';
import { useState } from 'react';

export default function DesignShowcase() {
  return (
    <div className="max-w-5xl mx-auto px-4 md:px-6 py-8 space-y-10">
      {/* Header */}
      <header>
        <div className={headingScript + ' text-lg'}>
          Entry №01 · Hyrule Field Notes
        </div>
        <h1 className={headingDisplay + ' text-4xl md:text-5xl italic'}>
          Design Showcase
        </h1>
        <p className="font-body text-ink-secondary mt-2 max-w-prose">
          A visual QA page for every journal primitive. Navigate to{' '}
          <code className="font-rune text-sm">/__design</code> in dev to inspect
          the foundations before the rest of the app is reskinned.
        </p>
      </header>

      <DeckleDivider glyph="compass-rose" label="Typography" />

      <section className="grid md:grid-cols-2 gap-6">
        <ParchmentCard flourish>
          <h2 className="font-display text-2xl mb-1">Cormorant Garamond</h2>
          <p className="font-script text-ink-whisper text-sm">display — chapter titles, heroes</p>
          <p className="font-body text-base mt-3">
            The quick brown fox jumps over the lazy dog. <em>italic</em>,{' '}
            <strong>bold</strong>, and <span className="font-display italic">display italic</span>.
          </p>
        </ParchmentCard>
        <ParchmentCard>
          <h2 className="font-script text-3xl text-ink-primary">Caveat kicker</h2>
          <p className="font-body text-base mt-1 text-ink-secondary">
            Hand-lettered for dates, page numbers, asides.
          </p>
          <div className="font-rune text-sm mt-3 text-ember-deep">
            02:47:13 · $24.50 · 120🪙
          </div>
          <p className="font-script text-xs text-ink-whisper mt-1">
            Space Mono as rune tallies for numbers.
          </p>
        </ParchmentCard>
      </section>

      <DeckleDivider glyph="rune-orb" label="Palette" />

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ['ink-page', 'ink-primary'],
          ['ink-page-aged', 'ink-primary'],
          ['ink-page-shadow', 'ink-primary'],
          ['sheikah-teal', 'ink-primary'],
          ['sheikah-teal-deep', 'ink-page-rune-glow'],
          ['moss', 'ink-page-rune-glow'],
          ['ember', 'ink-page-rune-glow'],
          ['ember-deep', 'ink-page-rune-glow'],
          ['royal', 'ink-page-rune-glow'],
          ['gold-leaf', 'ink-primary'],
        ].map(([bg, fg]) => (
          <div
            key={bg}
            className={`rounded-lg border border-ink-page-shadow bg-${bg} text-${fg} p-3 text-center`}
          >
            <div className="font-rune text-xs">{bg}</div>
          </div>
        ))}
      </section>

      <DeckleDivider glyph="flourish-corner" label="Buttons" />

      <section className="flex flex-wrap gap-3">
        <Button size="sm">Wax-seal primary</Button>
        <Button variant="success" size="sm">Mossy success</Button>
        <Button variant="secondary" size="sm">Parchment secondary</Button>
        <Button variant="danger" size="sm">Ember danger</Button>
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
          <h3 className="font-display text-lg mt-1">Plain parchment</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Standard aged-paper panel with a hairline border.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" flourish>
          <div className="font-script text-ink-whisper text-xs">flourish</div>
          <h3 className="font-display text-lg mt-1">Flourished corners</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Decorative rune-flourish in each corner.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" seal>
          <div className="font-script text-ink-whisper text-xs">seal</div>
          <h3 className="font-display text-lg mt-1">Wax-sealed</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            A wax seal stamped in the corner.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" tone="bright">
          <div className="font-script text-ink-whisper text-xs">tone: bright</div>
          <h3 className="font-display text-lg mt-1">Bright parchment</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Lighter tone — use for hero/spotlight panels.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="plain" tone="deep">
          <div className="font-script text-ink-whisper text-xs">tone: deep</div>
          <h3 className="font-display text-lg mt-1">Deep parchment</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Deeper tone — for nested / quieter panels.
          </p>
        </ParchmentCard>

        <ParchmentCard variant="deckle">
          <div className="font-script text-ink-whisper text-xs">variant: deckle</div>
          <h3 className="font-display text-lg mt-1">Deckle edge</h3>
          <p className="font-body text-sm text-ink-secondary mt-1">
            Torn-paper edges via SVG mask. No border.
          </p>
        </ParchmentCard>
      </section>

      <DeckleDivider glyph="compass-rose" label="QuestLogEntry" />

      <ParchmentCard>
        <ul className="space-y-2">
          <QuestLogEntry
            title="Make bed"
            meta="Daily duty · due today"
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
            meta="Trial · expires in 2 days"
            reward="+25 XP · egg"
            kind="trial"
            tone="royal"
            status="pending"
            icon={<DragonIcon size={16} />}
          />
          <QuestLogEntry
            title="Sketch a dragon in under 10 min"
            meta="Habit · strength 4"
            reward="+1🪙"
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

      <section className="grid md:grid-cols-2 gap-4">
        <PartyCard
          pet={{ species_name: 'Ember Drake', potion_variant: 'fire', growth_points: 62 }}
          variant="compact"
        />
        <PartyCard
          pet={{ species_name: 'Tidebloom', potion_variant: 'water', growth_points: 18 }}
          variant="full"
          onFeed={() => alert('fed!')}
        />
        <PartyCard pet={null} />
      </section>

      <RuneBand projectTitle="Stained-glass dragon lantern" elapsedLabel="00:42:17" />

      <DeckleDivider glyph="rune-orb" label="Chapter icons" />

      <section className="flex flex-wrap gap-6 items-center text-ink-primary">
        <Labeled label="Today"><TodayIcon size={32} /></Labeled>
        <Labeled label="Quests"><QuestsIcon size={32} /></Labeled>
        <Labeled label="Bestiary"><BestiaryIcon size={32} /></Labeled>
        <Labeled label="Treasury"><TreasuryIcon size={32} /></Labeled>
        <Labeled label="Atlas"><AtlasIcon size={32} /></Labeled>
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

      <DeckleDivider glyph="sheikah-eye" label="Form primitives" />

      <ParchmentCard className="space-y-4">
        <TextField
          id="demo-text"
          label="What ventures are stirring today?"
          placeholder="Sketch a dragon, plan a campfire, ink a letter…"
          helpText="TextField — labeled input with helpText slot."
        />
        <SelectField
          id="demo-select"
          label="Pick a quest"
          helpText="SelectField — labeled select; pass <option> children directly."
        >
          <option value="">Choose…</option>
          <option value="dragon">Slay a dragon</option>
          <option value="forge">Forge a sword</option>
          <option value="map">Chart a map</option>
        </SelectField>
        <TextAreaField
          id="demo-textarea"
          label="Notes for the next traveller"
          rows={3}
          placeholder="Mind the embers near dusk…"
          helpText="TextAreaField — labeled textarea; rows defaults to 3."
        />
        <TextField
          id="demo-error"
          label="Field with error"
          defaultValue="invalid-input"
          error="This field has an error message wired through aria-describedby."
        />
      </ParchmentCard>

      <DeckleDivider glyph="dragon-crest" label="Skills · Tome Shelf & Folio" />

      <SkillsShowcase />

      <DeckleDivider glyph="dragon-crest" />

      <footer className="text-center font-script text-ink-whisper text-sm pt-2 pb-8">
        End of entry · {new Date().toLocaleDateString()}
      </footer>
    </div>
  );
}

const SHOWCASE_CATEGORIES = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Cooking', icon: '🍳' },
  { id: 3, name: 'Coding', icon: '💻' },
  { id: 4, name: 'Sewing', icon: '🧵' },
  { id: 5, name: 'Music', icon: '🎵' },
  { id: 6, name: 'Art', icon: '🎨' },
  { id: 7, name: 'Science', icon: '🔬' },
];

const SHOWCASE_SUMMARIES = {
  1: { level: 4, total_xp: 1800 },
  2: { level: 2, total_xp: 400 },
  3: { level: 5, total_xp: 1700 },
  4: { level: 1, total_xp: 120 },
  5: { level: 3, total_xp: 680 },
  6: { level: 0, total_xp: 40 },
  7: { level: 6, total_xp: 2500 },
};

function buildShowcaseTree(id) {
  const cat = SHOWCASE_CATEGORIES.find((c) => c.id === id) || SHOWCASE_CATEGORIES[0];
  const summary = SHOWCASE_SUMMARIES[cat.id];
  return {
    category: cat,
    summary,
    subjects: [
      {
        id: 100 + cat.id,
        name: 'Foundations',
        icon: '📐',
        summary: { level: Math.max(0, summary.level - 1), total_xp: Math.floor(summary.total_xp * 0.6) },
        skills: [
          {
            id: 1000 + cat.id,
            name: 'Measure & Mark',
            icon: '📏',
            level: 3,
            xp_points: 780,
            unlocked: true,
            level_names: { 1: 'Novice', 2: 'Journeyman', 3: 'Adept', 4: 'Master', 5: 'Virtuoso', 6: 'Grand Master' },
            prerequisites: [],
          },
          {
            id: 1001 + cat.id,
            name: 'Read a Plan',
            icon: '📜',
            level: 1,
            xp_points: 220,
            unlocked: true,
            level_names: { 1: 'Novice', 2: 'Journeyman' },
            prerequisites: [
              { skill_id: 1000 + cat.id, skill_name: 'Measure & Mark', required_level: 2, met: true },
            ],
          },
        ],
      },
      {
        id: 200 + cat.id,
        name: 'Techniques',
        icon: '🔨',
        summary: { level: summary.level, total_xp: Math.floor(summary.total_xp * 0.4) },
        skills: [
          {
            id: 2000 + cat.id,
            name: 'Dovetail Joint',
            icon: '🔗',
            level: 6,
            xp_points: 2500,
            unlocked: true,
            level_names: { 6: 'Grand Master' },
            prerequisites: [],
          },
          {
            id: 2001 + cat.id,
            name: 'Inlay Work',
            icon: '✨',
            level: 0,
            xp_points: 0,
            unlocked: false,
            level_names: { 0: 'Locked' },
            prerequisites: [
              { skill_id: 2000 + cat.id, skill_name: 'Dovetail Joint', required_level: 4, met: true },
              { skill_id: 9999, skill_name: 'Gilding (other category)', required_level: 3, met: false },
            ],
          },
        ],
      },
    ],
  };
}

function SkillsShowcase() {
  const [active, setActive] = useState(1);
  const [vesselActive, setVesselActive] = useState('potion');
  return (
    <section className="space-y-4">
      <div>
        <div className="font-script text-sheikah-teal-deep text-caption">
          atlas · tome shelf opens onto the folio
        </div>
        <h2 className={headingDisplay + ' italic text-2xl'}>Skills</h2>
      </div>

      <div className="flex items-center gap-6 flex-wrap">
        <Labeled label="locked">
          <IlluminatedVersal letter="L" progressPct={0} tier={PROGRESS_TIER.locked} />
        </Labeled>
        <Labeled label="nascent 10%">
          <IlluminatedVersal letter="N" progressPct={10} tier={PROGRESS_TIER.nascent} />
        </Labeled>
        <Labeled label="rising 45%">
          <IlluminatedVersal letter="R" progressPct={45} tier={PROGRESS_TIER.rising} />
        </Labeled>
        <Labeled label="cresting 75%">
          <IlluminatedVersal letter="C" progressPct={75} tier={PROGRESS_TIER.cresting} />
        </Labeled>
        <Labeled label="gilded 100%">
          <IlluminatedVersal letter="G" progressPct={100} tier={PROGRESS_TIER.gilded} />
        </Labeled>
      </div>

      <div>
        <div className="font-script text-ink-whisper text-caption mb-1">codex variant · book spines</div>
        <TomeShelf
          items={SHOWCASE_CATEGORIES.map((cat) => {
            const summary = SHOWCASE_SUMMARIES[cat.id];
            const totalXp = summary?.total_xp ?? 0;
            const shelfPct = Math.min(100, (totalXp / XP_THRESHOLDS[6]) * 100);
            return {
              id: cat.id,
              name: cat.name,
              icon: cat.icon,
              chip: `L${summary?.level ?? 0}`,
              progressPct: shelfPct,
              tier: tierForProgress({ unlocked: true, progressPct: shelfPct, level: summary?.level ?? 0 }),
            };
          })}
          activeId={active}
          onSelect={setActive}
          ariaLabel="Skill categories"
        />
      </div>

      <div>
        <div className="font-script text-ink-whisper text-caption mb-1">vessel variant · labeled drawers</div>
        <TomeShelf
          items={SHOWCASE_VESSELS}
          activeId={vesselActive}
          onSelect={setVesselActive}
          ariaLabel="Satchel compartments"
        />
      </div>

      <FolioSpread tree={buildShowcaseTree(active)} onSelectSkill={() => {}} />
    </section>
  );
}

const SHOWCASE_VESSELS = [
  { id: 'egg',       name: 'Eggs',           icon: '🥚', chip: '×4',  variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'potion',    name: 'Potions',        icon: '🧪', chip: '×42', variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'food',      name: 'Provisions',     icon: '🍎', chip: '×12', variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'frame',     name: 'Avatar Frames',  icon: '🖼', chip: '×3',  variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'title',     name: 'Titles',         icon: '✒', chip: '×7',  variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'scroll',    name: 'Quest Scrolls',  icon: '📜', chip: '×2',  variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
  { id: 'pouch',     name: 'Coin Pouches',   icon: '💰', chip: '×5',  variant: 'vessel', progressPct: null, tier: PROGRESS_TIER.nascent },
];

function Labeled({ label, children }) {
  return (
    <div className="flex flex-col items-center gap-1">
      {children}
      <span className="font-script text-xs text-ink-secondary">{label}</span>
    </div>
  );
}
