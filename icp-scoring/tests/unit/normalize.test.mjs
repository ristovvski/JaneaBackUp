// tests/unit/normalize.test.mjs — the §6 table, driven from data.
//
// Every row is a real shape seen in Pipedrive org records, a LinkedIn paste,
// or a rep's typing. Adding a row is cheaper than a bug report.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeDomain,
  normalizeLinkedInCompanyUrl,
  normalizeCompanyName,
  resolveIdentifier,
  PUBLIC_SUFFIXES,
} from '../../engine/normalize.mjs';

// --------------------------------------------------------------------------
// normalizeDomain
// --------------------------------------------------------------------------
const DOMAIN_CASES = [
  // [input, expected, why]
  ['HTTP://WWW.Acme.IO/about?x=1', 'acme.io', 'scheme + www + path + query, uppercase'],
  ['acme.io.', 'acme.io', 'trailing root dot'],
  ['acme.io', 'acme.io', 'already bare'],
  ['www.acme.io', 'acme.io', 'www prefix'],
  ['https://acme.io', 'acme.io', 'https, no path'],
  ['//acme.io/x', 'acme.io', 'protocol-relative'],
  ['acme.io:8443', 'acme.io', 'explicit port'],
  ['https://acme.io:443/a/b/c', 'acme.io', 'port plus deep path'],
  ['https://user:pw@acme.io/x', 'acme.io', 'userinfo stripped'],
  ['careers.acme.co.uk', 'acme.co.uk', 'public suffix aware, two-label suffix'],
  ['https://jobs.careers.acme.co.uk/list', 'acme.co.uk', 'multiple subdomains + co.uk'],
  ['acme.com.au', 'acme.com.au', 'com.au'],
  ['sub.acme.com.br', 'acme.com.br', 'com.br'],
  ['shop.acme.co.nz', 'acme.co.nz', 'co.nz'],
  ['x.y.acme.co.jp', 'acme.co.jp', 'co.jp'],
  ['blog.acme.on.ca', 'acme.on.ca', 'Canadian provincial suffix'],
  ['ACME.CO.ZA', 'acme.co.za', 'co.za, uppercase'],
  ['acme.dev', 'acme.dev', 'new gTLD'],
  ['acme.co', 'acme.co', 'co is a TLD in its own right, not a suffix here'],
  ['deep.sub.acme.com', 'acme.com', 'two subdomains, single-label suffix'],
  ['acme-corp.io', 'acme-corp.io', 'hyphen in the registrable label'],
  ['  https://www.acme.io/  ', 'acme.io', 'surrounding whitespace'],
  ['https://www.acme.io/#fragment', 'acme.io', 'fragment'],
  // Rejections
  ['co.uk', null, 'a bare public suffix is not a registrable domain'],
  ['com.au', null, 'ditto for com.au'],
  ['localhost', null, 'single label'],
  ['1.2.3.4', null, 'IPv4 literal'],
  ['http://[::1]/x', null, 'IPv6 literal'],
  ['acme', null, 'no dot'],
  ['', null, 'empty string'],
  ['   ', null, 'whitespace only'],
  ['.acme.io', null, 'leading dot'],
  ['acme..io', null, 'double dot'],
  ['-acme.io', null, 'leading hyphen'],
  ['acme.io/path with space', 'acme.io', 'space appears only after the host'],
  ['not a domain at all', null, 'prose'],
  [null, null, 'null'],
  [undefined, null, 'undefined'],
  [12345, null, 'non-string'],
  [{}, null, 'object'],
];

describe('normalizeDomain', () => {
  for (const [input, expected, why] of DOMAIN_CASES) {
    test(`${JSON.stringify(input)} -> ${JSON.stringify(expected)} (${why})`, () => {
      assert.equal(normalizeDomain(input), expected);
    });
  }

  test('is idempotent: normalizing a result changes nothing', () => {
    for (const [input] of DOMAIN_CASES) {
      const once = normalizeDomain(input);
      if (once !== null) assert.equal(normalizeDomain(once), once, JSON.stringify(input));
    }
  });

  test('the vendored suffix list is non-trivial and contains no single-label entries', () => {
    assert.ok(PUBLIC_SUFFIXES.size > 100);
    for (const suffix of PUBLIC_SUFFIXES) {
      assert.ok(suffix.includes('.'), `${suffix} is single-label and would be redundant`);
    }
  });
});

// --------------------------------------------------------------------------
// normalizeLinkedInCompanyUrl
// --------------------------------------------------------------------------
const LINKEDIN_CASES = [
  ['linkedin.com/company/acme/', 'https://www.linkedin.com/company/acme', 'trailing slash, no scheme'],
  ['https://www.linkedin.com/company/acme', 'https://www.linkedin.com/company/acme', 'already canonical'],
  ['https://www.linkedin.com/company/Acme-Corp/', 'https://www.linkedin.com/company/acme-corp', 'uppercase slug'],
  ['http://linkedin.com/company/acme?trk=abc', 'https://www.linkedin.com/company/acme', 'http + query'],
  ['https://de.linkedin.com/company/acme', 'https://www.linkedin.com/company/acme', 'country subdomain'],
  ['https://www.linkedin.com/company/acme/about/', 'https://www.linkedin.com/company/acme', 'sub-page'],
  ['https://www.linkedin.com/company/acme/people/?x=1', 'https://www.linkedin.com/company/acme', 'sub-page + query'],
  ['https://www.linkedin.com/company/12345678', 'https://www.linkedin.com/company/12345678', 'numeric company id'],
  ['  https://www.linkedin.com/company/acme  ', 'https://www.linkedin.com/company/acme', 'whitespace'],
  ['https://www.linkedin.com/company/acme#feed', 'https://www.linkedin.com/company/acme', 'fragment'],
  ['https://www.linkedin.com/company/acme.io', 'https://www.linkedin.com/company/acme.io', 'dot inside slug'],
  // Rejections — a people or school URL is not a company identifier
  ['www.linkedin.com/in/pii-60c32bf3', null, 'people URL'],
  ['https://www.linkedin.com/in/pii-5dfa3744/', null, 'people URL with slug'],
  ['https://www.linkedin.com/school/mit/', null, 'school URL'],
  ['https://www.linkedin.com/showcase/acme/', null, 'showcase URL'],
  ['https://www.linkedin.com/company/', null, 'no slug'],
  ['https://www.linkedin.com/', null, 'root'],
  ['https://linkedin.com', null, 'no path at all'],
  ['https://notlinkedin.com/company/acme', null, 'lookalike host'],
  ['https://linkedin.com.evil.tld/company/acme', null, 'suffix-confusion host'],
  ['acme.io', null, 'not LinkedIn'],
  ['', null, 'empty'],
  [null, null, 'null'],
  [42, null, 'non-string'],
];

describe('normalizeLinkedInCompanyUrl', () => {
  for (const [input, expected, why] of LINKEDIN_CASES) {
    test(`${JSON.stringify(input)} -> ${JSON.stringify(expected)} (${why})`, () => {
      assert.equal(normalizeLinkedInCompanyUrl(input), expected);
    });
  }

  test('is idempotent', () => {
    for (const [input] of LINKEDIN_CASES) {
      const once = normalizeLinkedInCompanyUrl(input);
      if (once !== null) assert.equal(normalizeLinkedInCompanyUrl(once), once, JSON.stringify(input));
    }
  });

  test('every result is lowercase, https, www, and has no trailing slash', () => {
    for (const [input] of LINKEDIN_CASES) {
      const out = normalizeLinkedInCompanyUrl(input);
      if (out === null) continue;
      assert.equal(out, out.toLowerCase());
      assert.ok(out.startsWith('https://www.linkedin.com/company/'));
      assert.ok(!out.endsWith('/'));
      assert.ok(!out.includes('?'));
    }
  });
});

// --------------------------------------------------------------------------
// normalizeCompanyName
// --------------------------------------------------------------------------
const NAME_CASES = [
  ['Acme, Inc.', 'acme', 'comma + Inc.'],
  ['ACME INC', 'acme', 'uppercase, no punctuation'],
  ['Acme Inc', 'acme', 'plain Inc'],
  ['Acme, LLC', 'acme', 'LLC'],
  ['Acme L.L.C.', 'acme', 'dotted LLC'],
  ['Acme Ltd.', 'acme', 'Ltd'],
  ['Acme Limited', 'acme', 'Limited spelled out'],
  ['Acme Incorporated', 'acme', 'Incorporated spelled out'],
  ['Acme GmbH', 'acme', 'GmbH'],
  ['Acme Corp.', 'acme', 'Corp'],
  ['Acme Corporation', 'acme', 'Corporation'],
  ['Acme Co.', 'acme', 'Co'],
  ['Acme PLC', 'acme', 'PLC'],
  ['Acme S.A.S.', 'acme', 'SAS'],
  ['Acme B.V.', 'acme', 'BV'],
  ['Acme AG', 'acme', 'AG'],
  ['Acme S.r.l.', 'acme', 'SRL'],
  ['Acme Pty Ltd', 'acme', 'two stacked suffixes'],
  ['Acme Pte. Ltd.', 'acme', 'Singapore form'],
  ['Acme Group Holdings Ltd', 'acme', 'three stacked suffixes'],
  ['  Acme   Systems  ', 'acme systems', 'collapsed whitespace, no suffix'],
  ['Müller & Sons GmbH', 'muller sons', 'accent folded, ampersand as separator'],
  ['Ærø A/S', 'aero', 'ligature + Nordic legal form'],
  ['Łódź Software Sp', 'lodz software sp', 'Polish diacritics'],
  ["O'Neil Analytics", 'oneil analytics', 'apostrophe inside a token'],
  ['Acme (US) Inc', 'acme us', 'parentheses become separators'],
  ['Acme-Corp Inc.', 'acme-corp', 'hyphen kept inside the token'],
  ['Ltd', 'ltd', 'a name that is only a suffix is left alone'],
  ['Inc.', 'inc', 'ditto'],
  ['', null, 'empty'],
  ['   ', null, 'whitespace only'],
  ['!!!', null, 'punctuation only'],
  [null, null, 'null'],
  [undefined, null, 'undefined'],
  [7, null, 'non-string'],
];

describe('normalizeCompanyName', () => {
  for (const [input, expected, why] of NAME_CASES) {
    test(`${JSON.stringify(input)} -> ${JSON.stringify(expected)} (${why})`, () => {
      assert.equal(normalizeCompanyName(input), expected);
    });
  }

  test('"Acme, Inc." and "ACME INC" collide, which is the point', () => {
    assert.equal(normalizeCompanyName('Acme, Inc.'), normalizeCompanyName('ACME INC'));
  });

  test('is idempotent', () => {
    for (const [input] of NAME_CASES) {
      const once = normalizeCompanyName(input);
      if (once !== null) assert.equal(normalizeCompanyName(once), once, JSON.stringify(input));
    }
  });

  test('distinct companies do not collide', () => {
    const names = ['Akuvo', 'QCash', 'InvoiceCloud', 'Alloya', 'LumaMDX', 'Sumersports', 'Formstack'];
    const normalized = names.map(normalizeCompanyName);
    assert.equal(new Set(normalized).size, names.length);
  });
});

// --------------------------------------------------------------------------
// resolveIdentifier — priority order and confidence
// --------------------------------------------------------------------------
describe('resolveIdentifier', () => {
  test('website wins over LinkedIn and name, at high confidence', () => {
    assert.deepEqual(
      resolveIdentifier({
        name: 'Acme, Inc.',
        website: 'https://www.acme.io/about',
        linkedin: 'https://www.linkedin.com/company/acme',
      }),
      { kind: 'domain', value: 'acme.io', confidence: 'high' }
    );
  });

  test('no website -> LinkedIn, at high confidence', () => {
    assert.deepEqual(
      resolveIdentifier({ name: 'Acme, Inc.', website: null, linkedin: 'linkedin.com/company/Acme/' }),
      { kind: 'linkedin', value: 'https://www.linkedin.com/company/acme', confidence: 'high' }
    );
  });

  test('name only -> name, at LOW confidence (NEEDS_DECISION #5 default)', () => {
    assert.deepEqual(
      resolveIdentifier({ name: 'Acme, Inc.' }),
      { kind: 'name', value: 'acme', confidence: 'low' }
    );
  });

  test('an unusable website falls through to LinkedIn rather than failing', () => {
    const out = resolveIdentifier({ name: 'Acme', website: 'n/a', linkedin: 'linkedin.com/company/acme' });
    assert.equal(out.kind, 'linkedin');
  });

  test('a people LinkedIn URL is not an identifier and falls through to name', () => {
    const out = resolveIdentifier({ name: 'Acme Inc', linkedin: 'https://www.linkedin.com/in/pii-60c32bf3' });
    assert.deepEqual(out, { kind: 'name', value: 'acme', confidence: 'low' });
  });

  test('the alternate field spellings are accepted', () => {
    assert.equal(resolveIdentifier({ domain: 'acme.io' }).kind, 'domain');
    assert.equal(resolveIdentifier({ linkedin_url: 'linkedin.com/company/acme' }).kind, 'linkedin');
    assert.equal(resolveIdentifier({ company_name: 'Acme Inc' }).kind, 'name');
  });

  test('nothing usable -> null', () => {
    assert.equal(resolveIdentifier({ name: '', website: '', linkedin: '' }), null);
    assert.equal(resolveIdentifier({}), null);
    assert.equal(resolveIdentifier(null), null);
  });

  test('only domain and linkedin are ever high confidence', () => {
    for (const org of [
      { website: 'acme.io' },
      { linkedin: 'linkedin.com/company/acme' },
      { name: 'Acme' },
    ]) {
      const out = resolveIdentifier(org);
      assert.equal(out.confidence, out.kind === 'name' ? 'low' : 'high');
    }
  });
});
