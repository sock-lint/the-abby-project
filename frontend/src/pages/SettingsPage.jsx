import { useState, useEffect } from 'react';
import { LogOut, Link2, Unlink, Calendar, RefreshCw, Flame, Check } from 'lucide-react';
import {
  getGoogleAuthUrl, getGoogleAccount, unlinkGoogleAccount,
  updateCalendarSettings, triggerCalendarSync, updateMe,
} from '../api';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import { CoinIcon } from '../components/icons/JournalIcons';
import { useAuth } from '../hooks/useApi';
import { themes, applyTheme, LEGACY_THEME_ALIASES } from '../themes';
import { buttonPrimary } from '../constants/styles';

export default function SettingsPage() {
  const { user, logout: onLogout } = useAuth();
  const initialTheme = LEGACY_THEME_ALIASES[user?.theme] || user?.theme || 'hyrule';
  const [currentTheme, setCurrentTheme] = useState(initialTheme);

  const [googleAccount, setGoogleAccount] = useState(null);
  const [googleLoading, setGoogleLoading] = useState(true);
  const [calendarEnabled, setCalendarEnabled] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [googleMessage, setGoogleMessage] = useState('');

  useEffect(() => {
    loadGoogleAccount();
    const params = new URLSearchParams(window.location.search);
    const googleStatus = params.get('google');
    if (googleStatus === 'linked') {
      setGoogleMessage('Google account linked successfully.');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (googleStatus === 'error') {
      const detail = params.get('detail') || 'unknown';
      setGoogleMessage(`Google linking failed: ${detail}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const loadGoogleAccount = async () => {
    setGoogleLoading(true);
    try {
      const data = await getGoogleAccount();
      setGoogleAccount(data);
      if (data?.linked) setCalendarEnabled(data.calendar_sync_enabled || false);
    } catch {
      setGoogleAccount(null);
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleThemeChange = async (themeName) => {
    setCurrentTheme(themeName);
    applyTheme(themeName);
    try { await updateMe({ theme: themeName }); }
    catch { /* best-effort */ }
  };

  const handleLinkGoogle = async () => {
    try {
      const data = await getGoogleAuthUrl();
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch {
      setGoogleMessage('Could not start Google linking.');
    }
  };

  const handleUnlinkGoogle = async () => {
    try {
      await unlinkGoogleAccount();
      setGoogleAccount({ linked: false });
      setCalendarEnabled(false);
      setGoogleMessage('Google account unlinked.');
    } catch {
      setGoogleMessage('Failed to unlink Google account.');
    }
  };

  const handleToggleCalendar = async () => {
    const newVal = !calendarEnabled;
    try {
      await updateCalendarSettings({ calendar_sync_enabled: newVal });
      setCalendarEnabled(newVal);
    } catch {
      setGoogleMessage('Failed to update calendar settings.');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await triggerCalendarSync();
      setGoogleMessage('Calendar sync started.');
    } catch {
      setGoogleMessage('Failed to start sync.');
    } finally {
      setSyncing(false);
    }
  };

  const fieldLabel = 'font-script text-sm text-ink-whisper';
  const fieldValue = 'font-body text-ink-primary';

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          preferences · tune the journal
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Settings
        </h1>
      </header>

      {/* Profile */}
      <ParchmentCard>
        <h2 className="font-display text-xl text-ink-primary mb-4">Profile</h2>
        <div className="space-y-3">
          <div className="flex justify-between items-baseline text-sm">
            <span className={fieldLabel}>Username</span>
            <span className={fieldValue}>{user?.username}</span>
          </div>
          <div className="flex justify-between items-baseline text-sm">
            <span className={fieldLabel}>Display name</span>
            <span className={fieldValue}>{user?.display_name || '—'}</span>
          </div>
          <div className="flex justify-between items-baseline text-sm">
            <span className={fieldLabel}>Role</span>
            <RuneBadge tone="teal" size="sm">{user?.role}</RuneBadge>
          </div>
          <div className="flex justify-between items-baseline text-sm">
            <span className={fieldLabel}>Hourly rate</span>
            <span className="font-rune font-bold text-ink-primary tabular-nums">
              ${user?.hourly_rate}/hr
            </span>
          </div>
        </div>
      </ParchmentCard>

      {/* Google */}
      <ParchmentCard>
        <h2 className="font-display text-xl text-ink-primary mb-4">Google account</h2>
        {googleMessage && (
          <div className="font-script text-sm text-sheikah-teal-deep mb-3">{googleMessage}</div>
        )}
        {googleLoading ? (
          <div className="font-script text-sm text-ink-whisper">Loading…</div>
        ) : googleAccount?.linked ? (
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className={fieldLabel}>Linked to</span>
              <span className={fieldValue}>{googleAccount.google_email}</span>
            </div>
            <button
              type="button"
              onClick={handleUnlinkGoogle}
              className="flex items-center gap-2 font-script text-sm text-ember-deep hover:text-ember transition-colors"
            >
              <Unlink size={14} /> unlink Google account
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={handleLinkGoogle}
            className="flex items-center gap-2 w-full px-4 py-2.5 rounded-lg border border-ink-page-shadow text-ink-primary hover:border-sheikah-teal/60 hover:bg-ink-page-rune-glow transition-colors text-sm font-body"
          >
            <Link2 size={16} /> Connect Google account
          </button>
        )}
      </ParchmentCard>

      {/* Calendar Sync */}
      {googleAccount?.linked && (
        <ParchmentCard>
          <h2 className="font-display text-xl text-ink-primary mb-2">Calendar sync</h2>
          <p className="font-body text-sm text-ink-secondary mb-4">
            Sync project deadlines, chore schedules, and work sessions to your Google Calendar.
          </p>
          <div className="space-y-3">
            <label className="flex items-center justify-between cursor-pointer font-body text-sm text-ink-primary">
              <span className="flex items-center gap-2">
                <Calendar size={16} className="text-sheikah-teal-deep" />
                Enable calendar sync
              </span>
              <button
                type="button"
                onClick={handleToggleCalendar}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  calendarEnabled ? 'bg-sheikah-teal-deep' : 'bg-ink-page-shadow'
                }`}
                aria-pressed={calendarEnabled}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-ink-page-rune-glow transition-transform ${
                    calendarEnabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </label>
            {calendarEnabled && (
              <button
                type="button"
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 font-script text-sm text-sheikah-teal-deep hover:text-sheikah-teal disabled:opacity-50 transition-colors"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'syncing…' : 'sync now'}
              </button>
            )}
          </div>
        </ParchmentCard>
      )}

      {/* Journal covers (themes) */}
      <ParchmentCard>
        <div className="mb-2">
          <div className="font-script text-sm text-ink-whisper uppercase tracking-wider">
            pick a cover
          </div>
          <h2 className="font-display text-xl text-ink-primary leading-tight">Journal cover</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {Object.entries(themes).map(([key, theme]) => {
            const active = currentTheme === key;
            const t = theme.tones || {};
            return (
              <button
                key={key}
                type="button"
                onClick={() => handleThemeChange(key)}
                aria-pressed={active}
                aria-label={`Pick ${theme.name} cover`}
                className={`relative p-3 rounded-xl border-2 text-left transition-all ${
                  active
                    ? 'border-sheikah-teal-deep ring-2 ring-offset-2 ring-offset-ink-page ring-sheikah-teal-glow'
                    : 'border-ink-page-shadow hover:border-sheikah-teal/50'
                }`}
                style={{ backgroundColor: theme.page }}
              >
                {active && (
                  <span
                    className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-rune uppercase tracking-wider border"
                    style={{
                      color: theme.accent,
                      borderColor: theme.accent,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <Check size={10} strokeWidth={2.5} />
                    reading
                  </span>
                )}
                <div className="flex items-baseline gap-2">
                  <div className="text-2xl leading-none" aria-hidden>{theme.icon}</div>
                  <div
                    className="font-display text-base font-semibold leading-tight"
                    style={{ color: theme.ink }}
                  >
                    {theme.name}
                  </div>
                </div>
                <div
                  className="font-body text-xs mt-1.5 leading-snug"
                  style={{ color: theme.inkSecondary }}
                >
                  Ink the day&apos;s deeds here.
                </div>
                <div
                  className="font-script text-xs mt-0.5"
                  style={{ color: theme.inkWhisper }}
                >
                  — 6 chapters opened
                </div>
                <div className="flex items-center gap-1.5 mt-2.5">
                  <span
                    className="inline-flex items-center gap-1 h-6 px-1.5 rounded-full border text-[11px] font-rune tabular-nums"
                    style={{
                      color: t.emberDeep || theme.ember,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <Flame size={11} />
                    <span>7</span>
                  </span>
                  <span
                    className="inline-flex items-center gap-1 h-6 px-1.5 rounded-full border text-[11px] font-rune tabular-nums"
                    style={{
                      color: t.goldLeaf,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <CoinIcon size={11} />
                    <span>142</span>
                  </span>
                  <span
                    className="inline-flex items-center h-6 px-1.5 rounded-full border text-[11px] font-rune"
                    style={{
                      color: theme.accent,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    quest
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </ParchmentCard>

      {/* About */}
      <ParchmentCard>
        <h2 className="font-display text-xl text-ink-primary mb-2">About Hyrule Field Notes</h2>
        <p className="font-body text-sm text-ink-secondary">
          Chronicle ventures, rituals, and study. Ink hours, earn XP, unlock skills,
          collect coins, and grow the party.
        </p>
      </ParchmentCard>

      {/* Sign off */}
      <ParchmentCard>
        <h2 className="font-display text-xl text-ink-primary mb-4">Account</h2>
        <button
          type="button"
          onClick={onLogout}
          className={`${buttonPrimary} flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm`}
        >
          <LogOut size={16} /> Sign off
        </button>
      </ParchmentCard>
    </div>
  );
}
