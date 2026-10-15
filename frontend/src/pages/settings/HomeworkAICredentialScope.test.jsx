import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import HomeworkAISettings from './HomeworkAISettings';

vi.mock('../../hooks/useApi', () => ({ useAuth: () => ({ user: { id: 1, role: 'child' } }) }));

describe('Homework AI credential scope', () => {
  it('does not crash child settings when browser randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', { randomUUID: undefined });
    try {
      expect(() => render(<HomeworkAISettings />)).not.toThrow();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
