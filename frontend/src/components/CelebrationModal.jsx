import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { Flame, Sun } from 'lucide-react'

import Button from './Button'
import { markNotificationRead } from '../api'

function usePrefersReducedMotion() {
  const [pref, setPref] = useState(() =>
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mql = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mql) return
    const handler = (e) => setPref(e.matches)
    mql.addEventListener?.('change', handler)
    return () => mql.removeEventListener?.('change', handler)
  }, [])
  return pref
}

// Title from the streak notification looks like "🔥 30-day streak!" — the
// first integer is the streak day count.
function parseStreakDays(title) {
  const m = /\d+/.exec(title || '')
  return m ? parseInt(m[0], 10) : null
}

function StreakBody({ days }) {
  return (
    <>
      <Flame
        size={56}
        className="mx-auto text-ember-deep"
        aria-hidden="true"
      />
      <h2 className="mt-3 font-serif text-2xl text-ink-primary">
        {days} day streak!
      </h2>
      <p className="mt-2 text-body text-ink-secondary">
        You've been showing up day after day — keep the flame alive.
      </p>
    </>
  )
}

function PerfectDayBody() {
  return (
    <>
      <Sun
        size={56}
        className="mx-auto text-gold-leaf"
        aria-hidden="true"
      />
      <h2 className="mt-3 font-serif text-2xl text-ink-primary">
        Perfect day
      </h2>
      <p className="mt-2 text-body text-ink-secondary">
        Every duty done. Today's page glows.
      </p>
      <p className="mt-3 text-caption text-gold-leaf">+15 coins · perfect day</p>
    </>
  )
}

export default function CelebrationModal({ notification, onDismiss }) {
  const titleId = useId()
  const reduced = usePrefersReducedMotion()
  const [leaving, setLeaving] = useState(false)

  const isStreak = notification.notification_type === 'streak_milestone'
  const isPerfectDay = notification.notification_type === 'perfect_day'
  const days = isStreak ? parseStreakDays(notification.title) : null

  const dismiss = async () => {
    setLeaving(true)
    try {
      await markNotificationRead(notification.id)
    } finally {
      onDismiss?.()
    }
  }

  // Unknown celebration type — render nothing rather than a broken modal.
  if (!isStreak && !isPerfectDay) return null

  const content = (
    <div
      role="alertdialog"
      aria-labelledby={titleId}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <div className="absolute inset-0 bg-[rgba(204,170,92,0.25)] backdrop-blur-sm" />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.85, rotateY: -20 }}
        animate={{ opacity: 1, scale: 1, rotateY: 0 }}
        exit={{ opacity: 0 }}
        transition={reduced ? { duration: 0.15 } : { duration: 0.6 }}
        className="relative parchment-bg-aged p-8 text-center max-w-sm w-full rounded-2xl"
      >
        <div id={titleId} className="sr-only">
          {notification.title}
        </div>
        {isStreak && days != null && <StreakBody days={days} />}
        {isPerfectDay && <PerfectDayBody />}
        <div className="mt-6">
          <Button variant="primary" onClick={dismiss} disabled={leaving}>
            Turn the page →
          </Button>
        </div>
      </motion.div>
    </div>
  )

  return createPortal(content, document.body)
}
