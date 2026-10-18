import { describe, expect, it } from 'vitest';
import { useState } from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import ProgressionExperimentNotebook from './ProgressionExperimentNotebook';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { selectDropdown } from '../../test/selectDropdown';
import listing from '../../../../contracts/api/fixtures/progression-experiment-list.json';
import comparison from '../../../../contracts/api/fixtures/progression-experiment-comparison.json';
import decided from '../../../../contracts/api/fixtures/progression-experiment-decided.json';
import observations from '../../../../contracts/api/fixtures/progression-observations-empty.json';
import observed from '../../../../contracts/api/fixtures/progression-experiment-observed.json';
const root = '/api/rpg/progression-lab/experiments/';
const draft = { ...decided, latest_decision: null, comparisons: [], decisions: [] };
const setup = (detail = draft, evidence = comparison) => server.use(
  http.get(`*${root}`, () => HttpResponse.json(listing)),
  http.get(`*${root}${draft.id}/`, () => HttpResponse.json(detail)),
  http.get(`*${root}${draft.id}/comparisons/${comparison.id}/`, () => HttpResponse.json(evidence)),
  http.get('*/api/rpg/progression-lab/observations/', () => HttpResponse.json(observations)),
);
async function open(user) {
  await selectDropdown(user, await screen.findByRole('combobox', { name: 'Open experiment' }), draft.id);
  await screen.findByText('Saved experiment loaded.');
}
describe('Progression experiment notebook', () => {
  it('saves only anonymous inputs and runs server-generated control and candidate', async () => {
    setup();
    const create = spyHandler('post', new RegExp(`${root}$`), draft);
    const run = spyHandler('post', new RegExp(`${root}${draft.id}/compare/$`), comparison);
    server.use(create.handler, run.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await screen.findByRole('combobox', { name: 'Open experiment' });
    await user.click(screen.getByRole('button', { name: 'Add criterion' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Criterion 1 minimum' }), { target: { value: '0' } });
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByText('Experiment saved. Live rewards are unchanged.');
    expect(create.calls[0].body).toMatchObject({ config: { ...draft.config, reward_budget: { daily_coins: null } }, candidate_daily_coins: 100, targets: [{ metric: 'coins_earned_p50', min: 0, max: null }] });
    expect(Object.keys(create.calls[0].body).sort()).toEqual(['candidate_daily_coins', 'candidate_expedition_budget', 'candidate_policy', 'config', 'hypothesis', 'name', 'targets']);
    await user.click(screen.getByRole('button', { name: 'Run control and candidate' }));
    await screen.findByRole('region', { name: 'Saved experiment comparison' });
    expect(run.calls[0].body).toEqual({ revision: 1 });
    expect(screen.getByText('No eligible new-user Coin observations yet.')).toBeVisible();
    expect(screen.getByText(/Available as an opt-in Lab prototype/)).toBeVisible();
  });
  it('saves the fixed commitment candidate and resets both control policies', async () => {
    setup();
    const create = spyHandler('post', new RegExp(`${root}$`), { ...draft, candidate_policy: 'commitment100' });
    server.use(create.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={{ ...draft.config, reward_commitment: { enabled: true }, reward_budget: { daily_coins: 50 } }} />);
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Candidate reward policy' }), 'commitment100');
    expect(screen.getByRole('spinbutton', { name: 'Candidate Coins per child per day' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByText('Experiment saved. Live rewards are unchanged.');
    expect(create.calls[0].body).toMatchObject({ candidate_policy: 'commitment100', candidate_daily_coins: 100, config: { reward_commitment: { enabled: false }, reward_budget: { daily_coins: null } } });
  });
  it('saves an expedition-only hypothesis with matching Coin rules and explicit candidate limits', async () => {
    setup();
    const quota = { daily_launches: null, daily_items: null };
    server.use(http.get(`*${root}`, () => HttpResponse.json({ ...listing, feedback: { ...listing.feedback, expedition_budget_defaults: quota, expedition_budget_limits: { daily_launches: { min: 0, max: 15 }, daily_items: { min: 0, max: 45 } } } })));
    const create = spyHandler('post', new RegExp(`${root}$`), { ...draft, candidate_policy: 'expedition_limits', candidate_daily_coins: null, candidate_expedition_budget: { daily_launches: null, daily_items: 3 } });
    server.use(create.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={{ ...draft.config, reward_commitment: { enabled: true }, reward_budget: { daily_coins: null }, expedition_budget: { daily_launches: 2, daily_items: 6 } }} />);
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Candidate reward policy' }), 'expedition_limits');
    const limits = screen.getByRole('region', { name: 'Candidate expedition limits' });
    await user.click(within(limits).getByRole('button', { name: '3 items per child per day' }));
    expect(screen.queryByRole('spinbutton', { name: 'Candidate Coins per child per day' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByText('Experiment saved. Live rewards are unchanged.');
    expect(create.calls[0].body).toMatchObject({ candidate_policy: 'expedition_limits', candidate_daily_coins: null, candidate_expedition_budget: { daily_launches: null, daily_items: 3 }, config: { reward_commitment: { enabled: true }, reward_budget: { daily_coins: null }, expedition_budget: quota } });
  });
  it('updates the exact revision and captures the changed routine explicitly', async () => {
    setup(decided);
    const patch = spyHandler('patch', new RegExp(`${root}${draft.id}/$`), { ...draft, revision: 2 });
    server.use(patch.handler);
    function EditableRoutine() {
      const [routine, setRoutine] = useState(draft.config);
      return <><button onClick={() => setRoutine({ ...draft.config, seed: 99 })}>Change routine above</button><ProgressionExperimentNotebook routine={routine} /></>;
    }
    const { user } = renderWithProviders(<EditableRoutine />);
    await open(user);
    fireEvent.change(screen.getByRole('textbox', { name: 'Experiment name' }), { target: { value: 'Revised test' } });
    expect(screen.getByRole('button', { name: 'Run control and candidate' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Change routine above' }));
    expect(screen.getByText(/The routine above differs/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Use current routine' }));
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByText('Experiment saved. Live rewards are unchanged.');
    expect(patch.calls[0].body).toMatchObject({ revision: 1, name: 'Revised test', config: { seed: 99 } });
  });
  it('records a concrete decision and retest action against saved current evidence', async () => {
    setup(decided);
    const decision = spyHandler('post', new RegExp(`${root}${draft.id}/decisions/$`), decided);
    server.use(decision.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await open(user);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Saved comparison' }), comparison.id);
    await screen.findByRole('region', { name: 'Saved experiment comparison' });
    await user.type(screen.getByRole('textbox', { name: 'Decision reason' }), 'Continue testing commitments.');
    await user.type(screen.getByRole('textbox', { name: 'Next action' }), 'Model full pouch promises.');
    fireEvent.change(screen.getByLabelText('Review on'), { target: { value: '2099-01-01' } });
    await user.click(screen.getByRole('button', { name: 'Record decision' }));
    await screen.findByText('Decision recorded. No live changes were approved.');
    expect(decision.calls[0].body).toEqual({ revision: 1, comparison_id: comparison.id, outcome: 'keep_testing', rationale: 'Continue testing commitments.', next_action: 'Model full pouch promises.', review_on: '2099-01-01' });
    expect(screen.getByText(decided.decisions[0].next_action)).toBeVisible();
  });
  it('shows missing metrics honestly and blocks decisions on unavailable evidence', async () => {
    const unknown = { ...comparison, stale: true, freshness: 'unavailable', evaluation: { ...comparison.evaluation, status: 'insufficient', checks: [{ ...comparison.evaluation.checks[0], candidate: { value: null, completed_trials: 0, trials: 3 }, status: 'insufficient' }] } };
    setup(decided, unknown);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await open(user);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Saved comparison' }), comparison.id);
    await screen.findByText(/Current rules or catalog could not be checked/);
    expect(within(screen.getByRole('table', { name: 'Experiment success criteria' })).getByRole('cell', { name: /^Not reached or unavailable/ })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Publish/ })).toBeNull();
  });
  it('preserves failed edits and presents explicit conflict recovery', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`${root}${draft.id}/$`), HttpResponse.json({ detail: 'Experiment changed. Reload it before continuing.' }, { status: 409 }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await open(user);
    fireEvent.change(screen.getByRole('textbox', { name: 'Experiment name' }), { target: { value: 'My retained name' } });
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('textbox', { name: 'Experiment name' })).toHaveValue('My retained name');
    expect(patch.calls).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Reload saved experiment' })).toBeVisible();
  });
  it('does not validate an undeployed policy using uncapped Coin observations', async () => {
    setup();
    server.use(http.get('*/api/rpg/progression-lab/observations/', () => HttpResponse.json({ ...observations, status: 'observations_available', cohort: { ...observations.cohort, eligible_children: 2 }, ledger: { ...observations.ledger, credits: 300 } })));
    renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await screen.findByText('Observed installed-economy Coins');
    expect(screen.getByText(/Attribution is incomplete/)).toBeVisible();
    expect(screen.getByText(/The 100-Coin policy is not live/)).toBeVisible();
  });
  it('captures an immutable server observation checkpoint and reopens its insufficient evidence', async () => {
    setup();
    const capture = spyHandler('post', new RegExp(`${root}${draft.id}/observations/$`), observed);
    server.use(capture.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await open(user);
    await user.click(screen.getByRole('button', { name: 'Save observation checkpoint' }));
    await screen.findByText(/Observation checkpoint saved/);
    expect(capture.calls[0].body).toEqual({ revision: 1 });
    await user.click(screen.getByText(/Checkpoint .*insufficient evidence/));
    expect(screen.getAllByText('No eligible new-user Coin observations yet.')).toHaveLength(2);
    expect(screen.getByText(/Saved experiment revision 1/)).toBeVisible();
  });
  it('discards only confirmed edits before opening evidence and protects decision notes on rerun', async () => {
    setup(decided);
    const compare = spyHandler('post', new RegExp(`${root}${draft.id}/compare/$`), comparison);
    server.use(compare.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await open(user);
    fireEvent.change(screen.getByRole('textbox', { name: 'Experiment name' }), { target: { value: 'Unsaved name' } });
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Saved comparison' }), comparison.id);
    const discard = screen.getByRole('alertdialog', { name: 'Discard unsaved experiment changes?' });
    await user.click(within(discard).getByRole('button', { name: 'Discard changes' }));
    await screen.findByRole('region', { name: 'Saved experiment comparison' });
    expect(screen.getByRole('textbox', { name: 'Experiment name' })).toHaveValue(draft.name);
    await user.type(screen.getByRole('textbox', { name: 'Decision reason' }), 'Keep my notes until confirmed.');
    await user.click(screen.getByRole('button', { name: 'Run control and candidate' }));
    const notes = screen.getByRole('alertdialog', { name: 'Discard unsaved decision notes?' });
    expect(compare.calls).toHaveLength(0);
    await user.click(within(notes).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('textbox', { name: 'Decision reason' })).toHaveValue('Keep my notes until confirmed.');
    await user.click(screen.getByRole('button', { name: 'Run control and candidate' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Discard changes' }));
    await screen.findByText('Control and candidate comparison saved.');
    expect(compare.calls[0].body).toEqual({ revision: 1 });
    expect(screen.getByRole('textbox', { name: 'Decision reason' })).toHaveValue('');
  });
  it('rejects unbounded criteria locally and retries failed notebook reads without inventing an empty list', async () => {
    setup();
    server.use(http.get(`*${root}`, () => HttpResponse.json({ detail: 'Notebook read failed.' }, { status: 503 })));
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await screen.findByRole('alert');
    expect(screen.queryByRole('combobox', { name: 'Open experiment' })).toBeNull();
    setup();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('combobox', { name: 'Open experiment' });
    await user.click(screen.getByRole('button', { name: 'Add criterion' }));
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await screen.findByText('Each success criterion needs a minimum or maximum. Remove an unused criterion.');
    await user.click(screen.getByRole('button', { name: 'Remove criterion 1' }));
    expect(screen.queryByRole('spinbutton', { name: 'Criterion 1 minimum' })).toBeNull();
  });
  it('refreshes observed evidence explicitly and retains successful reads on a later failure', async () => {
    setup();
    const reads = spyHandler('get', /\/api\/rpg\/progression-lab\/observations\/$/, observations);
    server.use(reads.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await screen.findByText('No eligible new-user Coin observations yet.');
    await user.click(screen.getByRole('button', { name: 'Refresh observed evidence' }));
    await waitFor(() => expect(reads.calls).toHaveLength(2));
    server.use(http.get('*/api/rpg/progression-lab/observations/', () => HttpResponse.json({ detail: 'Observation read failed.' }, { status: 503 })));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh observed evidence' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Refresh observed evidence' }));
    await screen.findByText(/Could not load observed evidence/);
    expect(screen.getByText('No eligible new-user Coin observations yet.')).toBeVisible();
  });
  it('ignores a delayed save after credential replacement', async () => {
    setup();
    let resolve;
    const delayed = new Promise((done) => { resolve = done; });
    const create = spyHandler('post', new RegExp(`${root}$`), async () => { await delayed; return draft; });
    server.use(create.handler);
    const { user } = renderWithProviders(<ProgressionExperimentNotebook routine={draft.config} />);
    await screen.findByRole('combobox', { name: 'Open experiment' });
    await user.click(screen.getByRole('button', { name: 'Save experiment' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    localStorage.setItem('abby_auth_token', 'replacement-session');
    resolve();
    await waitFor(() => expect(screen.queryByText('Experiment saved. Live rewards are unchanged.')).toBeNull());
    expect(screen.queryByRole('button', { name: 'Reload saved experiment' })).toBeNull();
  });
});
