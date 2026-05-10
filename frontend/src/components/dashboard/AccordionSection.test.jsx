import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AccordionSection from './AccordionSection';

describe('AccordionSection', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders collapsed by default with kicker, title, and peek', () => {
    render(
      <AccordionSection title="Treasury" kicker="peek here" peek="Balance $10">
        <div>body text</div>
      </AccordionSection>,
    );
    expect(screen.getByRole('heading', { name: /treasury/i })).toBeInTheDocument();
    expect(screen.getByText(/peek here/i)).toBeInTheDocument();
    expect(screen.getByText(/balance \$10/i)).toBeInTheDocument();
    // Body is not yet mounted while collapsed.
    expect(screen.queryByText(/body text/i)).not.toBeInTheDocument();
  });

  it('expands on click and reveals body', async () => {
    const user = userEvent.setup();
    render(
      <AccordionSection title="Hoard" peek="one goal">
        <div>body text</div>
      </AccordionSection>,
    );
    await user.click(screen.getByRole('button', { expanded: false }));
    expect(screen.getByText(/body text/i)).toBeInTheDocument();
  });

  it('renders an atlas chapter numeral when index is supplied', () => {
    render(
      <AccordionSection index={2} title="Hoard" peek="one goal">
        <div>body text</div>
      </AccordionSection>,
    );
    expect(screen.getByText('§III')).toBeInTheDocument();
  });

  it('omits the chapter numeral when no index is supplied', () => {
    render(
      <AccordionSection title="Hoard" peek="one goal">
        <div>body text</div>
      </AccordionSection>,
    );
    expect(screen.queryByText(/^§/)).toBeNull();
  });

  it('persists open state per-title via localStorage', async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <AccordionSection title="Treasury" peek="$10">
        <div>body</div>
      </AccordionSection>,
    );
    await user.click(screen.getByRole('button', { expanded: false }));
    expect(localStorage.getItem('dashboard-accordion-treasury')).toBe('1');
    unmount();

    render(
      <AccordionSection title="Treasury" peek="$10">
        <div>body</div>
      </AccordionSection>,
    );
    // Should remount already open, body mounted immediately.
    expect(screen.getByText(/body/i)).toBeInTheDocument();
  });
});
