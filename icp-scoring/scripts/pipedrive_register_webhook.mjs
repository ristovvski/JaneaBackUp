#!/usr/bin/env node
// scripts/pipedrive_register_webhook.mjs — register deal.create -> the DEV
// Path A webhook URL.
//
// IDEMPOTENT. Matching is on (event_action, event_object, subscription_url).
// An identical subscription is adopted, not duplicated: a duplicate webhook
// means every deal fires the workflow twice, and while Dedupe would swallow
// the second delivery, the right place to not have two is here.
//
//   ICP_DEV_WEBHOOK_URL=https://... PIPEDRIVE_API_TOKEN=... npm run pipedrive:webhook
//   ... --dry-run     show what would happen, write nothing
//   ... --list        list existing webhooks and exit
//
// Basic auth on the endpoint is REQUIRED by default (invariant: every webhook
// is authenticated). Pipedrive supports it on the subscription:
//   http_auth_user / http_auth_password  — "The HTTP basic auth username /
//   password of the subscription URL endpoint (if required)"
// Set ICP_WEBHOOK_BASIC_USER and ICP_WEBHOOK_BASIC_PASSWORD to the same values
// configured on the n8n webhook node's Basic Auth credential. Pass
// --allow-unauthenticated only for a throwaway DEV probe, and expect the
// static review to flag the workflow if the node has no auth.
//
// API evidence (developers.pipedrive.com, Webhooks):
//   POST /api/v1/webhooks
//     required: subscription_url, event_action, event_object, name
//     optional: user_id, http_auth_user, http_auth_password, version ('1.0'|'2.0', default '2.0')
//   event_action: create | change | delete | *
//   event_object: activity | deal | lead | note | organization | person | ... | *
//   GET    /api/v1/webhooks
//   DELETE /api/v1/webhooks/{id}
//
// deal.added in the build task is Pipedrive's event_action=create on
// event_object=deal. There is no "added" action in the API.

const BASE = 'https://api.pipedrive.com';

const token = process.env.PIPEDRIVE_API_TOKEN;
const url = process.env.ICP_DEV_WEBHOOK_URL;
const basicUser = process.env.ICP_WEBHOOK_BASIC_USER || null;
const basicPassword = process.env.ICP_WEBHOOK_BASIC_PASSWORD || null;

const dryRun = process.argv.includes('--dry-run');
const listOnly = process.argv.includes('--list');
const allowUnauthenticated = process.argv.includes('--allow-unauthenticated');

const WEBHOOK_NAME = 'ICP v5 — deal.create -> WF-ICP-Score (DEV)';
const EVENT_ACTION = 'create';
const EVENT_OBJECT = 'deal';
const VERSION = '2.0';

if (!token) {
  process.stderr.write('PIPEDRIVE_API_TOKEN is not set.\n');
  process.exit(1);
}

async function api(method, path, body = null) {
  const response = await fetch(new URL(path, BASE), {
    method,
    headers: {
      'x-api-token': token,
      accept: 'application/json',
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 429) {
    const wait = Number(response.headers.get('retry-after') || 2) * 1000;
    await new Promise((r) => setTimeout(r, wait));
    return api(method, path, body);
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status}: ${text.slice(0, 400)}`);
  }
  return text ? JSON.parse(text) : {};
}

/** Never print a subscription URL in full: the path is the endpoint's secret. */
function redactUrl(value) {
  try {
    const u = new URL(value);
    const parts = u.pathname.split('/').filter(Boolean);
    const tail = parts.length > 0 ? parts[parts.length - 1] : '';
    const masked = tail.length > 6 ? `${tail.slice(0, 3)}…${tail.slice(-2)}` : '…';
    return `${u.origin}/${parts.slice(0, -1).join('/')}${parts.length > 1 ? '/' : ''}${masked}`;
  } catch {
    return '(unparseable url)';
  }
}

const existing = (await api('GET', '/api/v1/webhooks')).data || [];

if (listOnly) {
  process.stdout.write(`${existing.length} webhook(s) on this account:\n`);
  for (const hook of existing) {
    process.stdout.write(
      `  #${hook.id}  ${hook.event_action}.${hook.event_object}` +
      `  v${hook.version || '?'}  ${redactUrl(hook.subscription_url)}` +
      `  auth=${hook.http_auth_user ? 'basic' : 'none'}\n`
    );
  }
  process.exit(0);
}

if (!url) {
  process.stderr.write(
    'ICP_DEV_WEBHOOK_URL is not set.\n\n' +
    'Import n8n/workflows/WF-ICP-Score.dev.json into the DEV project, open the\n' +
    'Pipedrive webhook node, and copy its PRODUCTION webhook URL.\n\n' +
    '  ICP_DEV_WEBHOOK_URL=https://... PIPEDRIVE_API_TOKEN=... npm run pipedrive:webhook\n'
  );
  process.exit(1);
}

if (!/^https:\/\//.test(url)) {
  process.stderr.write(`ICP_DEV_WEBHOOK_URL must be https, got: ${redactUrl(url)}\n`);
  process.exit(1);
}

if ((!basicUser || !basicPassword) && !allowUnauthenticated) {
  process.stderr.write(
    'Refusing to register an unauthenticated webhook.\n\n' +
    'Every webhook endpoint must verify the caller. Pipedrive supports HTTP basic\n' +
    'auth on the subscription, so set both of:\n\n' +
    '  ICP_WEBHOOK_BASIC_USER=...\n' +
    '  ICP_WEBHOOK_BASIC_PASSWORD=...\n\n' +
    'to the same values as the n8n webhook node\'s Basic Auth credential.\n' +
    'Pass --allow-unauthenticated only for a throwaway DEV probe.\n'
  );
  process.exit(1);
}

// Idempotency: same action + object + destination is the same subscription.
const match = existing.find(
  (hook) => hook.event_action === EVENT_ACTION &&
            hook.event_object === EVENT_OBJECT &&
            hook.subscription_url === url
);

if (match) {
  process.stdout.write(
    `FOUND    webhook #${match.id} — ${EVENT_ACTION}.${EVENT_OBJECT} -> ${redactUrl(url)}\n` +
    `         version ${match.version || '?'}, auth ${match.http_auth_user ? 'basic' : 'NONE'}\n` +
    `\n0 created, 1 found. Nothing changed.\n`
  );
  if (!match.http_auth_user && !allowUnauthenticated) {
    process.stdout.write(
      '\nWARNING: the existing subscription has no basic auth. Pipedrive cannot add auth to\n' +
      'a live webhook, so to fix it: DELETE /api/v1/webhooks/' + match.id + ' and re-run this\n' +
      'script with the credentials set.\n'
    );
    process.exit(2);
  }
  process.exit(0);
}

// A same-event subscription pointing somewhere else is worth surfacing: it is
// how a workflow ends up firing twice from two n8n instances.
const otherDestination = existing.filter(
  (hook) => hook.event_action === EVENT_ACTION && hook.event_object === EVENT_OBJECT
);
if (otherDestination.length > 0) {
  process.stdout.write(
    `note: ${otherDestination.length} other ${EVENT_ACTION}.${EVENT_OBJECT} webhook(s) already exist:\n`
  );
  for (const hook of otherDestination) {
    process.stdout.write(`  #${hook.id} -> ${redactUrl(hook.subscription_url)}\n`);
  }
  process.stdout.write('These are left alone. Confirm none of them is a second copy of this workflow.\n\n');
}

const body = {
  subscription_url: url,
  event_action: EVENT_ACTION,
  event_object: EVENT_OBJECT,
  name: WEBHOOK_NAME,
  version: VERSION,
};
if (basicUser && basicPassword) {
  body.http_auth_user = basicUser;
  body.http_auth_password = basicPassword;
}

if (dryRun) {
  process.stdout.write(
    'DRY RUN — would POST /api/v1/webhooks with:\n' +
    `  subscription_url : ${redactUrl(url)}\n` +
    `  event_action     : ${EVENT_ACTION}\n` +
    `  event_object     : ${EVENT_OBJECT}\n` +
    `  name             : ${WEBHOOK_NAME}\n` +
    `  version          : ${VERSION}\n` +
    `  http_auth_user   : ${basicUser ? '(set)' : '(none)'}\n` +
    `  http_auth_password: ${basicPassword ? '(set, not shown)' : '(none)'}\n` +
    '\nNothing was written.\n'
  );
  process.exit(0);
}

const created = await api('POST', '/api/v1/webhooks', body);
const hook = created.data || {};
process.stdout.write(
  `CREATED  webhook #${hook.id} — ${EVENT_ACTION}.${EVENT_OBJECT} -> ${redactUrl(url)}\n` +
  `         version ${hook.version || VERSION}, auth ${body.http_auth_user ? 'basic' : 'NONE'}\n` +
  `\n1 created, 0 found.\n` +
  `\nTo remove it:  curl -X DELETE -H "x-api-token: \$PIPEDRIVE_API_TOKEN" \\\n` +
  `  ${BASE}/api/v1/webhooks/${hook.id}\n`
);
