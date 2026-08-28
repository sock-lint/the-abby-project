import { PulseContext } from '../providers/pulseContext';

/**
 * MockPulse — drives the shared heartbeat directly in tests.
 *
 * The toast hooks derive from each new pulse object, so a test "beats" by
 * re-rendering with a new payload (RTL's `rerender`). Much simpler than the
 * fake-timer polling these tests needed when every hook owned its own
 * interval. Fixtures live in ./pulseFixtures.js.
 */
export default function MockPulse({ pulse = null, refresh = () => {}, children }) {
  return (
    <PulseContext.Provider value={{ pulse, refresh }}>
      {children}
    </PulseContext.Provider>
  );
}
