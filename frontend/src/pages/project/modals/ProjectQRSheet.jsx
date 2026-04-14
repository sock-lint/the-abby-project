import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { getProjectQR } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import Loader from '../../../components/Loader';

export default function ProjectQRSheet({ projectId, projectTitle, onClose }) {
  const [qrUrl, setQrUrl] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let revoked = false;
    let currentUrl = null;
    (async () => {
      try {
        const blob = await getProjectQR(projectId);
        if (revoked) return;
        currentUrl = URL.createObjectURL(blob);
        setQrUrl(currentUrl);
      } catch {
        if (!revoked) setQrUrl(null);
      } finally {
        if (!revoked) setLoading(false);
      }
    })();
    return () => {
      revoked = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [projectId]);

  return (
    <BottomSheet title="Project QR Code" onClose={onClose}>
      <div className="flex flex-col items-center gap-4">
        {loading ? (
          <Loader />
        ) : qrUrl ? (
          <>
            <img
              src={qrUrl}
              alt={`QR code for ${projectTitle}`}
              className="w-64 h-64 rounded-lg"
            />
            <a
              href={qrUrl}
              download={`project-${projectId}-qr.png`}
              className="flex items-center gap-1.5 text-sm text-amber-500 hover:underline"
            >
              <Download size={16} /> Save Image
            </a>
          </>
        ) : (
          <p className="text-forge-text-dim text-sm">Failed to load QR code.</p>
        )}
      </div>
    </BottomSheet>
  );
}
