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
import {
  buttonPrimary, buttonSecondary, buttonDanger, buttonSuccess, buttonGhost,
  inputClass, headingDisplay, headingScript,
} from '../constants/styles';

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
        <button className={buttonPrimary + ' px-4 py-2 text-sm'}>Wax-seal primary</button>
        <button className={buttonSuccess + ' px-4 py-2 text-sm'}>Mossy success</button>
        <button className={buttonSecondary + ' px-4 py-2 text-sm'}>Parchment secondary</button>
        <button className={buttonDanger + ' px-4 py-2 text-sm'}>Ember danger</button>
        <button className={buttonGhost + ' px-4 py-2 text-sm'}>Ghost action</button>
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
            meta="Daily ritual · due today"
            reward="$0.50 · 3🪙"
            kind="ritual"
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

      <DeckleDivider glyph="sheikah-eye" label="Form input" />

      <ParchmentCard>
        <label className="block font-script text-sm text-ink-secondary mb-1" htmlFor="demo-input">
          What ventures are stirring today?
        </label>
        <input
          id="demo-input"
          className={inputClass}
          placeholder="Sketch a dragon, plan a campfire, ink a letter…"
        />
      </ParchmentCard>

      <DeckleDivider glyph="dragon-crest" />

      <footer className="text-center font-script text-ink-whisper text-sm pt-2 pb-8">
        End of entry · {new Date().toLocaleDateString()}
      </footer>
    </div>
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
