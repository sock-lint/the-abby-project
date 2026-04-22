import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'

import Button from './Button'
import { markChronicleViewed } from '../api'
import candlePng from '../assets/birthday-candle-placeholder.png'

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

export default function BirthdayCelebrationModal({ entry, onDismiss }) {
  const titleId = useId()
  const reduced = usePrefersReducedMotion()
  const [leaving, setLeaving] = useState(false)

  // Extract age from the title (e.g. "Turned 15"); fallback empty string.
  const ageMatch = /\d+/.exec(entry.title || '')
  const age = ageMatch ? ageMatch[0] : ''
  const gift = entry.metadata?.gift_coins ?? 0

  const dismiss = async () => {
    setLeaving(true)
    try {
      await markChronicleViewed(entry.id)
    } finally {
      onDismiss?.()
    }
  }

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
        <img src={candlePng} alt="" aria-hidden="true" className="mx-auto h-16 w-16" />
        <h2 id={titleId} className="mt-4 font-serif text-2xl text-ink-primary">
          Happy birthday
        </h2>
        <motion.div
          initial={reduced ? {} : { scale: 0 }}
          animate={{ scale: 1 }}
          transition={reduced ? { duration: 0 } : { delay: 0.3, duration: 0.4 }}
          className="mt-4 text-6xl font-serif text-gold-leaf"
        >
          {age}
        </motion.div>
        {gift > 0 && (
          <p className="mt-4 text-body text-ink-secondary">🎁 {gift} coins added to your treasury</p>
        )}
        {!reduced && (
          <div
            data-testid="birthday-confetti"
            aria-hidden="true"
            className="pointer-events-none absolute inset-0"
          >
            {/* Confetti particles (framer-motion). MVP: simple visual flourish. */}
          </div>
        )}
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
