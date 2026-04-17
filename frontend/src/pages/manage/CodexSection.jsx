import { useState } from 'react';
import { Package, PawPrint, Swords } from 'lucide-react';
import {
  getItemCatalog, getPetSpeciesCatalog, getQuestCatalog,
} from '../../api';
import { useApi } from '../../hooks/useApi';
import BottomSheet from '../../components/BottomSheet';
import Card from '../../components/Card';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import RpgSprite from '../../components/rpg/RpgSprite';
import {
  RARITY_COLORS, RARITY_TEXT_COLORS, RARITY_PILL_COLORS,
} from '../../constants/colors';
import { normalizeList } from '../../utils/api';

const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, epic: 3, legendary: 4 };

const ITEM_TYPE_LABELS = {
  egg: 'Pet Eggs',
  potion: 'Hatching Potions',
  food: 'Pet Food',
  cosmetic_frame: 'Avatar Frames',
  cosmetic_title: 'Titles',
  cosmetic_theme: 'Dashboard Themes',
  cosmetic_pet_accessory: 'Pet Accessories',
  quest_scroll: 'Quest Scrolls',
  coin_pouch: 'Coin Pouches',
};

// Keeps the item groups in a sensible reading order.
const ITEM_TYPE_ORDER = [
  'egg', 'potion', 'food',
  'cosmetic_frame', 'cosmetic_title', 'cosmetic_theme', 'cosmetic_pet_accessory',
  'quest_scroll', 'coin_pouch',
];

function groupBy(list, keyFn) {
  return list.reduce((acc, x) => {
    const k = keyFn(x);
    (acc[k] ||= []).push(x);
    return acc;
  }, {});
}

function sortByRarityName(a, b) {
  return (
    (RARITY_ORDER[a.rarity] ?? 99) - (RARITY_ORDER[b.rarity] ?? 99)
    || a.name.localeCompare(b.name)
  );
}

function CatalogCard({ rarity, icon, spriteKey, name, subtitle, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl p-3 text-center border cursor-pointer transition-transform hover:-translate-y-0.5 ${
        RARITY_COLORS[rarity] || 'border-ink-page-shadow bg-ink-page-aged/50'
      }`}
    >
      <div className="flex items-center justify-center h-12 mb-1">
        <RpgSprite spriteKey={spriteKey} icon={icon} size={40} alt={name} />
      </div>
      <div className="text-xs font-medium leading-tight text-ink-primary line-clamp-2">{name}</div>
      {subtitle && (
        <div className={`text-micro mt-1 capitalize ${RARITY_TEXT_COLORS[rarity] || 'text-ink-whisper'}`}>
          {subtitle}
        </div>
      )}
    </button>
  );
}

function CatalogGrid({ children }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
      {children}
    </div>
  );
}

function SectionHeader({ icon, title, count }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {icon}
      <h3 className="font-display text-lg font-bold text-ink-primary">{title}</h3>
      <span className="text-xs text-ink-whisper">({count})</span>
    </div>
  );
}

/* ── Items ───────────────────────────────────────────────────────── */

function ItemsBlock({ items, onSelect }) {
  const grouped = groupBy(items, (i) => i.item_type);
  const orderedTypes = ITEM_TYPE_ORDER.filter((t) => grouped[t]?.length);

  if (!items.length) {
    return <EmptyState>No items authored yet. Add entries to content/rpg/initial/items.yaml.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      {orderedTypes.map((itemType) => {
        const rows = [...grouped[itemType]].sort(sortByRarityName);
        return (
          <div key={itemType}>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="font-display text-sm font-semibold text-ink-secondary uppercase tracking-wide">
                {ITEM_TYPE_LABELS[itemType] || itemType}
              </h4>
              <span className="text-tiny text-ink-whisper">({rows.length})</span>
            </div>
            <CatalogGrid>
              {rows.map((item) => (
                <CatalogCard
                  key={item.id}
                  rarity={item.rarity}
                  icon={item.icon}
                  spriteKey={item.sprite_key}
                  name={item.name}
                  subtitle={item.rarity_display}
                  onClick={() => onSelect(item)}
                />
              ))}
            </CatalogGrid>
          </div>
        );
      })}
    </div>
  );
}

function ItemDetail({ item }) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center h-16 mb-3">
        <RpgSprite spriteKey={item.sprite_key} icon={item.icon} size={64} alt={item.name} />
      </div>
      <div className={`text-sm capitalize font-medium mb-1 ${RARITY_TEXT_COLORS[item.rarity]}`}>
        {item.rarity_display} · {item.type_display}
      </div>
      {item.description && (
        <p className="text-sm text-ink-whisper mb-3">{item.description}</p>
      )}
      <div className="space-y-1 text-xs text-ink-secondary">
        {item.coin_value > 0 && (
          <div>Salvage value: <span className="text-gold-leaf font-semibold">{item.coin_value} coins</span></div>
        )}
        {item.pet_species_name && (
          <div>Hatches: <span className="text-ink-primary font-semibold">{item.pet_species_name}</span></div>
        )}
        {item.potion_type_name && (
          <div>Potion variant: <span className="text-ink-primary font-semibold">{item.potion_type_name}</span></div>
        )}
        {item.food_species_name && (
          <div>Preferred by: <span className="text-ink-primary font-semibold">{item.food_species_name}</span></div>
        )}
        {item.metadata && Object.keys(item.metadata).length > 0 && (
          <details className="mt-3 text-left">
            <summary className="cursor-pointer text-ink-whisper">Metadata</summary>
            <pre className="mt-2 p-2 bg-ink-page-aged/50 rounded text-micro overflow-x-auto">
              {JSON.stringify(item.metadata, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

/* ── Creatures ───────────────────────────────────────────────────── */

function CreaturesBlock({ species, onSelect }) {
  if (!species.length) {
    return <EmptyState>No pet species authored yet. Add entries to content/rpg/initial/pet_species.yaml.</EmptyState>;
  }
  return (
    <CatalogGrid>
      {species.map((s) => (
        <CatalogCard
          key={s.id}
          rarity="common" // species don't have rarity — neutral framing
          icon={s.icon}
          spriteKey={s.sprite_key}
          name={s.name}
          onClick={() => onSelect(s)}
        />
      ))}
    </CatalogGrid>
  );
}

function CreatureDetail({ species }) {
  const potions = species.available_potions || [];
  return (
    <div className="text-center">
      <div className="flex items-center justify-center h-16 mb-3">
        <RpgSprite spriteKey={species.sprite_key} icon={species.icon || '🐾'} size={64} alt={species.name} />
      </div>
      {species.description && (
        <p className="text-sm text-ink-whisper mb-3">{species.description}</p>
      )}
      <div className="space-y-2 text-xs text-ink-secondary">
        {species.food_preference && (
          <div>Preferred food: <span className="text-ink-primary font-semibold">{species.food_preference}</span></div>
        )}
        <div>
          <div className="mb-1 font-medium text-ink-secondary">
            Compatible potions ({potions.length}):
          </div>
          {potions.length === 0 ? (
            <div className="italic text-ink-whisper">All potions compatible (no restrictions declared)</div>
          ) : (
            <div className="flex flex-wrap gap-2 justify-center">
              {potions.map((p) => (
                <span
                  key={p.id}
                  className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-tiny ${
                    RARITY_PILL_COLORS[p.rarity] || 'bg-ink-page-aged/60 text-ink-secondary'
                  }`}
                >
                  <span
                    className="w-3 h-3 rounded-full border border-ink-page-shadow"
                    style={{ backgroundColor: p.color_hex || '#888' }}
                  />
                  {p.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Adventures (Quests) ─────────────────────────────────────────── */

function AdventuresBlock({ quests, onSelect }) {
  if (!quests.length) {
    return <EmptyState>No quests authored yet. Add entries to content/rpg/initial/quests.yaml.</EmptyState>;
  }
  return (
    <CatalogGrid>
      {quests.map((q) => (
        <CatalogCard
          key={q.id}
          rarity="rare" // neutral shared accent; quests don't carry a rarity field
          icon={q.icon}
          spriteKey={q.sprite_key}
          name={q.name}
          subtitle={q.quest_type_display}
          onClick={() => onSelect(q)}
        />
      ))}
    </CatalogGrid>
  );
}

function AdventureDetail({ quest }) {
  const rewards = quest.reward_items || [];
  return (
    <div className="text-center">
      <div className="flex items-center justify-center h-16 mb-3">
        <RpgSprite spriteKey={quest.sprite_key} icon={quest.icon || '⚔️'} size={64} alt={quest.name} />
      </div>
      <div className="text-sm capitalize font-medium mb-2 text-royal">
        {quest.quest_type_display} · Target {quest.target_value}
      </div>
      {quest.description && (
        <p className="text-sm text-ink-whisper mb-3">{quest.description}</p>
      )}
      <div className="space-y-1 text-xs text-ink-secondary">
        <div>Duration: <span className="text-ink-primary font-semibold">{quest.duration_days} days</span></div>
        {quest.coin_reward > 0 && (
          <div>Coin reward: <span className="text-gold-leaf font-semibold">{quest.coin_reward}</span></div>
        )}
        {quest.xp_reward > 0 && (
          <div>XP reward: <span className="text-sheikah-teal-deep font-semibold">{quest.xp_reward}</span></div>
        )}
        {rewards.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 font-medium text-ink-secondary">Reward items:</div>
            <div className="flex flex-wrap gap-2 justify-center">
              {rewards.map((r) => (
                <span
                  key={r.id}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-tiny bg-ink-page-aged/60 text-ink-primary"
                >
                  <RpgSprite
                    spriteKey={r.item_sprite_key}
                    icon={r.item_icon}
                    size={24}
                    alt={r.item_name}
                  />
                  {r.item_name} ×{r.quantity}
                </span>
              ))}
            </div>
          </div>
        )}
        {quest.trigger_filter && Object.keys(quest.trigger_filter).length > 0 && (
          <details className="mt-3 text-left">
            <summary className="cursor-pointer text-ink-whisper">Trigger filter</summary>
            <pre className="mt-2 p-2 bg-ink-page-aged/50 rounded text-micro overflow-x-auto">
              {JSON.stringify(quest.trigger_filter, null, 2)}
            </pre>
          </details>
        )}
        <div className="mt-2 text-ink-whisper italic">
          {quest.is_system ? 'System quest' : 'Custom quest'}
          {quest.is_repeatable ? ' · repeatable' : ''}
        </div>
      </div>
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────── */

export default function CodexSection() {
  const { data: itemsData, loading: itemsLoading, error: itemsError } = useApi(getItemCatalog);
  const { data: speciesData, loading: speciesLoading, error: speciesError } = useApi(getPetSpeciesCatalog);
  const { data: questsData, loading: questsLoading, error: questsError } = useApi(getQuestCatalog);

  const items = normalizeList(itemsData);
  const species = normalizeList(speciesData);
  const quests = normalizeList(questsData);

  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedSpecies, setSelectedSpecies] = useState(null);
  const [selectedQuest, setSelectedQuest] = useState(null);

  const loading = itemsLoading || speciesLoading || questsLoading;
  const error = itemsError || speciesError || questsError;

  return (
    <div className="space-y-6">
      <Card>
        <p className="text-sm text-ink-secondary">
          Behind-the-scenes audit of every RPG entry currently loaded from{' '}
          <code className="text-xs px-1.5 py-0.5 bg-ink-page-aged rounded">content/rpg/</code>{' '}
          YAML. The kids discover these organically — this page is for your reference only.
        </p>
      </Card>

      {error && <ErrorAlert error={error} />}
      {loading && <Loader />}

      {!loading && !error && (
        <>
          <Card>
            <SectionHeader
              icon={<Package size={18} className="text-sheikah-teal-deep" />}
              title="Items"
              count={items.length}
            />
            <ItemsBlock items={items} onSelect={setSelectedItem} />
          </Card>

          <Card>
            <SectionHeader
              icon={<PawPrint size={18} className="text-sheikah-teal-deep" />}
              title="Creatures"
              count={species.length}
            />
            <CreaturesBlock species={species} onSelect={setSelectedSpecies} />
          </Card>

          <Card>
            <SectionHeader
              icon={<Swords size={18} className="text-sheikah-teal-deep" />}
              title="Adventures"
              count={quests.length}
            />
            <AdventuresBlock quests={quests} onSelect={setSelectedQuest} />
          </Card>
        </>
      )}

      {selectedItem && (
        <BottomSheet title={selectedItem.name} onClose={() => setSelectedItem(null)}>
          <ItemDetail item={selectedItem} />
        </BottomSheet>
      )}
      {selectedSpecies && (
        <BottomSheet title={selectedSpecies.name} onClose={() => setSelectedSpecies(null)}>
          <CreatureDetail species={selectedSpecies} />
        </BottomSheet>
      )}
      {selectedQuest && (
        <BottomSheet title={selectedQuest.name} onClose={() => setSelectedQuest(null)}>
          <AdventureDetail quest={selectedQuest} />
        </BottomSheet>
      )}
    </div>
  );
}
