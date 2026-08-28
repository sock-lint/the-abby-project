import { useState } from 'react';
import { Plus, Printer, Trash2 } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import ModalActions from '../../components/ModalActions';
import { CheckboxField, SelectField, TextField } from '../../components/form';
import { createPrinter, deletePrinter, updatePrinter } from '../../api';
import { fieldErrors } from '../../utils/api';

const BLANK = {
  name: '', serial: '', model_name: 'X1C', transport: 'local',
  host: '', port: 8883, is_active: true,
  access_code: '', cloud_user_id: '', cloud_token: '',
};

/** Keys with an input in this form, so a 400 on anything else still surfaces. */
const FORM_FIELDS = Object.keys(BLANK);

function PrinterForm({ printer, onClose, onSaved }) {
  const [form, setForm] = useState(() => (printer ? {
    ...BLANK,
    name: printer.name || '',
    serial: printer.serial || '',
    model_name: printer.model_name || 'X1C',
    transport: printer.transport || 'local',
    host: printer.host || '',
    port: printer.port ?? 8883,
    is_active: printer.is_active !== false,
  } : BLANK));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState({});

  const set = (key) => (e) => {
    // Clear this field's server-side complaint as soon as it's being answered
    // — leaving it under the input while the parent types reads as if the
    // new value were rejected too.
    setFieldError(({ [key]: _cleared, ...rest }) => rest);
    setForm((f) => ({
      ...f,
      [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
    }));
  };

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    setSaving(true);
    setError('');
    setFieldError({});
    try {
      const payload = {
        name: form.name.trim(),
        serial: form.serial.trim(),
        model_name: form.model_name.trim(),
        transport: form.transport,
        host: form.host.trim(),
        port: Number(form.port) || 8883,
        is_active: form.is_active,
      };
      // Credentials are write-only and merge-on-omit server-side, so an
      // edit that leaves them blank keeps whatever is already stored rather
      // than wiping the access code. Only send what was actually typed.
      if (form.transport === 'cloud') {
        if (form.cloud_user_id.trim()) payload.cloud_user_id = form.cloud_user_id.trim();
        if (form.cloud_token.trim()) payload.cloud_token = form.cloud_token.trim();
      } else if (form.access_code.trim()) {
        payload.access_code = form.access_code.trim();
      }
      if (printer) await updatePrinter(printer.id, payload);
      else await createPrinter(payload);
      onSaved?.();
      onClose?.();
    } catch (err) {
      // A missing access code comes back as {access_code: [...]}, so put it
      // under the access code input rather than dumping the raw body into
      // the banner. Anything the form doesn't render an input for still has
      // to be readable, so it falls through to the banner.
      const fields = fieldErrors(err);
      const orphan = Object.entries(fields).find(([key]) => !FORM_FIELDS.includes(key));
      setFieldError(fields);
      setError(
        orphan?.[1]
        || (Object.keys(fields).length ? '' : err?.message)
        || 'Could not save that printer.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={printer ? 'Edit printer' : 'Add a printer'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <TextField id="forge-printer-name" label="Name" value={form.name} onChange={set('name')} placeholder="X1C in the garage" error={fieldError.name} />
        <TextField id="forge-printer-serial" label="Serial" value={form.serial} onChange={set('serial')} error={fieldError.serial} helpText="Forms the MQTT topic the listener subscribes to." />
        <TextField id="forge-printer-model" label="Model" value={form.model_name} onChange={set('model_name')} placeholder="X1C" />
        <SelectField id="forge-printer-transport" label="Transport" value={form.transport} onChange={set('transport')}>
          <option value="local">Local MQTT (LAN)</option>
          <option value="cloud">Bambu Cloud MQTT</option>
        </SelectField>
        {form.transport === 'local' ? (
          <>
            <TextField id="forge-printer-host" label="Host" value={form.host} onChange={set('host')} placeholder="192.168.1.42" error={fieldError.host} />
            <TextField id="forge-printer-port" label="Port" type="number" value={form.port} onChange={set('port')} />
            <TextField
              id="forge-printer-code"
              label="Access code"
              type="password"
              autoComplete="off"
              value={form.access_code}
              onChange={set('access_code')}
              error={fieldError.access_code}
              helpText={printer
                ? 'Leave blank to keep the stored code.'
                : 'Eight digits, on the printer’s screen under Settings → Network.'}
            />
          </>
        ) : (
          <>
            <TextField id="forge-printer-cloud-user" label="Cloud user id" value={form.cloud_user_id} onChange={set('cloud_user_id')} error={fieldError.cloud_user_id} />
            <TextField
              id="forge-printer-cloud-token"
              label="Cloud token"
              type="password"
              autoComplete="off"
              value={form.cloud_token}
              onChange={set('cloud_token')}
              error={fieldError.cloud_token}
              helpText={printer ? 'Leave blank to keep the stored token.' : undefined}
            />
          </>
        )}
        <CheckboxField
          id="forge-printer-active"
          label="Listen to this printer"
          checked={form.is_active}
          onChange={set('is_active')}
        />
        {error && <ErrorAlert message={error} />}
        <ModalActions
          onClose={onClose}
          saving={saving}
          submitLabel={printer ? 'Save printer' : 'Add printer'}
        />
      </form>
    </BottomSheet>
  );
}

/**
 * PrinterConfigPanel — parent-only printer registry.
 *
 * Credentials go in and never come back out: the read serializer exposes
 * whether they are set (`has_credentials`), which fields are still blank
 * (`missing_credentials` / `credential_hint`) and never the values, so a
 * leaked response body can't hand anyone the printer's LAN access code or a
 * Bambu cloud token. The form mirrors that — blank credential fields on an
 * edit mean "keep what is stored", not "clear it".
 *
 * The server refuses to save a printer whose credentials are incomplete, so
 * the failure lands as an inline error on the field that is blank while the
 * parent is still looking at the form. The hint on the card is for printers
 * that predate that rule.
 */
export default function PrinterConfigPanel({ printers, onChanged }) {
  const [editing, setEditing] = useState(null); // 'new' | printer object
  const [pendingDelete, setPendingDelete] = useState(null);
  const [error, setError] = useState('');

  const remove = async () => {
    try {
      await deletePrinter(pendingDelete.id);
      setPendingDelete(null);
      onChanged?.();
    } catch (err) {
      setError(err?.message || 'Could not remove that printer.');
      setPendingDelete(null);
    }
  };

  return (
    <div className="space-y-3">
      <ErrorAlert message={error} />
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setEditing('new')} className="flex items-center gap-1">
          <Plus size={14} /> Add printer
        </Button>
      </div>

      {(!printers || printers.length === 0) ? (
        <EmptyState icon={<Printer size={24} />}>
          No printer registered yet. Add one so the listener can watch it.
        </EmptyState>
      ) : (
        printers.map((printer) => (
          <ParchmentCard key={printer.id} className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="font-display text-base text-ink-primary truncate">{printer.name}</div>
              <div className="font-script text-caption text-ink-whisper truncate">
                {printer.serial} · {printer.transport_display || printer.transport}
                {printer.host ? ` · ${printer.host}` : ''}
              </div>
              {/* The badge alone is a dead end — it says something is wrong
                  without saying what, and the fix is hidden behind Edit.
                  `credential_hint` names the blank field; `last_error` is the
                  listener's own complaint, which only matters once the
                  credentials are actually there. */}
              {(printer.credential_hint || printer.last_error) && (
                <div className="font-body text-caption text-ember-deep mt-1">
                  {printer.credential_hint || printer.last_error}
                </div>
              )}
            </div>
            <RuneBadge tone={printer.has_credentials ? 'moss' : 'ember'}>
              {printer.has_credentials ? 'Ready' : 'No credentials'}
            </RuneBadge>
            <Button variant="ghost" size="sm" onClick={() => setEditing(printer)}>Edit</Button>
            <IconButton
              aria-label={`Remove ${printer.name}`}
              onClick={() => setPendingDelete(printer)}
            >
              <Trash2 size={16} />
            </IconButton>
          </ParchmentCard>
        ))
      )}

      {editing && (
        <PrinterForm
          printer={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={onChanged}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Remove this printer?"
          message="The listener stops watching it, and every job it recorded goes with it. Budget entries stay."
          confirmLabel="Remove"
          onConfirm={remove}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
