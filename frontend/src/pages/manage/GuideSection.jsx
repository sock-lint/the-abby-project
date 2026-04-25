import { getLorebook } from '../../api';
import { useApi } from '../../hooks/useApi';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import LorebookCodex from '../lorebook/LorebookCodex';

export default function GuideSection() {
  const { data, loading, error, reload } = useApi(getLorebook);

  if (loading) return <Loader />;
  if (error || !data) {
    return (
      <div className="space-y-3">
        <ErrorAlert message={error || 'Could not load the Lorebook guide.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <LorebookCodex
      entries={data.entries || []}
      mode="parent"
      showEconomyDiagram
      parentPanelsDefaultOpen
    />
  );
}
