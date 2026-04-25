import { getLorebook } from '../api';
import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { useApi } from '../hooks/useApi';
import LorebookCodex from './lorebook/LorebookCodex';

export default function Lorebook() {
  const { data, loading, error, reload } = useApi(getLorebook);

  if (loading) return <Loader />;
  if (error || !data) {
    return (
      <div className="space-y-3">
        <ErrorAlert message={error || 'Could not load your Lorebook.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <LorebookCodex
      entries={data.entries || []}
      mode="kid"
      showEconomyDiagram={false}
      parentPanelsDefaultOpen={false}
    />
  );
}
