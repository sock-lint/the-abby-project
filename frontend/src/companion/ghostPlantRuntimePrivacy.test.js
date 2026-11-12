import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, matchesGlob, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import runtime from '../../../shared/catalog/elemental-ghost-potted-plant.runtime.json';

const sourceRoot = resolve(process.cwd(), 'src');
const auditDescriptor = 'elemental-ghost-potted-plant.json';

function productionSources(directory, root = directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return path === join(root, 'test') ? [] : productionSources(path, root);
    return /\.[jt]sx?$/.test(entry.name) && !/\.(test|spec)\.[jt]sx?$/.test(entry.name) ? [path] : [];
  });
}

function auditReferences(source, path) {
  const literals = [];
  // Preserve offsets while excluding comments and string contents from call matching.
  const code = source.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n\r]*|(['"`])((?:\\[\s\S]|(?!\1)[^\\])*)\1/g,
    (text, quote, value, start) => {
      if (quote) {
        const decoded = value.replace(/\\(?:u\{([\da-f]+)\}|u([\da-f]{4})|x([\da-f]{2})|([\s\S]))/gi,
          (_escape, point, unicode, hex, character) => point || unicode || hex
            ? String.fromCodePoint(parseInt(point || unicode || hex, 16))
            : ({ n: '\n', r: '\r', t: '\t', '\n': '', '\r': '' }[character] ?? character));
        literals.push({ start, end: start + text.length, value: decoded, dynamic: quote === '`' && value.includes('${') });
      }
      return text.replace(/[^\n\r]/g, ' ');
    });
  const normalize = (value) => value.replace(/\\/g, '/').replace(/#.*$/, '').replace(/(\.json)\?.*$/, '$1');
  const target = resolve(sourceRoot, '../../shared/catalog', auditDescriptor);
  const references = [], globLiterals = new Set();
  const report = (kind, value) => references.push({ module: relative(sourceRoot, path), kind, value });
  for (const call of code.matchAll(/\bimport\s*\.\s*meta\s*\.\s*glob(?:Eager)?\s*\(/g)) {
    let start = call.index + call[0].length;
    while (/\s/.test(code[start] ?? '') && !literals.some((literal) => literal.start === start)) start += 1;
    const literal = literals.find((entry) => entry.start === start);
    const end = code.indexOf(']', start);
    const patterns = literal ? [literal] : source[start] === '[' && end !== -1
      ? literals.filter((entry) => entry.start > start && entry.end <= end) : [];
    for (const pattern of patterns) globLiterals.add(pattern.start);
    const staticArgument = literal ? /^\s*[,)]/.test(code.slice(literal.end))
      : source[start] === '[' && end !== -1 && !code.slice(start + 1, end).replace(/,/g, '').trim();
    if (!staticArgument || !patterns.length || patterns.some((entry) => entry.dynamic)) {
      report('unresolved glob', source.slice(start, literal?.end ?? (end === -1 ? start + 80 : end + 1)));
      continue;
    }
    const includes = patterns.filter((entry) => !entry.value.startsWith('!'));
    const excludes = patterns.filter((entry) => entry.value.startsWith('!'));
    const reachesAudit = (entry) => {
      const pattern = normalize(entry.value.replace(/^!/, ''));
      const absolute = pattern.startsWith('/') ? resolve(sourceRoot, '..', `.${pattern}`) : resolve(dirname(path), pattern);
      return matchesGlob(target, absolute);
    };
    if (includes.some(reachesAudit) && !excludes.some(reachesAudit)) report('glob', patterns.map((entry) => entry.value));
  }
  for (const literal of literals) {
    if (!globLiterals.has(literal.start) && basename(normalize(literal.value)) === auditDescriptor) report('literal', literal.value);
  }
  return references;
}

describe('Ghost and Potted Plant runtime privacy', () => {
  it.each([
    ['catalog glob', "const audit = import.meta.glob('../../../shared/catalog/elemental-ghost-potted-plant.json', { eager: true, import: 'default' });"],
    ['asset URL', "const audit = new URL('../../../shared/catalog/elemental-ghost-potted-plant.json', import.meta.url);"],
  ])('rejects the proven %s delivery counterexample', (_name, source) => {
    expect(auditReferences(source, resolve(sourceRoot, 'companion/probe.js'))).not.toEqual([]);
  });

  it.each([
    ['static import', "import audit from '../../../shared/catalog/elemental-ghost-potted-plant.json';"],
    ['side-effect import', "import '../../../shared/catalog/elemental-ghost-potted-plant.json';"],
    ['dynamic import', "import('../../../shared/catalog/elemental-ghost-potted-plant.json');"],
    ['export from', "export { default } from '../../../shared/catalog/elemental-ghost-potted-plant.json';"],
    ['require', "require('../../../shared/catalog/elemental-ghost-potted-plant.json');"],
    ['query and fragment', "new URL('../../../shared/catalog/elemental-ghost-potted-plant.json?url#asset', import.meta.url);"],
    ['raw query', "import('../../../shared/catalog/elemental-ghost-potted-plant.json?raw');"],
    ['static template', 'new URL(`../../../shared/catalog/elemental-ghost-potted-plant.json`, import.meta.url);'],
    ['escaped filename', String.raw`new URL('../../../shared/catalog/elemental-ghost-potted-\u0070lant.json', import.meta.url);`],
    ['catalog wildcard', "import.meta.glob('../../../shared/catalog/*.json');"],
    ['Vite root-absolute catalog wildcard', "import.meta.glob('/../shared/catalog/*.json', { eager: true, import: 'default' });"],
    ['recursive catalog wildcard', "import.meta.glob('../../../shared/**/catalog/*.{json,txt}');"],
    ['glob array', "import.meta.glob(['../avatar/**/*.png', '../../../shared/catalog/*.json']);"],
    ['dynamic glob', "import.meta.glob(catalogPattern);"],
    ['dynamic template glob', 'import.meta.glob(`../../../shared/catalog/${name}.json`);'],
  ])('rejects a private audit reference through %s', (_name, source) => {
    expect(auditReferences(source, resolve(sourceRoot, 'companion/probe.js'))).not.toEqual([]);
  });

  it.each([
    "import runtime from '../../../shared/catalog/elemental-ghost-potted-plant.runtime.json';",
    "new URL('../../../shared/catalog/elemental-ghost-potted-plant.runtime.json?url', import.meta.url);",
    "import.meta.glob('../../../shared/catalog/*.runtime.json');",
    "import.meta.glob(['../../../shared/catalog/*.json', '!../../../shared/catalog/elemental-ghost-potted-plant.json']);",
    "import.meta.glob(['/../shared/catalog/*.json', '!/../shared/catalog/elemental-ghost-potted-plant.json']);",
    "import.meta.glob('/src/avatar/shared/**/*.{glb,png}');",
    "import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, import: 'default' });",
    "import.meta.glob('../avatar/shared/**/*.{glb,png}', { query: '?url' });",
    "// import '../../../shared/catalog/elemental-ghost-potted-plant.json';\n/* import.meta.glob('../../../shared/catalog/*.json') */",
  ])('allows safe runtime, avatar and excluded references: %s', (source) => {
    expect(auditReferences(source, resolve(sourceRoot, 'companion/probe.js'))).toEqual([]);
  });

  it('scans nested production test routes while excluding root test scaffolding and test files', () => {
    const temporary = mkdtempSync(join(tmpdir(), 'abby-runtime-privacy-'));
    try {
      const nested = join(temporary, 'pages/manage/test/consumer.js');
      for (const path of [nested, join(temporary, 'test/fixture.js'), join(temporary, 'consumer.test.js'), join(temporary, 'consumer.spec.jsx')]) {
        mkdirSync(dirname(path), { recursive: true });
        writeFileSync(path, "new URL('../../../shared/catalog/elemental-ghost-potted-plant.json', import.meta.url);");
      }
      expect(productionSources(temporary)).toEqual([nested]);
      expect(auditReferences(readFileSync(nested, 'utf8'), nested)).not.toEqual([]);
    } finally {
      rmSync(temporary, { recursive: true, force: true });
    }
  });

  it('preserves every release and family value from the audit descriptor', () => {
    const audit = JSON.parse(readFileSync(resolve(sourceRoot, '../../shared/catalog', auditDescriptor), 'utf8'));
    expect(runtime).toEqual({ release: audit.release, families: audit.families });
  });

  it('allows only public runtime fields at every descriptor level', () => {
    const keys = (value) => Object.keys(value).sort();
    expect(keys(runtime)).toEqual(['families', 'release']);
    expect(keys(runtime.release)).toEqual(['family_id', 'manifest_sha256', 'release_version']);
    for (const family of runtime.families) {
      expect(keys(family)).toEqual(['challenges', 'egg_item_slug', 'review_icons', 'species_slug', 'sprite_key']);
      for (const challenge of family.challenges) {
        expect(keys(challenge)).toEqual(['catalog_icon', 'name', 'potion_slug', 'target_count', 'window_days']);
      }
      for (const icon of family.review_icons) expect(keys(icon)).toEqual(['asset_id', 'potion_slug']);
    }
  });

  it('keeps the private audit descriptor out of production imports', () => {
    const references = productionSources(sourceRoot).flatMap((path) => auditReferences(readFileSync(path, 'utf8'), path));
    expect(references).toEqual([]);
  });
});
