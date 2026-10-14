import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from '@playwright/test';
import { checkParentUx, checkChildUx } from './live-smoke/family-task-ux.js';

test.use({ serviceWorkers: 'block', trace: 'off', screenshot: 'off', video: 'off' });
test.setTimeout(30_000);

// Local DOM/request contracts for the observer helpers. Every request is fenced
// to this disposable loopback server; no real credentials or live host is used.
function fixtureApp(options) {
  const main = document.querySelector('main');
  let version = 0;
  let projectSearch = '';
  let projectTop = 0;
  const navigate = (path) => { history.pushState({}, '', path); render(); };
  window.addEventListener('popstate', render);
  const tasks = ['Projects', 'Chores', 'Habits', 'Movement', 'Forge'];
  const ids = ['ventures', 'duties', 'rituals', 'movement', 'forge'];
  function taskTabs() {
    return '<div role="tablist" aria-label="Tasks sections">' + tasks.map((name, index) => `<button role="tab" data-task="${ids[index]}">${name}</button>`).join('') + '</div>';
  }
  function hookTabs() {
    document.querySelectorAll('[data-task]').forEach((button) => button.onclick = () => navigate('/quests?tab=' + button.dataset.task));
    document.querySelectorAll('[data-memory]').forEach((button) => button.onclick = () => {
      const params = new URLSearchParams(location.search);
      params.set('tab', button.dataset.memory);
      navigate('/chronicle?' + params);
    });
  }
  function attachment(title, label, image) {
    const field = label === 'Photo' ? 'photo-file' : 'model-file';
    main.insertAdjacentHTML('beforeend', `<section role="dialog" aria-label="${title}">
      ${image ? '' : '<button id="upload-mode">Upload</button>'}
      <label for="${field}">${label}</label><input id="${field}" type="file" hidden>
      <div id="selection">No file selected</div><button id="remove" aria-label="Remove ${label.toLowerCase()}">Remove</button>
      <button id="cancel">Cancel</button></section>`);
    const input = document.getElementById(field);
    let blob;
    const clear = () => { if (blob) URL.revokeObjectURL(blob); blob = null; };
    input.onchange = () => {
      clear();
      const file = input.files[0];
      const selection = document.getElementById('selection');
      selection.textContent = file.name;
      if (image) {
        blob = URL.createObjectURL(file);
        selection.insertAdjacentHTML('beforeend', '<img alt="Photo preview" style="width:64px;height:64px">');
        selection.querySelector('img').src = blob;
      }
      if (options.unexpectedUpload) fetch('/api/photos/', { method: 'POST', body: file });
    };
    document.getElementById('remove').onclick = () => { clear(); input.value = ''; document.getElementById('selection').textContent = 'No file selected'; };
    document.getElementById('cancel').onclick = () => { clear(); document.querySelector('[role="dialog"]').remove(); };
  }
  async function render() {
    const current = ++version;
    const url = new URL(location.href);
    if (url.pathname === '/') {
      main.innerHTML = '<h1>Today</h1><button id="timeline" aria-label="View Fixture child\'s timeline">View timeline</button>';
      document.getElementById('timeline').onclick = () => navigate('/chronicle?tab=yearbook&child=7');
      return;
    }
    if (url.pathname === '/chronicle') {
      main.innerHTML = '<div role="tablist" aria-label="Memories sections">' + ['Gallery', 'Journal', 'Grades', 'Timeline'].map((name, index) => `<button role="tab" data-memory="${['sketchbook', 'journal', 'grades', 'yearbook'][index]}">${name}</button>`).join('') + '</div>';
      hookTabs();
      if (url.searchParams.get('tab') === 'sketchbook') {
        main.insertAdjacentHTML('beforeend', '<button id="add-photo">Add photo</button>');
        document.getElementById('add-photo').onclick = () => attachment('Upload Photo', 'Photo', true);
        return;
      }
      if (options.role === 'parent') main.insertAdjacentHTML('beforeend', '<label for="viewing">Viewing</label><select id="viewing"><option value="7">Fixture child</option></select>');
      else main.insertAdjacentHTML('beforeend', '<button>Write today’s entry</button>');
      await fetch('/api/chronicle/summary/' + (options.role === 'parent' ? '?user_id=7' : ''));
      return;
    }
    if (/^\/quests\/ventures\/\d+$/.test(url.pathname)) {
      main.innerHTML = `<h1>Fixture project</h1><a id="back" href="/quests${projectSearch}">Back to Projects</a>`;
      document.getElementById('back').onclick = (event) => { event.preventDefault(); navigate('/quests' + projectSearch); };
      return;
    }
    if (url.pathname !== '/quests') { main.innerHTML = '<h1>Ready</h1>'; return; }
    const tab = url.searchParams.get('tab');
    main.innerHTML = taskTabs();
    hookTabs();
    if (tab === 'forge') {
      main.insertAdjacentHTML('beforeend', '<h1>Forge</h1><button id="ask-print">Ask for a print</button>');
      document.getElementById('ask-print').onclick = () => attachment('Ask for a print', 'Model file', false);
      return;
    }
    if (tab === 'movement') {
      main.insertAdjacentHTML('beforeend', '<h1>Movement</h1><p>0 sessions recorded today · 0 XP earned</p>'); return;
    }
    const kind = tab === 'duties' ? 'chores' : tab === 'rituals' ? 'habits' : 'projects';
    main.insertAdjacentHTML('beforeend', `<h1>${kind[0].toUpperCase() + kind.slice(1)}</h1><div id="content"></div>`);
    let rows;
    try {
      rows = await (await fetch('/api/' + kind + '/')).json();
    } catch {
      if (current !== version) return;
      document.getElementById('content').innerHTML = `<div role="alert">Couldn't load ${kind}.<button id="retry">Retry</button></div>`;
      document.getElementById('retry').onclick = render;
      return;
    }
    if (current !== version) return;
    const content = document.getElementById('content');
    const empty = kind === 'chores' ? 'No chores available today.' : kind === 'habits' ? 'No habits yet. Add or propose a habit to get started.' : 'No projects yet. Ask a parent to add one.';
    if (!rows.length || options.falseProjectEmpty && kind === 'projects') { content.textContent = empty; return; }
    content.innerHTML = `<input type="search" aria-label="Filter ${kind}" value="${url.searchParams.get('q') || ''}"><div id="rows"></div>`;
    if (kind === 'projects') {
      content.insertAdjacentHTML('afterbegin', '<select aria-label="Filter by status"><option value="">All statuses</option><option value="in_progress">In progress</option></select><select aria-label="Filter by type"><option value="">All types</option><option value="bounty">Bounty</option></select>' + (options.role === 'parent' ? '<select aria-label="Filter by child"><option value="">All children</option><option value="unassigned">Unassigned</option><option value="7">Fixture child</option></select>' : ''));
      content.querySelectorAll('select').forEach((select, index) => {
        const param = ['status', 'type', 'child'][index];
        select.value = url.searchParams.get(param) || '';
        select.onchange = () => {
          const params = new URLSearchParams(location.search);
          params.set(param, select.value);
          history.replaceState({}, '', '/quests?' + params);
        };
      });
    }
    const search = content.querySelector('input');
    const results = document.getElementById('rows');
    const update = () => {
      const matches = rows.filter((row) => row.title.toLowerCase().includes(search.value.toLowerCase()));
      if (kind === 'projects') {
        const params = new URLSearchParams(location.search);
        if (search.value) params.set('q', search.value); else params.delete('q');
        history.replaceState({}, '', '/quests?' + params);
      }
      if (!matches.length) {
        results.innerHTML = `<p>No matches for “${search.value}”</p><button id="clear">Clear filter</button>`;
        document.getElementById('clear').onclick = () => { search.value = ''; update(); };
      } else if (kind === 'projects') {
        results.innerHTML = '<button aria-label="Open Fixture project" style="display:block;margin-top:1000px">Fixture project</button>';
        results.querySelector('button').onclick = () => { projectSearch = location.search; projectTop = window.scrollY; navigate('/quests/ventures/3'); };
      } else results.textContent = matches[0].title;
    };
    search.oninput = update;
    update();
    if (kind === 'projects' && projectTop) requestAnimationFrame(() => window.scrollTo(0, projectTop));
  }
  render();
}

async function localCheck(browser, options, run) {
  const requests = [];
  const server = createServer((request, response) => {
    requests.push({ method: request.method, path: request.url });
    if (request.url.startsWith('/api/')) {
      response.setHeader('content-type', 'application/json; charset=utf-8');
      response.end(JSON.stringify(options.rows || options.falseProjectEmpty ? [{ id: 3, title: 'Fixture project', status: 'in_progress', payment_kind: 'bounty', assigned_to: null }] : []));
    } else {
      response.setHeader('content-type', 'text/html; charset=utf-8');
      response.end(`<html><body style="margin:0;min-height:2200px"><main></main><script>(${fixtureApp.toString()})(${JSON.stringify(options)})</script></body></html>`);
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  let context;
  let unexpected = false;
  const credentials = { baseUrl, child: { id: 7 }, parent: { id: 8 } };
  const gate = { credentials, role: options.role, verified: true, assertSafe() { assert.equal(unexpected, false, 'Only loopback GET reads are allowed'); } };
  try {
    context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1280, height: 800 } });
    await context.route('**/*', async (route) => {
      const request = route.request();
      if (new URL(request.url()).origin !== baseUrl || request.method() !== 'GET') { unexpected = true; await route.abort(); }
      else await route.continue();
    });
    const page = await context.newPage();
    await page.goto(baseUrl + '/ready');
    await run(page, credentials, gate, requests);
    assert.ok(requests.every((request) => request.method === 'GET'));
    assert.ok(requests.every((request) => !request.path.includes('user_id=0')));
  } finally {
    await context?.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

test('parent context recovery and existing project return use only local reads', async ({ browser }) => {
  await localCheck(browser, { role: 'parent', rows: true }, async (page, credentials, gate) => {
    assert.deepEqual(await checkParentUx(page, credentials, gate), {
      memoryContext: 'verified_parent', invalidChild: 'verified_roster_recovery', projectReturn: 'detail_and_back',
    });
  });
});

test('child empty fixture checks stay explicit, recover a real offline GET and never submit local files', async ({ browser }) => {
  await localCheck(browser, { role: 'child' }, async (page, credentials, gate) => {
    const result = await checkChildUx(page, credentials, gate);
    assert.equal(result.choresSearch, 'verified_true_empty');
    assert.equal(result.habitsSearch, 'verified_true_empty');
    assert.equal(result.projectReturn, 'verified_true_empty');
    assert.equal(result.readRecovery, 'offline_retry');
    assert.equal(result.attachments, 'local_only');
  });
});

test('populated child fixtures exercise unmatched search, clear and existing project return', async ({ browser }) => {
  await localCheck(browser, { role: 'child', rows: true }, async (page, credentials, gate) => {
    const result = await checkChildUx(page, credentials, gate);
    assert.equal(result.choresSearch, 'filtered_and_cleared');
    assert.equal(result.habitsSearch, 'filtered_and_cleared');
    assert.equal(result.projectReturn, 'detail_and_back');
  });
});

test('a false empty project view cannot count as verified empty coverage', async ({ browser }) => {
  await localCheck(browser, { role: 'parent', falseProjectEmpty: true }, async (page, credentials, gate) => {
    await assert.rejects(() => checkParentUx(page, credentials, gate), { code: 'BROWSER' });
  });
});

test('an unverified session fails before any helper navigation', async ({ browser }) => {
  await localCheck(browser, { role: 'parent' }, async (page, credentials, gate, requests) => {
    gate.verified = false;
    const before = requests.length;
    await assert.rejects(() => checkParentUx(page, credentials, gate), { code: 'ISOLATION' });
    assert.equal(requests.length, before);
  });
});

test('a chooser which unexpectedly uploads is rejected and its POST never reaches the server', async ({ browser }) => {
  await localCheck(browser, { role: 'child', unexpectedUpload: true }, async (page, credentials, gate, requests) => {
    await assert.rejects(() => checkChildUx(page, credentials, gate), { message: /Only loopback GET reads are allowed/ });
    assert.ok(requests.every((request) => request.method === 'GET'));
  });
});
