import { useState } from 'react'
import BottomSheet from '../../components/BottomSheet'
import Button from '../../components/Button'
import { TextField, TextAreaField } from '../../components/form'
import { createManualChronicleEntry } from '../../api'
import { toISODate } from '../../utils/dates'

export default function ManualEntryFormModal({ userId, onClose, onCreated }) {
  const [form, setForm] = useState({ title: '', summary: '', occurred_on: '' })
  const [saving, setSaving] = useState(false)
  const today = toISODate(new Date())

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await createManualChronicleEntry({
        user_id: userId,
        title: form.title,
        summary: form.summary,
        occurred_on: form.occurred_on,
      })
      onCreated?.(res)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <BottomSheet title="Add memory" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3 p-4">
        <TextField
          label="Title"
          required
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
        />
        <TextField
          type="date"
          label="When"
          required
          max={today}
          helpText="Memories live in the past — pick today or earlier."
          value={form.occurred_on}
          onChange={(e) => setForm((f) => ({ ...f, occurred_on: e.target.value }))}
        />
        <TextAreaField
          label="Summary"
          value={form.summary}
          onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  )
}
