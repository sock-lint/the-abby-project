import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import OverviewTab from './OverviewTab.jsx';
import { buildProject } from '../../test/factories.js';

describe('OverviewTab', () => {
  it('renders description and Instructables link', () => {
    render(
      <OverviewTab
        project={buildProject({ description: 'Do cool thing', instructables_url: 'https://x' })}
        isParent={false}
      />,
    );
    expect(screen.getByText('Do cool thing')).toBeInTheDocument();
    expect(screen.getByText(/view on instructables/i)).toBeInTheDocument();
  });

  it('omits optional sections when absent', () => {
    render(<OverviewTab project={buildProject({ description: '', instructables_url: null })} />);
    expect(screen.queryByText(/view on instructables/i)).toBeNull();
  });
});
