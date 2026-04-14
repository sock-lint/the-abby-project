import { FileText, Link as LinkIcon } from 'lucide-react';
import Card from '../../components/Card';
import TabButton from '../../components/TabButton';
import { buttonPrimary, inputClass } from '../../constants/styles';

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
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Tutorial URL</label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className={inputClass}
            type="url"
            placeholder="https://www.instructables.com/... or any how-to page"
          />
          <p className="text-xs text-forge-text-dim mt-1">
            Instructables links are parsed in full. Other sites are best-effort.
          </p>
        </div>
      ) : (
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">PDF Tutorial</label>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-forge-text-dim file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-primary file:text-black file:font-semibold"
          />
          {file && <p className="text-xs text-forge-text-dim mt-1">{file.name}</p>}
        </div>
      )}

      <button
        type="button"
        onClick={onStart}
        disabled={disabled}
        className={`w-full py-2.5 ${buttonPrimary}`}
      >
        Parse Source
      </button>
    </Card>
  );
}
