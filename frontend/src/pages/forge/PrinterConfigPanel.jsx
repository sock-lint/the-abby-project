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

const BLANK = {
  name: '', serial: '', model_name: 'X1C', transport: 'local',
  host: '', port: 8883, is_active: true,
  access_code: '', cloud_user_id: '', cloud_token: '',
};

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

  const set = (key) => (e) => setForm((f) => ({
    ...f,
    [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  }));

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    setSaving(true);
    setError('');
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
      setError(err?.message || 'Could not save that printer.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={printer ? 'Edit printer' : 'Add a printer'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <TextField id="forge-printer-name" label="Name" value={form.name} onChange={set('name')} placeholder="X1C in the garage" />
        <TextField id="forge-printer-serial" label="Serial" value={form.serial} onChange={set('serial')} helpText="Forms the MQTT topic the listener subscribes to." />
        <TextField id="forge-printer-model" label="Model" value={form.model_name} onChange={set('model_name')} placeholder="X1C" />
        <SelectField id="forge-printer-transport" label="Transport" value={form.transport} onChange={set('transport')}>
          <option value="local">Local MQTT (LAN)</option>
          <option value="cloud">Bambu Cloud MQTT</option>
        </SelectField>
        {form.transport === 'local' ? (
          <>
            <TextField id="forge-printer-host" label="Host" value={form.host} onChange={set('host')} placeholder="192.168.1.42" />
            <TextField id="forge-printer-port" label="Port" type="number" value={form.port} onChange={set('port')} />
            <TextField
              id="forge-printer-code"
              label="Access code"
              type="password"
              autoComplete="off"
              value={form.access_code}
              onChange={set('access_code')}
              helpText={printer ? 'Leave blank to keep the stored code.' : 'From the printer’s network settings.'}
            />
          </>
        ) : (
          <>
            <TextField id="forge-printer-cloud-user" label="Cloud user id" value={form.cloud_user_id} onChange={set('cloud_user_id')} />
            <TextField
              id="forge-printer-cloud-token"
              label="Cloud token"
              type="password"
              autoComplete="off"
              value={form.cloud_token}
              onChange={set('cloud_token')}
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
 * `has_credentials` (a boolean) and nothing else, so a leaked response body
 * can't hand anyone the printer's LAN access code or a Bambu cloud token.
 * The form mirrors that — blank credential fields on an edit mean "keep what
 * is stored", not "clear it".
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
