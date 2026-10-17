import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LogOut, Link2, Unlink, Calendar, RefreshCw, Check,
  Lock,
} from 'lucide-react';
import {
  getGoogleAccount, unlinkGoogleAccount,
  updateCalendarSettings, triggerCalendarSync,
  getCosmetics, equipCosmetic,
} from '../api';
import { getToken } from '../api/client';
import DeckleDivider from '../components/journal/DeckleDivider';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import ErrorAlert from '../components/ErrorAlert';
import SectionHeader from '../components/SectionHeader';
import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';
import { useAuth } from '../hooks/useApi';
import { themes, applyTheme, LEGACY_THEME_ALIASES } from '../themes';
import { cosmeticLockHint } from './character/character.constants';
import { isCatalogAvailable } from '../utils/catalogAvailability';
import Button from '../components/Button';
import { ToggleField } from '../components/form';
import InstallCard from '../pwa/InstallCard';
import PushNotificationsCard from '../pwa/PushNotificationsCard';
import HomeworkAISettings from './settings/HomeworkAISettings';
import useGoogleAuthorization from '../hooks/useGoogleAuthorization';
import { takeGoogleLinkResult } from '../auth/googleOAuth';

// Auto-dismiss window for transient Google-account status banners. Long
// enough to read but short enough that the user doesn't come back to
// the page hours later wondering why "Calendar sync started." is still
// shouting at them.
const GOOGLE_MESSAGE_DISMISS_MS = 5000;

export default function SettingsPage() {
  const { user, logout: onLogout, setUser } = useAuth();
  const googleAuthorization = useGoogleAuthorization({ mode: 'link', actor: user });
  const { hash } = useLocation();
  const appearanceRef = useRef(null);
  const homeworkAIRef = useRef(null);
  useEffect(() => {
    if (hash === '#appearance') appearanceRef.current?.scrollIntoView({ block: 'start' });
    if (hash === '#homework-ai') homeworkAIRef.current?.scrollIntoView({ block: 'start' });
  }, [hash, user?.id]);
  const initialTheme = LEGACY_THEME_ALIASES[user?.theme] || user?.theme || 'hyrule';
  const [currentTheme, setCurrentTheme] = useState(initialTheme);

  // Owned journal covers, keyed by theme slug (e.g. ``hyrule``). The map
  // is built from the user's ``/api/cosmetics/`` active_theme slot —
  // legacy ``theme-*`` cosmetics without a ``metadata.theme`` linking to
  // a palette in themes.js are intentionally filtered out so the picker
  // only surfaces journal covers that actually swap the visible binding.
  const [ownedByTheme, setOwnedByTheme] = useState(null);
  const [coversLoading, setCoversLoading] = useState(true);
  const [coverEquipping, setCoverEquipping] = useState(null); // theme slug
  const [coverError, setCoverError] = useState('');
  const [coverLoadError, setCoverLoadError] = useState('');
  const equippingRef = useRef(false);
  const mountedRef = useRef(true);
  const coverRequestRef = useRef(0);
  const userRef = useRef(user);
  userRef.current = user;
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      coverRequestRef.current += 1;
    };
  }, []);

  const [googleAccount, setGoogleAccount] = useState(null);
  const [googleLoading, setGoogleLoading] = useState(true);
  const [calendarEnabled, setCalendarEnabled] = useState(false);
  const [syncing, setSyncing] = useState(false);
  // Successes and failures are kept apart on purpose. They used to share one
  // decorative teal script line, so "Failed to unlink Google account." read
  // exactly like "Google account linked successfully."
  const [googleMessage, setGoogleMessage] = useState('');
  const [googleError, setGoogleError] = useState('');
  // Calendar failures get their own slot so the alert lands in the card
  // that holds the toggle rather than one card up.
  const [calendarError, setCalendarError] = useState('');

  const loadGoogleAccount = useCallback(async () => {
    if (!user?.id) return;
    const token = getToken();
    const actorId = user?.id;
    const familyId = user?.family?.id;
    const current = () => mountedRef.current && getToken() === token
      && userRef.current?.id === actorId && userRef.current?.family?.id === familyId;
    setGoogleLoading(true);
    try {
      const data = await getGoogleAccount();
      if (!current()) return;
      setGoogleAccount(data);
      if (data?.linked) setCalendarEnabled(data.calendar_sync_enabled || false);
    } catch {
      if (!current()) return;
      setGoogleAccount(null);
    } finally {
      if (current()) setGoogleLoading(false);
    }
  }, [user?.id, user?.family?.id]);

  useEffect(() => { void loadGoogleAccount(); }, [loadGoogleAccount]);

  useEffect(() => {
    loadCovers();
    const result = takeGoogleLinkResult();
    if (result?.error) setGoogleError(result.error);
    else if (result) setGoogleMessage('Google account linked successfully.');
    const params = new URLSearchParams(window.location.search);
    const googleStatus = params.get('google');
    if (googleStatus === 'linked') {
      setGoogleMessage('Google account linked successfully.');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (googleStatus === 'error') {
      const detail = params.get('detail') || 'unknown';
      setGoogleError(`Google linking failed: ${detail}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  // Keep the picker's active swatch in lockstep with the auth user.
  // The server-saved account palette determines the selected theme.
  useEffect(() => {
    const resolved = LEGACY_THEME_ALIASES[user?.theme] || user?.theme;
    if (resolved && themes[resolved]) {
      setCurrentTheme(resolved);
    }
  }, [user?.theme]);

  // Auto-dismiss transient Google status banners. Only successes live in
  // ``googleMessage`` now, so this no longer has to sniff the copy for the
  // word "failed" — failures go to ``googleError`` and stay until the user
  // navigates or the next attempt lands.
  useEffect(() => {
    if (!googleMessage) return undefined;
    const timer = setTimeout(() => setGoogleMessage(''), GOOGLE_MESSAGE_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [googleMessage]);

  const loadCovers = async () => {
    const token = getToken();
    const requestId = ++coverRequestRef.current;
    const isCurrentLoad = () => mountedRef.current && getToken() === token
      && requestId === coverRequestRef.current;
    setCoversLoading(true);
    setCoverLoadError('');
    try {
      const data = await getCosmetics();
      if (!isCurrentLoad()) return;
      if (!Array.isArray(data?.active_theme)) throw new Error('Missing color themes');
      const themeItems = data.active_theme;
      const map = {};
      for (const item of themeItems) {
        const slug = item?.metadata?.theme;
        if (slug && themes[slug]) {
          map[slug] = item;
        }
      }
      setOwnedByTheme(map);
    } catch {
      if (isCurrentLoad()) {
        setCoverLoadError('Could not load your color themes. Your saved theme has not changed.');
      }
    } finally {
      if (isCurrentLoad()) setCoversLoading(false);
    }
  };


  const handleThemeChange = async (themeName) => {
    const owned = ownedByTheme?.[themeName];
    if (!owned || !isCatalogAvailable(owned) || themeName === currentTheme
      || coversLoading || coverLoadError || equippingRef.current || !user) return;
    const token = getToken();
    const userId = user.id;
    const isCurrentAccount = () => mountedRef.current
      && getToken() === token && userRef.current?.id === userId;
    equippingRef.current = true;
    setCoverError('');
    setCoverEquipping(themeName);
    // Optimistic local swap so the swatch + page paint feel instant; we
    // roll back on equip failure.
    const prevTheme = currentTheme;
    setCurrentTheme(themeName);
    applyTheme(themeName);
    try {
      await equipCosmetic(owned.id);
      if (!isCurrentAccount()) return;
      setUser((current) => {
        if (current?.id !== userId || getToken() !== token) return current;
        return {
          ...current,
          theme: themeName,
          character_profile: current.character_profile
            ? { ...current.character_profile, active_theme_id: owned.id }
            : current.character_profile,
        };
      });
    } catch (err) {
      if (!isCurrentAccount()) return;
      setCurrentTheme(prevTheme);
      applyTheme(prevTheme);
      setCoverError(err?.message || 'Could not change your color theme. Try again.');
    } finally {
      equippingRef.current = false;
      if (isCurrentAccount()) setCoverEquipping(null);
    }
  };

  const handleUnlinkGoogle = async () => {
    setGoogleError('');
    try {
      await unlinkGoogleAccount();
      setGoogleAccount({ linked: false });
      setCalendarEnabled(false);
      setGoogleMessage('Google account unlinked.');
    } catch {
      setGoogleError('Failed to unlink Google account.');
    }
  };

  const handleToggleCalendar = async () => {
    const newVal = !calendarEnabled;
    setCalendarError('');
    try {
      await updateCalendarSettings({ calendar_sync_enabled: newVal });
      setCalendarEnabled(newVal);
    } catch {
      // The toggle snaps back on its own (calendarEnabled never moved) —
      // the ember alert is what tells the parent why.
      setCalendarError('Failed to update calendar settings. The toggle was left as it was.');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setCalendarError('');
    try {
      await triggerCalendarSync();
      setGoogleMessage('Calendar sync started.');
    } catch {
      setCalendarError('Failed to start sync.');
    } finally {
      setSyncing(false);
    }
  };

  const ownedCount = useMemo(
    () => Object.keys(themes).filter((key) => ownedByTheme?.[key]).length,
    [ownedByTheme],
  );

  const fieldLabel = 'shrink-0 font-script text-body text-ink-whisper';
  const fieldValue = 'min-w-0 break-words text-right font-body text-ink-primary';

  return (
    <PageShell width="narrow" rhythm="loose">
      <PageHeader title="Settings" kicker="Your account and app preferences" />

      {/* Account details */}
      <ParchmentCard>
        <SectionHeader index={0} title="Account details" className="mb-4" />
        <div className="space-y-3">
          <div className="flex justify-between items-baseline gap-3 text-body">
            <span className={fieldLabel}>Username</span>
            <span className={fieldValue}>{user?.username}</span>
          </div>
          <div className="flex justify-between items-baseline gap-3 text-body">
            <span className={fieldLabel}>Display name</span>
            <span className={fieldValue}>{user?.display_name || '—'}</span>
          </div>
          <div className="flex justify-between items-baseline gap-3 text-body">
            <span className={fieldLabel}>Role</span>
            <RuneBadge tone="teal" size="sm">{user?.role}</RuneBadge>
          </div>
          <div className="flex justify-between items-baseline gap-3 text-body">
            <span className={fieldLabel}>Hourly rate</span>
            <span className="font-rune font-bold text-ink-primary tabular-nums">
              ${user?.hourly_rate}/hr
            </span>
          </div>
          <p className="font-body text-caption text-ink-secondary">
            Your profile has your picture, character and earned cosmetics.
          </p>
          <Link to="/sigil" className="inline-flex min-h-11 items-center text-body underline underline-offset-4 text-sheikah-teal-deep">
            View profile
          </Link>
        </div>
      </ParchmentCard>

      {/* Use the inline check rather than ``useRole`` so we don't fork the
          ``useAuth`` context already destructured above for ``setUser`` /
          ``logout``. ``useRole`` is preferred when those aren't needed. */}
      {user?.role === 'parent' && user?.family && (
        <ParchmentCard>
          <SectionHeader index={1} title="Family" kicker="your household" className="mb-2" />
          <div className="font-display text-base text-ink-primary break-words">
            {user.family.name}
          </div>
          <div className="font-script text-ink-whisper text-caption mt-1">
            Accounts and family activity belong to this household.
          </div>
        </ParchmentCard>
      )}

      {/* Earned journal covers supply the app's account-scoped color themes. */}
      <ParchmentCard id="appearance" ref={appearanceRef} className="scroll-mt-24">
        <SectionHeader index={2} title="Appearance" className="mb-2" />
        <h3 className="font-body font-semibold text-ink-primary">Color theme</h3>
        <p className="font-body text-body text-ink-secondary mt-1">
          Choose the colors used throughout the app. Your choice is saved to your account.
          Earned journal covers unlock more themes.
        </p>
        {coverError && <ErrorAlert message={coverError} className="mt-2" />}
        {coverLoadError && (
          <div className="mt-3 space-y-3">
            <ErrorAlert message={coverLoadError} />
            <Button size="sm" variant="secondary" onClick={loadCovers} disabled={coversLoading}>
              Retry color themes
            </Button>
          </div>
        )}
        {coversLoading && (
          <p role="status" aria-busy="true" className="font-body text-body text-ink-whisper mt-3">
            Loading your color themes…
          </p>
        )}
        {ownedByTheme && !coverLoadError && !coversLoading && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3" data-testid="cover-picker" aria-busy={Boolean(coverEquipping)}>
              {Object.entries(themes).map(([key, theme]) => {
                const owned = ownedByTheme[key];
                const active = owned && currentTheme === key;
                const equipping = coverEquipping === key;

                if (!owned || !isCatalogAvailable(owned)) {
                  return (
                    <div
                      key={key}
                      role="img"
                      aria-label={`${theme.name} color theme · ${owned ? 'saved, currently unavailable' : 'not yet earned'}`}
                      data-testid={`cover-locked-${key}`}
                      className="relative p-3 rounded-xl border-2 border-dashed border-ink-page-shadow text-left bg-ink-page-aged/60"
                      style={{ filter: 'grayscale(0.85)' }}
                    >
                      <span
                        aria-hidden
                        className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-micro font-rune uppercase tracking-wider border border-ink-page-shadow bg-ink-page-aged text-ink-whisper"
                      >
                        <Lock size={10} strokeWidth={2.5} />
                        {owned ? 'saved' : 'locked'}
                      </span>
                      <div className="flex items-baseline gap-2 pr-20 opacity-70">
                        <div className="shrink-0 text-2xl leading-none" aria-hidden>{theme.icon}</div>
                        <div className="min-w-0 break-words font-display text-base font-semibold leading-tight text-ink-whisper">
                          {theme.name}
                        </div>
                      </div>
                      <div className="font-script text-caption mt-2 italic leading-snug text-ink-whisper/80 line-clamp-2">
                        {owned
                          ? 'This saved theme is currently unavailable.'
                          : cosmeticLockHint({ description: '', rarity: 'uncommon' })}
                      </div>
                    </div>
                  );
                }

                return (
                  <Button
                    variant="secondary"
                    key={key}
                    type="button"
                    onClick={() => handleThemeChange(key)}
                    disabled={Boolean(coverEquipping) || !user}
                    aria-pressed={active}
                    aria-label={`Choose ${theme.name} color theme`}
                    data-testid={`cover-owned-${key}`}
                    className={`relative p-3 rounded-xl border-2 text-left transition-all disabled:opacity-70 ${
                      active
                        ? 'border-sheikah-teal-deep ring-2 ring-offset-2 ring-offset-ink-page ring-sheikah-teal-glow'
                        : 'border-ink-page-shadow hover:border-sheikah-teal/50'
                    }`}
                    style={{ backgroundColor: theme.page }}
                  >
                    {active && (
                      <span
                        className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-micro font-rune uppercase tracking-wider border"
                        style={{
                          color: theme.accent,
                          borderColor: theme.accent,
                          backgroundColor: theme.pageAged,
                        }}
                      >
                        <Check size={10} strokeWidth={2.5} />
                        {equipping ? 'Saving…' : 'Selected'}
                      </span>
                    )}
                    <div className={`flex items-baseline gap-2 ${active ? 'pr-20' : ''}`}>
                      <div className="shrink-0 text-2xl leading-none" aria-hidden>{theme.icon}</div>
                      <div
                        className="min-w-0 break-words font-display text-base font-semibold leading-tight"
                        style={{ color: theme.ink }}
                      >
                        {theme.name}
                      </div>
                    </div>
                    <div
                      className="font-body text-caption mt-1.5 leading-snug"
                      style={{ color: theme.inkSecondary }}
                    >
                      Keep track of your day.
                    </div>
                    <div
                      className="font-script text-caption mt-0.5"
                      style={{ color: theme.inkWhisper }}
                    >
                      Your progress, all in one place
                    </div>
                  </Button>
                );
              })}
            </div>
            <div className="mt-3 font-script text-caption text-ink-whisper">
              {ownedCount} of {Object.keys(themes).length} themes owned —{' '}
              <Link to="/sigil" className="underline decoration-dotted hover:text-sheikah-teal-deep">
                View earned cosmetics
              </Link>
            </div>
          </>
        )}
      </ParchmentCard>

      <DeckleDivider glyph="flourish-corner" className="my-2" />

      <InstallCard />
      <PushNotificationsCard />

      <HomeworkAISettings sectionRef={homeworkAIRef} />

      {/* Google */}
      <ParchmentCard>
        <SectionHeader index={user?.role === 'parent' ? 4 : 3} title="Google account" kicker="connect a calendar" className="mb-4" />
        <p className="font-body text-body text-ink-secondary mb-3">
          Use Add to calendar beside a saved deadline or scheduled return to open Google Calendar
          or download an Apple Calendar (.ics) file. Chores let you choose a reminder date.
          These are one-time copies; later date changes need to be updated in your calendar.
          You can use them without connecting a Google account.
        </p>
        <p className="font-body text-caption text-ink-whisper mb-4">
          On a Mac, open the downloaded file in Calendar or choose File → Import.
          Events added to an iCloud calendar also appear on your other Apple devices.
        </p>
        {(googleError || googleAuthorization.error) && <ErrorAlert message={googleError || googleAuthorization.error} className="mb-3" />}
        {googleMessage && (
          <div className="font-script text-body text-sheikah-teal-deep mb-3">{googleMessage}</div>
        )}
        {googleLoading ? (
          <div className="font-script text-body text-ink-whisper">Loading…</div>
        ) : googleAccount?.linked ? (
          <div className="space-y-3">
            <div className="flex justify-between items-center gap-3 text-body">
              <span className={fieldLabel}>Linked to</span>
              <span className={fieldValue}>{googleAccount.google_email}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleUnlinkGoogle}
              className="flex items-center gap-2 font-script text-body text-ember-deep hover:text-ember"
            >
              <Unlink size={14} /> unlink Google account
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            onClick={() => { setGoogleError(''); void googleAuthorization.start(); }}
            disabled={googleAuthorization.busy}
            className="flex items-center gap-2 w-full"
          >
            <Link2 size={16} /> Connect Google account
          </Button>
        )}
      </ParchmentCard>

      {/* Calendar Sync */}
      {googleAccount?.linked && (
        <ParchmentCard>
          <SectionHeader index={user?.role === 'parent' ? 5 : 4} title="Calendar sync" kicker="weave the dates in" className="mb-2" />
          <p className="font-body text-body text-ink-secondary mb-4">
            Sync project deadlines, chore schedules, and work sessions to your Google Calendar.
          </p>
          {calendarError && <ErrorAlert message={calendarError} className="mb-3" />}
          <div className="space-y-3">
            <ToggleField
              checked={calendarEnabled}
              onChange={handleToggleCalendar}
              labelNode={
                <span className="flex items-center gap-2">
                  <Calendar size={16} className="text-sheikah-teal-deep" />
                  Enable calendar sync
                </span>
              }
              className="flex items-center justify-between [&>div]:w-full [&>div]:justify-between"
            />
            {calendarEnabled && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 font-script text-body text-sheikah-teal-deep hover:text-sheikah-teal"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'syncing…' : 'sync now'}
              </Button>
            )}
          </div>
        </ParchmentCard>
      )}

      {/* About */}
      <ParchmentCard>
        <SectionHeader index={user?.role === 'parent' ? 6 : 5} title="About The Abby Project" className="mb-2" />
        <p className="font-body text-body text-ink-secondary">
          Track projects, chores, habits, and homework. Log time, build skills,
          earn coins, and care for your pets.
        </p>
      </ParchmentCard>

      {/* Sign off */}
      <ParchmentCard>
        <SectionHeader index={user?.role === 'parent' ? 7 : 6} title="Account" className="mb-4" />
        <Button
          size="sm"
          onClick={onLogout}
          className="flex items-center justify-center gap-2 w-full"
        >
          <LogOut size={16} /> Sign out
        </Button>
      </ParchmentCard>
    </PageShell>
  );
}
