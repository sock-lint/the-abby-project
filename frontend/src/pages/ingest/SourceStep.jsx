import { FileText, Link as LinkIcon } from 'lucide-react';
import Card from '../../components/Card';
import TabButton from '../../components/TabButton';
import Button from '../../components/Button';
import { formLabelClass } from '../../constants/styles';
import { TextField } from '../../components/form';

export default function SourceStep({
  sourceTab, setSourceTab,
  url, setUrl,
  file, setFile,
  onStart,
}) {
  const disabled = sourceTab === 'url' ? !url : !file;

  return (
    <Card className="space-y-4">
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
          {/* Raw <input type="file"> stays — file picker has custom file:* tailwind treatment, not inputClass */}
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-ink-whisper file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-primary file:text-black file:font-semibold"
          />
          {file && <p className="text-xs text-ink-whisper mt-1">{file.name}</p>}
        </div>
      )}

      <Button onClick={onStart} disabled={disabled} className="w-full">
        Parse Source
      </Button>
    </Card>
  );
}
