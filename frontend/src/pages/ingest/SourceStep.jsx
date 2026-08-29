import { FileText, Link as LinkIcon } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import TabButton from '../../components/TabButton';
import Button from '../../components/Button';
import { formLabelClass } from '../../constants/styles';
import { TextField } from '../../components/form';

export default function SourceStep({
  sourceTab, setSourceTab,
  url, setUrl,
  file, setFile,
  onStart,
  starting = false,
}) {
  const disabled = sourceTab === 'url' ? !url : !file;

  return (
    <ParchmentCard className="space-y-4">
      <div className="flex gap-2">
        <TabButton active={sourceTab === 'url'} onClick={() => setSourceTab('url')}>
          <span className="flex items-center gap-2"><LinkIcon size={14} /> URL</span>
        </TabButton>
        <TabButton active={sourceTab === 'pdf'} onClick={() => setSourceTab('pdf')}>
          <span className="flex items-center gap-2"><FileText size={14} /> PDF</span>
        </TabButton>
      </div>

      {sourceTab === 'url' ? (
        <TextField
          label="Tutorial URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          type="url"
          placeholder="https://www.instructables.com/... or any how-to page"
          helpText="Instructables links are parsed in full. Other sites are best-effort."
        />
      ) : (
        <div>
          <label className={formLabelClass}>PDF Tutorial</label>
          {/* intentional: raw <input type="file"> — the form primitives don't
              wrap file pickers, so the control keeps its file:* treatment.
              The colors are current tokens, not the legacy amber alias. */}
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-body text-ink-whisper file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-sheikah-teal-deep file:text-ink-page-rune-glow file:font-semibold"
          />
          {file && <p className="text-caption text-ink-whisper mt-1">{file.name}</p>}
        </div>
      )}

      {/* Starting an ingest POSTs a job that runs the paid LLM enrichment
          pipeline, so the button has to look busy the moment it is tapped —
          a phone upload on cellular takes seconds and every extra tap would
          queue another job. */}
      <Button
        onClick={onStart}
        disabled={disabled || starting}
        loading={starting}
        className="w-full"
      >
        {starting ? <span>Reading…</span> : 'Parse Source'}
      </Button>
    </ParchmentCard>
  );
}
