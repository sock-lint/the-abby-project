import { useEffect, useRef, useState } from 'react';
import { FileUp } from 'lucide-react';
import Button from '../Button';
import useFieldIds from '../form/useFieldIds';
import { formLabelClass, formHelpClass, formErrorClass } from '../../constants/styles';
import { formatFileSize } from './attachmentHelpers';

// Selection is local only. The owning form keeps its validation, processing
// and upload contract; this field never starts or retries a network request.
export default function AttachmentField({
  label, file, onChange, accept, helpText, error, disabled = false,
  previewImage = false, chooseLabel, id: idProp,
}) {
  const inputRef = useRef(null);
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });
  const pick = () => inputRef.current?.click();
  const select = (event) => {
    const selected = event.target.files?.[0];
    event.target.value = ''; // The same file can be selected again after removal.
    if (selected) onChange(selected);
  };
  const remove = () => {
    if (inputRef.current) inputRef.current.value = '';
    onChange(null);
  };
  return <div className="space-y-2 min-w-0">
    <label htmlFor={id} className={formLabelClass}>{label}</label>
    <input ref={inputRef} id={id} type="file" accept={accept} disabled={disabled}
      onChange={select} aria-invalid={error ? 'true' : undefined}
      aria-describedby={describedBy} className="hidden" />
    {previewImage && file && <ImagePreview file={file} label={label} />}
    <div role="status" aria-live="polite" className="text-body text-ink-secondary break-words [overflow-wrap:anywhere]">
      {file ? <><span className="font-semibold text-ink-primary">{file.name}</span><span className="block text-caption">{formatFileSize(file.size)}</span></> : 'No file selected'}
    </div>
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={pick} disabled={disabled} aria-describedby={describedBy}
        className="inline-flex items-center gap-2">
        <FileUp size={16} aria-hidden="true" />
        {file ? `Replace ${label.toLowerCase()}` : chooseLabel || `Choose ${label.toLowerCase()}`}
      </Button>
      {file && <Button variant="ghost" onClick={remove} disabled={disabled} aria-label={`Remove ${label.toLowerCase()}`}>Remove</Button>}
    </div>
    {helpText && <p id={helpId} className={formHelpClass}>{helpText}</p>}
    {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
  </div>;
}

function ImagePreview({ file, label }) {
  const [preview, setPreview] = useState(null);
  const [failedFile, setFailedFile] = useState(null);
  useEffect(() => {
    let active = true;
    let url;
    try { url = URL.createObjectURL(file); } catch { return undefined; }
    // Defer the update so a replaced file never briefly inherits an old URL.
    queueMicrotask(() => { if (active) setPreview({ file, url }); });
    return () => {
      active = false;
      URL.revokeObjectURL?.(url);
    };
  }, [file]);
  if (failedFile === file) return <p className={formHelpClass}>Preview unavailable. The selected file is still attached.</p>;
  if (preview?.file !== file) return null;
  return <img src={preview.url} alt={`${label} preview`} onError={() => setFailedFile(file)}
    className="w-full max-h-48 object-contain rounded-lg border border-ink-page-shadow bg-ink-page" />;
}
