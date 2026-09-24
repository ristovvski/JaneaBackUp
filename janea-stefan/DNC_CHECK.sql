-- DNC_CHECK.sql — one call that answers "may we contact this person?"
--
-- WHAT IT CORRECTS. The documented Clay setup (SUPABASE_LOOKUP.md) does two separate Lookup columns:
-- person by identity_key, company by email domain. That is right about the TWO checks and wrong
-- about the first one: identity_key is "LinkedIn slug if it resolves, else email", so a person who
-- entered the registry by EMAIL (a Smartlead reply, say) is keyed by that email - and when Clay later
-- sees the same person WITH a LinkedIn URL, its formula produces the slug and the lookup misses the
-- row. The ledger itself never makes that mistake: DNC__UpsertLedger__v1 looks up by LinkedIn AND by
-- email. This function does the same, and does the company check in the same call.
--
-- CONTRACT
--   select dnc_check(p_linkedin_url => '...', p_email => '...');
--   POST /rest/v1/rpc/dnc_check  {"p_linkedin_url": "...", "p_email": "..."}
-- Either argument may be null. Returns jsonb:
--   blocked            true if ANY matched person row or the company domain is status = 'active'
--   block_reasons      ["person_active", "company_active"] - which of the two fired
--   identity           the normalized identity, exactly as normalizeIdentityV1 would compute it
--   domain             the email's domain, lowercased, leading www. stripped
--   persons            every registry row this person could be filed under (by either identity)
--   company            the dnc_domains row for the domain, or null
--   norm_v             'v1'
-- Only status = 'active' blocks. A 'removed' row is reported but does not block (tombstoned, not
-- deleted). A row that is active but past expires_at is reported with expired_but_active = true and
-- STILL blocks: whether an expired row should stop blocking is a policy decision, and the expiry job
-- that used to flip such rows is currently inactive. This function does not make that decision.
--
-- NORMALIZATION is a port of normalizeIdentityV1 (DNC_OBS_P1_build/subworkflows/lib/normalize_v1.js),
-- frozen as v1. Four details the prose in NORMALIZATION_RULES.md does not state, taken from the code:
--   * the LinkedIn URL is trimmed BEFORE lowercasing (JavaScript trim: all Unicode whitespace + BOM)
--   * lowercasing happens BEFORE percent-decoding, so an encoded capital (%41) decodes to 'A'
--   * a malformed percent sequence keeps the UNDECODED slug - it does not fail the identity
--   * after the second trailing-slash strip the slug is trimmed again
-- Tested byte-for-byte against the real JavaScript function; see test_dnc_check.mjs.
--
-- SECURITY: SECURITY INVOKER, so it reads through the existing read-only RLS policies and grants
-- nothing the caller did not already have. It writes nothing.
--
-- DEPLOY: paste into the Supabase SQL editor (PostgREST cannot create functions). Idempotent.

-- ---------------------------------------------------------------- helpers
create or replace function public.dnc_js_trim(p text)
returns text
language sql
immutable
parallel safe
as $$
  -- JavaScript String.prototype.trim: WhiteSpace + LineTerminator + BOM
  select regexp_replace(
           p,
           '^[ \t\n\v\f\r   -     　﻿]+'
           || '|[ \t\n\v\f\r   -     　﻿]+$',
           '', 'g');
$$;

create or replace function public.dnc_url_decode_v1(p text)
returns text
language plpgsql
immutable
strict
parallel safe
as $$
-- decodeURIComponent: %XX sequences become bytes, the result must be valid UTF-8. Anything malformed
-- returns NULL so the caller keeps the undecoded value, exactly as the JavaScript catch does.
declare
  i   int := 1;
  n   int := length(p);
  buf bytea := ''::bytea;
  ch  text;
  hx  text;
begin
  while i <= n loop
    ch := substr(p, i, 1);
    if ch = '%' then
      hx := substr(p, i + 1, 2);
      if length(hx) < 2 or hx !~ '^[0-9A-Fa-f]{2}$' then
        return null;
      end if;
      buf := buf || decode(hx, 'hex');
      i := i + 3;
    else
      buf := buf || convert_to(ch, 'UTF8');
      i := i + 1;
    end if;
  end loop;
  return convert_from(buf, 'UTF8');
exception when others then
  return null;            -- invalid UTF-8, or a NUL byte Postgres text cannot hold
end;
$$;

create or replace function public.dnc_identity_v1(
  p_linkedin_url text,
  p_email text,
  out identity_key text,
  out linkedin_slug text,
  out linkedin_url_norm text,
  out email_lc text)
language plpgsql
immutable
parallel safe
as $$
declare
  raw      text;
  after_in text;
  slug     text;
  dec      text;
  e        text;
  at_pos   int;
begin
  -- LinkedIn: trim, lowercase, first /in/<segment>, strip trailing slashes, decode, strip, trim
  if p_linkedin_url is not null and public.dnc_js_trim(p_linkedin_url) <> '' then
    raw := lower(public.dnc_js_trim(p_linkedin_url));
    after_in := substring(raw from '/in/([^/?#]+)');
    if after_in is not null and after_in <> '' then
      slug := regexp_replace(after_in, '/+$', '');
      dec := public.dnc_url_decode_v1(slug);
      if dec is not null then
        slug := dec;
      end if;
      slug := public.dnc_js_trim(regexp_replace(slug, '/+$', ''));
      if slug <> '' then
        linkedin_slug := slug;
        linkedin_url_norm := 'https://www.linkedin.com/in/' || slug;
      end if;
    end if;
  end if;

  -- Email: trim + lowercase ONLY; valid iff '@' is not first and a '.' follows it
  if p_email is not null and public.dnc_js_trim(p_email) <> '' then
    e := lower(public.dnc_js_trim(p_email));
    at_pos := strpos(e, '@');
    if at_pos > 1 and strpos(substr(e, at_pos), '.') > 0 then
      email_lc := e;
    end if;
  end if;

  identity_key := coalesce(linkedin_slug, email_lc);
end;
$$;

-- ---------------------------------------------------------------- the check
create or replace function public.dnc_check(
  p_linkedin_url text default null,
  p_email text default null)
returns jsonb
language plpgsql
stable
security invoker
set search_path = public, pg_temp
as $$
declare
  id       record;
  dom      text;
  persons  jsonb;
  company  jsonb;
  p_active boolean;
  c_active boolean;
  reasons  jsonb := '[]'::jsonb;
begin
  select * into id from public.dnc_identity_v1(p_linkedin_url, p_email);

  if id.email_lc is not null then
    dom := substring(id.email_lc from '@([^@]+)$');
    dom := regexp_replace(dom, '^www\.', '');
  end if;

  -- every row this person could be filed under: the slug OR the email, as key or as column
  select coalesce(jsonb_agg(jsonb_build_object(
           'identity_key', r.identity_key,
           'matched_by', case
                           when id.linkedin_slug is not null and r.identity_key = id.linkedin_slug
                             then 'linkedin_slug'
                           when id.email_lc is not null and r.identity_key = id.email_lc
                             then 'email'
                           when id.linkedin_url_norm is not null
                                and r.linkedin_url_norm = id.linkedin_url_norm
                             then 'linkedin_url_norm'
                           else 'email_lc'
                         end,
           'status', r.status,
           'reason', r.reason,
           'entry_type', r.entry_type,
           'reply_category', r.reply_category,
           'added_at', r.added_at,
           'expires_at', r.expires_at,
           'removed_at', r.removed_at,
           'expired_but_active', (r.status = 'active' and r.expires_at is not null
                                  and r.expires_at < now()))
           order by r.status = 'active' desc, r.added_at desc), '[]'::jsonb)
    into persons
    from public.dnc_registry r
   where (id.linkedin_slug is not null
          and (r.identity_key = id.linkedin_slug or r.linkedin_url_norm = id.linkedin_url_norm))
      or (id.email_lc is not null
          and (r.identity_key = id.email_lc or r.email_lc = id.email_lc));

  if dom is not null then
    select jsonb_build_object('domain', d.domain, 'status', d.status, 'reason', d.reason,
                              'added_at', d.added_at)
      into company
      from public.dnc_domains d
     where d.domain = dom;
  end if;

  p_active := exists (select 1 from jsonb_array_elements(persons) x
                       where x->>'status' = 'active');
  c_active := coalesce(company->>'status' = 'active', false);
  if p_active then reasons := reasons || '"person_active"'::jsonb; end if;
  if c_active then reasons := reasons || '"company_active"'::jsonb; end if;

  return jsonb_build_object(
    'blocked', p_active or c_active,
    'block_reasons', reasons,
    'identity', jsonb_build_object('identity_key', id.identity_key,
                                   'linkedin_slug', id.linkedin_slug,
                                   'linkedin_url_norm', id.linkedin_url_norm,
                                   'email_lc', id.email_lc),
    'domain', dom,
    'persons', persons,
    'company', company,
    'norm_v', 'v1');
end;
$$;

-- ---------------------------------------------------------------- grants
revoke all on function public.dnc_check(text, text) from public;
grant execute on function public.dnc_check(text, text) to anon, authenticated;
grant execute on function public.dnc_identity_v1(text, text) to anon, authenticated;
grant execute on function public.dnc_url_decode_v1(text) to anon, authenticated;
grant execute on function public.dnc_js_trim(text) to anon, authenticated;

comment on function public.dnc_check(text, text) is
  'May we contact this person? Person (by LinkedIn slug OR email) + company (email domain). '
  'Only status=active blocks. See DNC_CHECK.sql header for the contract.';
