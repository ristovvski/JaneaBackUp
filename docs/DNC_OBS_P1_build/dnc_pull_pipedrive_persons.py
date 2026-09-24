"""
Phase A of the People-DNC identity resolution (per owner's GO w/ 3 constraints, 2026-08-07):
Bulk-pull ALL Pipedrive persons ONCE, build local indexes (li_url_canon, email_lc, member_id),
so the 23,838-row seed resolves entirely in-memory with zero per-row API calls.

DO NOT RUN THE FULL PULL DURING THE FLIP WINDOW. This is throttled + checkpointed + resumable:
a crash/interrupt at any page picks back up from PERSONS_CURSOR_FILE, never restarts from zero.

Read-only. Makes zero writes to Pipedrive.

Usage:
  python dnc_pull_pipedrive_persons.py            # resumes/continues the pull
  python dnc_pull_pipedrive_persons.py --sanity    # pulls exactly one page (~100 persons), for testing only
"""
import os, sys, json, time, ssl, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
PERSONS_CACHE_FILE = os.path.join(HERE, "fixtures", "pipedrive_persons_cache.jsonl")
CURSOR_FILE = os.path.join(HERE, "fixtures", "pipedrive_persons_cache.cursor")
INDEX_FILE = os.path.join(HERE, "fixtures", "pipedrive_persons_index.json")

LI_URL_FIELD_KEY = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"   # lh_linkedin_profile_url -- SAME field WF-1's resolver uses. Do not swap for a different LinkedIn-shaped field.
MEMBER_ID_FIELD_KEY = "010fc51128116e8c73ae2b33fd52fd4537451f2b"  # lh_member_id -- W1.0.16 fallback field

PAGE_LIMIT = 500
THROTTLE_SECONDS = 0.3  # be gentle -- this shares rate limits with live WF-1/WF-2 traffic


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def make_ctx():
    ca = os.environ.get("REQUESTS_CA_BUNDLE")
    if ca and os.path.exists(ca):
        return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


def get_json(url, ctx, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def canon_li(url):
    import re
    if not url:
        return None
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.IGNORECASE)
    if not m:
        return None
    slug = m.group(1).split("?")[0].split("#")[0].rstrip("/")
    return slug.lower()


def extract_custom(person, field_key):
    cf = person.get("custom_fields") or {}
    if isinstance(cf, dict):
        val = cf.get(field_key)
        if isinstance(val, dict):
            return val.get("value")
        return val
    return None


def pull_all_persons(token, ctx, sanity_only=False):
    os.makedirs(os.path.dirname(PERSONS_CACHE_FILE), exist_ok=True)

    cursor = None
    if os.path.exists(CURSOR_FILE) and not sanity_only:
        with open(CURSOR_FILE, encoding="utf-8") as f:
            cursor = f.read().strip() or None
        print(f"resuming from checkpoint cursor: {cursor!r}")

    mode = "a" if (cursor and not sanity_only) else "w"
    pulled = 0
    with open(PERSONS_CACHE_FILE, mode, encoding="utf-8") as out:
        while True:
            params = {"limit": PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            base = os.environ["PIPEDRIVE_API_TOKEN"]  # noqa -- token goes in header ideally, kept here minimal for v2
            url = "https://api.pipedrive.com/api/v2/persons?" + urllib.parse.urlencode(params)
            req_url = url + f"&api_token={base}"
            data = get_json(req_url, ctx)

            items = data.get("data") or []
            for p in items:
                out.write(json.dumps(p) + "\n")
            pulled += len(items)
            out.flush()

            next_cursor = (data.get("additional_data") or {}).get("next_cursor")
            print(f"page pulled: {len(items)} persons (running total {pulled}), next_cursor={next_cursor!r}")

            if sanity_only:
                print("SANITY MODE: stopping after one page, not writing checkpoint.")
                return pulled

            if not next_cursor:
                if os.path.exists(CURSOR_FILE):
                    os.remove(CURSOR_FILE)
                print(f"DONE. Total persons pulled: {pulled}")
                return pulled

            cursor = next_cursor
            with open(CURSOR_FILE, "w", encoding="utf-8") as cf:
                cf.write(cursor)

            time.sleep(THROTTLE_SECONDS)


def build_indexes():
    # B19/DEL discipline: persons/search silently returns soft-deleted records with no is_deleted
    # field to filter on. This v2 /persons list DOES carry is_deleted -- use it. Deleted persons are
    # indexed separately (by_li_url_canon_deleted / by_email_lc_deleted) so the resolver can see and
    # report a "matched a deleted person" case explicitly, instead of silently matching a dead record
    # or silently dropping the signal.
    by_li, by_li_deleted = {}, {}
    by_email, by_email_deleted = {}, {}
    by_member_id, by_member_id_deleted = {}, {}
    total, total_deleted = 0, 0
    with open(PERSONS_CACHE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            total += 1
            pid = p.get("id")
            deleted = bool(p.get("is_deleted"))
            if deleted:
                total_deleted += 1
            li_map = by_li_deleted if deleted else by_li
            email_map = by_email_deleted if deleted else by_email
            member_map = by_member_id_deleted if deleted else by_member_id

            li_raw = extract_custom(p, LI_URL_FIELD_KEY)
            slug = canon_li(li_raw) if li_raw else None
            if slug:
                li_map.setdefault(slug, []).append(pid)

            for e in (p.get("emails") or p.get("email") or []):
                addr = e.get("value") if isinstance(e, dict) else e
                if addr:
                    email_map.setdefault(addr.strip().lower(), []).append(pid)

            member_id = extract_custom(p, MEMBER_ID_FIELD_KEY)
            if member_id:
                member_map.setdefault(str(member_id), []).append(pid)

    index = {
        "total_persons_indexed": total,
        "total_deleted_persons_indexed": total_deleted,
        "by_li_url_canon": by_li,
        "by_email_lc": by_email,
        "by_member_id": by_member_id,
        "by_li_url_canon_deleted": by_li_deleted,
        "by_email_lc_deleted": by_email_deleted,
        "by_member_id_deleted": by_member_id_deleted,
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f)
    print(f"Index built: {total} live persons ({total_deleted} soft-deleted, indexed separately), "
          f"{len(by_li)} distinct live LI slugs ({len(by_li_deleted)} deleted), "
          f"{len(by_email)} distinct live emails ({len(by_email_deleted)} deleted), "
          f"{len(by_member_id)} distinct live member_ids ({len(by_member_id_deleted)} deleted)")
    print(f"Wrote {INDEX_FILE}")


if __name__ == "__main__":
    load_env()
    ctx = make_ctx()
    sanity = "--sanity" in sys.argv
    pull_all_persons(os.environ["PIPEDRIVE_API_TOKEN"], ctx, sanity_only=sanity)
    if not sanity:
        build_indexes()
    else:
        print("Sanity pull complete. Full run NOT triggered -- re-run without --sanity when authorized.")
