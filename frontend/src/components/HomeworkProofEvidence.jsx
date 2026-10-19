import { ExternalLink } from 'lucide-react';
import ProofGallery from './ProofGallery';
import { getHomeworkProofUrl } from '../utils/homeworkProof';

export default function HomeworkProofEvidence({ proofs = [], proofUrl }) {
  const url = getHomeworkProofUrl(proofUrl);
  if (!proofs.length && !url) return null;

  return (
    <div className="space-y-2 min-w-0">
      <ProofGallery proofs={proofs} />
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center gap-2 rounded-lg font-body text-body font-semibold text-ink-primary underline underline-offset-2 break-words [overflow-wrap:anywhere]"
        >
          <ExternalLink size={16} className="shrink-0" aria-hidden="true" />
          <span>Open proof link <span className="font-normal">({new URL(url).hostname})</span><span className="sr-only"> (opens in a new tab)</span></span>
        </a>
      )}
    </div>
  );
}
