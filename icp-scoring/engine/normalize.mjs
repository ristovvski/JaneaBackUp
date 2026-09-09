// engine/normalize.mjs — identifier normalization.
//
// Pure, no I/O, no dependencies. Everything here exists so that "the same
// company" looks the same however Pipedrive, LinkedIn or a rep typed it:
// duplicate detection, Clay lookup keys and the audit trail all depend on it.

// ---------------------------------------------------------------------------
// Vendored public suffix list (multi-label entries only).
//
// A single-label suffix (`io`, `com`, `dev`) is the default, so only suffixes
// that span more than one label need listing. This is a curated subset, not
// the full IANA PSL: it covers the suffixes that actually appear in B2B
// company domains. `careers.acme.co.uk` collapses to `acme.co.uk` because
// `co.uk` is below; an unlisted multi-label suffix would collapse one label
// too far. Adding one is a single line here.
// ---------------------------------------------------------------------------
export const PUBLIC_SUFFIXES = new Set([
  // United Kingdom / Ireland
  'co.uk', 'org.uk', 'me.uk', 'ltd.uk', 'plc.uk', 'net.uk', 'sch.uk', 'ac.uk', 'gov.uk', 'nhs.uk',
  'co.ie',
  // Australia / New Zealand
  'com.au', 'net.au', 'org.au', 'edu.au', 'gov.au', 'id.au', 'asn.au',
  'co.nz', 'net.nz', 'org.nz', 'govt.nz', 'ac.nz', 'school.nz',
  // Canada (provincial)
  'ab.ca', 'bc.ca', 'mb.ca', 'nb.ca', 'nf.ca', 'nl.ca', 'ns.ca', 'nt.ca',
  'nu.ca', 'on.ca', 'pe.ca', 'qc.ca', 'sk.ca', 'yk.ca', 'gc.ca',
  // Asia
  'co.jp', 'or.jp', 'ne.jp', 'ac.jp', 'go.jp', 'ad.jp', 'ed.jp', 'gr.jp', 'lg.jp',
  'co.kr', 'or.kr', 'ne.kr', 'go.kr', 're.kr', 'pe.kr',
  'com.cn', 'net.cn', 'org.cn', 'gov.cn', 'edu.cn', 'ac.cn',
  'com.hk', 'org.hk', 'net.hk', 'edu.hk', 'gov.hk', 'idv.hk',
  'com.tw', 'org.tw', 'net.tw', 'gov.tw', 'edu.tw',
  'com.sg', 'net.sg', 'org.sg', 'edu.sg', 'gov.sg', 'per.sg',
  'co.in', 'net.in', 'org.in', 'firm.in', 'gen.in', 'ind.in', 'gov.in', 'ac.in', 'edu.in',
  'com.my', 'net.my', 'org.my', 'gov.my', 'edu.my',
  'co.id', 'or.id', 'web.id', 'ac.id', 'go.id',
  'co.th', 'in.th', 'ac.th', 'go.th',
  'com.ph', 'net.ph', 'org.ph',
  'com.vn', 'net.vn', 'org.vn',
  'co.il', 'org.il', 'net.il', 'ac.il', 'gov.il',
  'com.tr', 'net.tr', 'org.tr', 'gov.tr', 'edu.tr',
  'com.sa', 'net.sa', 'org.sa', 'gov.sa', 'edu.sa',
  'co.ae', 'net.ae', 'org.ae', 'gov.ae', 'ac.ae',
  // Latin America
  'com.br', 'net.br', 'org.br', 'gov.br', 'edu.br', 'ind.br', 'eng.br',
  'com.mx', 'net.mx', 'org.mx', 'gob.mx', 'edu.mx',
  'com.ar', 'net.ar', 'org.ar', 'gob.ar', 'edu.ar',
  'com.co', 'net.co', 'org.co', 'gov.co', 'edu.co',
  'com.pe', 'com.uy', 'com.ve', 'com.ec',
  // Europe
  'co.at', 'or.at', 'ac.at', 'gv.at',
  'com.de', 'com.es', 'nom.es', 'org.es', 'gob.es', 'edu.es',
  'com.pl', 'net.pl', 'org.pl', 'gov.pl', 'edu.pl',
  'com.pt', 'org.pt', 'gov.pt',
  'com.it', 'edu.it', 'gov.it',
  'com.gr', 'net.gr', 'org.gr', 'gov.gr', 'edu.gr',
  'com.ro', 'com.ua', 'net.ua', 'org.ua', 'gov.ua', 'edu.ua',
  'com.ru', 'net.ru', 'org.ru',
  'com.cy', 'com.hr', 'com.mt', 'com.ee', 'com.lv', 'gov.lt',
  'co.rs', 'co.me', 'co.hu',
  // Africa / Middle East
  'co.za', 'net.za', 'org.za', 'gov.za', 'ac.za', 'web.za',
  'com.ng', 'net.ng', 'org.ng', 'gov.ng', 'edu.ng',
  'co.ke', 'or.ke', 'go.ke', 'ac.ke',
  'com.eg', 'net.eg', 'org.eg', 'gov.eg', 'edu.eg',
  'co.ma', 'com.gh', 'com.tn', 'co.bw',
  // South Asia / other
  'com.bd', 'com.pk', 'net.pk', 'org.pk', 'gov.pk', 'edu.pk', 'com.mm',
]);

const LEGAL_SUFFIX_TOKENS = new Set([
  'inc', 'incorporated', 'llc', 'lc', 'ltd', 'limited', 'gmbh', 'corp',
  'corporation', 'co', 'company', 'plc', 'sas', 'sa', 'sarl', 'bv', 'nv', 'ag',
  'srl', 'spa', 'pty', 'pte', 'oy', 'ab', 'as', 'aps', 'kk', 'kg', 'ug', 'ou',
  'ps', 'ks', 'group', 'holding', 'holdings',
]);

// ---------------------------------------------------------------------------
// normalizeDomain
// ---------------------------------------------------------------------------

/**
 * Reduce any URL or bare domain to its registrable root domain.
 * `HTTP://WWW.Acme.IO/about?x=1` -> `acme.io`
 * `careers.acme.co.uk`           -> `acme.co.uk`
 * Returns null for empty, malformed, IP-literal or single-label input.
 */
export function normalizeDomain(input) {
  if (typeof input !== 'string') return null;
  let s = input.trim().toLowerCase();
  if (s === '') return null;

  // Strip scheme (and a protocol-relative "//" prefix), then userinfo, then
  // anything from the first path separator.
  s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//, '');
  s = s.replace(/^\/\//, '');
  s = s.replace(/^[^/@]*@/, '');
  s = s.split(/[/?#]/)[0];
  // Strip port, then a trailing root dot ("acme.io." is the same host).
  s = s.split(':')[0];
  s = s.replace(/\.+$/, '');
  if (s === '') return null;

  // An IP literal has no registrable domain.
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(s)) return null;
  if (s.includes('[') || s.includes(']')) return null;

  if (!/^[a-z0-9.-]+$/.test(s)) return null;
  if (s.includes('..') || s.startsWith('.') || s.startsWith('-')) return null;

  const labels = s.split('.').filter((l) => l !== '');
  if (labels.length < 2) return null;
  if (labels.some((l) => l.length > 63 || /^-|-$/.test(l))) return null;
  // A bare public suffix ("co.uk") is not a registrable domain.
  if (PUBLIC_SUFFIXES.has(s)) return null;

  // Longest matching public suffix wins; the default is the last label alone.
  let suffixLen = 1;
  for (let take = Math.min(labels.length - 1, 4); take >= 2; take -= 1) {
    const candidate = labels.slice(labels.length - take).join('.');
    if (PUBLIC_SUFFIXES.has(candidate)) { suffixLen = take; break; }
  }

  if (labels.length <= suffixLen) return null; // a bare public suffix
  return labels.slice(labels.length - suffixLen - 1).join('.');
}

// ---------------------------------------------------------------------------
// normalizeLinkedInCompanyUrl
// ---------------------------------------------------------------------------

/**
 * Canonicalize a LinkedIn *company* URL.
 * `linkedin.com/company/Acme/` -> `https://www.linkedin.com/company/acme`
 * A people URL (`/in/john`) is not a company and returns null.
 */
export function normalizeLinkedInCompanyUrl(input) {
  if (typeof input !== 'string') return null;
  let s = input.trim().toLowerCase();
  if (s === '') return null;

  s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//, '');
  s = s.split(/[?#]/)[0];

  const slash = s.indexOf('/');
  if (slash === -1) return null;
  const host = s.slice(0, slash).split(':')[0].replace(/\.+$/, '');
  const path = s.slice(slash);

  // linkedin.com plus its country subdomains (de.linkedin.com, ...).
  if (host !== 'linkedin.com' && !host.endsWith('.linkedin.com')) return null;

  const match = path.match(/^\/company\/([^/]+)/);
  if (!match) return null;

  let slug = match[1];
  try { slug = decodeURIComponent(slug); } catch { /* keep the raw slug */ }
  slug = slug.replace(/\.+$/, '');
  if (slug === '' || !/^[a-z0-9._~-]+$/.test(slug)) return null;

  return `https://www.linkedin.com/company/${slug}`;
}

// ---------------------------------------------------------------------------
// normalizeCompanyName
// ---------------------------------------------------------------------------

/**
 * `Acme, Inc.` and `ACME INC` both -> `acme`.
 * Legal suffixes are stripped repeatedly from the end ("Acme Pty Ltd" -> "acme")
 * but never to the point of emptying the name ("Ltd" stays "ltd").
 */
export function normalizeCompanyName(input) {
  if (typeof input !== 'string') return null;

  let s = input.trim().toLowerCase();
  if (s === '') return null;

  // Fold accents to ASCII first, so "Muller" and "Müller" match instead of the
  // umlaut being dropped as punctuation and splitting the token in two.
  s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/ß/g, 'ss').replace(/æ/g, 'ae').replace(/œ/g, 'oe')
       .replace(/ø/g, 'o').replace(/ł/g, 'l').replace(/đ/g, 'd').replace(/ħ/g, 'h');

  // Nordic legal forms are written with a slash; collapse them before the
  // slash becomes a separator, so "Aero A/S" strips like any other suffix.
  s = s.replace(/\b([aps])\/s\b/g, '$1s');

  // Ampersand and slash read as word separators; other punctuation is dropped.
  s = s.replace(/[&/]/g, ' ');
  s = s.replace(/[^a-z0-9\s.'’-]/g, ' ');
  // Dots and apostrophes vanish inside tokens ("l.l.c" -> "llc", "o'neil" -> "oneil").
  s = s.replace(/[.'’]/g, '');
  s = s.replace(/\s+/g, ' ').trim();
  if (s === '') return null;

  const tokens = s.split(' ').filter((t) => t !== '' && t !== '-');
  if (tokens.length === 0) return null;

  const stripped = tokens.slice();
  while (stripped.length > 1 && LEGAL_SUFFIX_TOKENS.has(stripped[stripped.length - 1])) {
    stripped.pop();
  }
  const result = (stripped.length > 0 ? stripped : tokens).join(' ').trim();
  return result === '' ? null : result;
}

// ---------------------------------------------------------------------------
// resolveIdentifier
// ---------------------------------------------------------------------------

/**
 * Pick the identifier Clay should enrich from, in priority order:
 * domain (high) > LinkedIn company URL (high) > company name (low).
 *
 * NEEDS_DECISION #5 default: an org with neither domain nor LinkedIn is still
 * scored, from name + HQ, at low confidence. It is never "Insufficient data"
 * on the strength of a missing identifier alone.
 *
 * @returns {{kind:'domain'|'linkedin'|'name', value:string, confidence:'high'|'low'}|null}
 */
export function resolveIdentifier(org) {
  if (!org || typeof org !== 'object') return null;

  const domain = normalizeDomain(org.website || org.domain || null);
  if (domain) return { kind: 'domain', value: domain, confidence: 'high' };

  const linkedin = normalizeLinkedInCompanyUrl(org.linkedin || org.linkedin_url || null);
  if (linkedin) return { kind: 'linkedin', value: linkedin, confidence: 'high' };

  const name = normalizeCompanyName(org.name || org.company_name || null);
  if (name) return { kind: 'name', value: name, confidence: 'low' };

  return null;
}
