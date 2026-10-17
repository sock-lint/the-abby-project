import { getGreenlightOverview } from '../../api';
import { useApi } from '../../hooks/useApi';
import BottomSheet from '../../components/BottomSheet';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import GreenlightTransferForm from './GreenlightTransferForm';

// Reuse the completed-transfer workflow and its saved retry identity. Opening
// a weekly payment never settles money before the parent's confirmation.
export default function TimecardTransferSheet({ timecard, ownerKey, onClose, onSaved }) {
  const { data, loading, error, reload } = useApi(
    (signal) => getGreenlightOverview(timecard.user, signal), [timecard.user],
  );
  const kidName = timecard.username || 'this child';
  if (!loading && !error && data?.approved_timecards?.some((card) => card.id === timecard.id)) {
    return <GreenlightTransferForm userId={timecard.user} kidName={kidName} overview={data}
      ownerKey={ownerKey} initialTimecardId={timecard.id} onClose={onClose} onSaved={onSaved} />;
  }
  return <BottomSheet title={`Record a Greenlight transfer for ${kidName}`} onClose={onClose}>
    {loading ? <Loader /> : <div className="space-y-3">
      <ErrorAlert message={error || 'This timecard is no longer ready for payment. Refresh its payment details before continuing.'} />
      <Button variant="secondary" onClick={reload}>Refresh payment details</Button>
    </div>}
  </BottomSheet>;
}
