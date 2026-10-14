import { requireValue } from './asset-checks-contract.mjs';

// Tailwind accepts CSS query aliases even on .js files. Inspect every source,
// and inspect transformed source before its pre-hook can load host modules.
export function rejectExecutableStyles(value) {
  const text = String(value).replace(/\\(?:([0-9a-f]{1,6})[ \t\r\n\f]?|([^\r\n]))/gi, (_match, hex, character) => {
    if (!hex) return character;
    const code = Number.parseInt(hex, 16);
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : '\ufffd';
  }).replace(/\/\*[\s\S]*?\*\//g, '');
  requireValue(!/@\s*(?:plugin|config|reference|source)\b/i.test(text), 'UNSUPPORTED_CSS_PLUGIN');
  for (const rule of text.match(/@\s*import\b[^;]*(?:;|$)/gi) || []) {
    requireValue(/^@\s*import\s+(['"])tailwindcss\1\s*;$/i.test(rule), 'UNSUPPORTED_CSS_IMPORT');
  }
}
export function rejectStyleQuery(value) {
  const query = String(value).split('?').slice(1).join('?');
  let decoded;
  try { decoded = decodeURIComponent(query); } catch { throw new Error('UNSUPPORTED_STYLE_QUERY'); }
  requireValue(!/\.css/i.test(decoded), 'UNSUPPORTED_STYLE_QUERY');
}
export function assetPreviewGuard(root) {
  return {
    name: 'abby-private-source-guard',
    enforce: 'pre',
    transform(code, id) {
      rejectStyleQuery(id);
      if (id.startsWith(root + '/')) rejectExecutableStyles(code);
      return null;
    },
  };
}
