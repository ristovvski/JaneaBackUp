#!/usr/bin/env python3
"""Build a Git audit repository with baseline + one commit per W1.0 fix.

The final workflow byte-for-byte matches the supplied W1.0 patched JSON.
Intermediate commits are cumulative and intentionally keep each fix isolated.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path('/mnt/data')
BASE = ROOT / 'WF-1 HeyReach Receiver (1)(2).json'
FINAL = ROOT / 'WF-1 HeyReach Receiver - W1.0 patched.json'
REPO = ROOT / 'WF1_W1.0_AUDIT_REPO'


def run(*args: str, cwd: Path = REPO) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save(workflow: dict[str, Any]) -> None:
    (REPO / 'wf1.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def nodes(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n['name']: n for n in workflow['nodes']}


def copy_node(workflow: dict[str, Any], final: dict[str, Any], name: str) -> None:
    wm = nodes(workflow)
    fm = nodes(final)
    value = copy.deepcopy(fm[name])
    if name in wm:
        idx = next(i for i, n in enumerate(workflow['nodes']) if n['name'] == name)
        workflow['nodes'][idx] = value
    else:
        workflow['nodes'].append(value)


def set_conn(workflow: dict[str, Any], final: dict[str, Any], name: str) -> None:
    workflow['connections'][name] = copy.deepcopy(final['connections'][name])


COMMIT_INDEX = 0


def commit(message: str) -> None:
    global COMMIT_INDEX
    save(CURRENT)
    run('git', 'add', 'wf1.json')
    # Fixed timestamps make the audit bundle reproducible across rebuilds.
    stamp = f'2026-07-12T00:{COMMIT_INDEX:02d}:00Z'
    env = os.environ.copy()
    env['GIT_AUTHOR_DATE'] = stamp
    env['GIT_COMMITTER_DATE'] = stamp
    subprocess.run(
        ['git', 'commit', '-m', message],
        cwd=REPO,
        check=True,
        env=env,
    )
    COMMIT_INDEX += 1


base = load(BASE)
final = load(FINAL)
CURRENT = copy.deepcopy(base)

if REPO.exists():
    shutil.rmtree(REPO)
REPO.mkdir(parents=True)
run('git', 'init', '-b', 'main')
run('git', 'config', 'user.name', 'OpenAI Release Audit')
run('git', 'config', 'user.email', 'release-audit@example.invalid')

# Baseline
commit('baseline')

# F1: reply Normalize keys and canonical conversation. Keep old first-lead behavior until F4.
copy_node(CURRENT, final, 'M7 Build')
code = nodes(CURRENT)['M7 Build']['parameters']['jsCode']
selector = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}
const selectedLead = selectLead(leadResp && leadResp.data);"""
old_selection = """const leadsForReply = (leadResp && Array.isArray(leadResp.data)) ? leadResp.data : [];
const selectedLead = leadsForReply.length ? leadsForReply[0] : null;"""
if selector not in code:
    raise SystemExit('F1 selector block not found')
nodes(CURRENT)['M7 Build']['parameters']['jsCode'] = code.replace(selector, old_selection)
commit('F1: align reply branch with Normalize msgs/conv contract')

# F2: 3-way gate + converged lead_id. Keep first-result selection until F4.
for name in ['Lead Create Gate', 'Create Activity']:
    copy_node(CURRENT, final, name)
for name in ['Select Existing Lead', 'Lead From Create', 'Sent IF Lead ID']:
    copy_node(CURRENT, final, name)
sel = nodes(CURRENT)['Select Existing Lead']['parameters']['jsCode']
shared = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}
const lead = selectLead($json.data);"""
first = """const leads = Array.isArray($json.data) ? $json.data : [];
const lead = leads.length ? leads[0] : null;"""
if shared not in sel:
    raise SystemExit('F2 selector block not found')
nodes(CURRENT)['Select Existing Lead']['parameters']['jsCode'] = sel.replace(shared, first)
for name in ['Lead Create Gate', 'Create Lead', 'Lead From Create', 'Select Existing Lead', 'Sent IF Lead ID']:
    set_conn(CURRENT, final, name)
commit('F2: route empty/existing/invalid lead-search responses separately')

# F3: labels use effective rank; late accepted can fill connected_at without rollback.
for name in ['M5 IF Rank Accepted', 'M5 Person Patch Accepted', 'M5 Labels Compute', 'M7 Labels Compute']:
    copy_node(CURRENT, final, name)
# Preserve original M5 newest-lead logic until F4.
m5 = nodes(CURRENT)['M5 Labels Compute']['parameters']['jsCode']
shared_m5 = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}
const lead = selectLead($json.data);"""
legacy_m5 = """const leads = Array.isArray($json.data) ? $json.data : [];
const active = leads.filter(l => !l.is_archived);
const pool = active.length ? active : leads;
pool.sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0));
const lead = pool[0] || null;"""
if shared_m5 not in m5:
    raise SystemExit('F3 M5 selector block not found')
nodes(CURRENT)['M5 Labels Compute']['parameters']['jsCode'] = m5.replace(shared_m5, legacy_m5)
# Preserve old M7 first-result behavior until F4.
m7 = nodes(CURRENT)['M7 Labels Compute']['parameters']['jsCode']
shared_m7 = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}
const lead = selectLead($('M7 Lead Get').item.json.data);"""
legacy_m7 = """const leads = Array.isArray($('M7 Lead Get').item.json.data) ? $('M7 Lead Get').item.json.data : [];
const lead = leads.length ? leads[0] : null;"""
if shared_m7 not in m7:
    raise SystemExit('F3 M7 selector block not found')
nodes(CURRENT)['M7 Labels Compute']['parameters']['jsCode'] = m7.replace(shared_m7, legacy_m7)
commit('F3: derive labels from effective lifecycle rank')

# F4: one identical newest-active lead selector everywhere.
for name in ['M5 Labels Compute', 'M6 Build', 'M7 Build', 'M7 Labels Compute', 'Select Existing Lead']:
    copy_node(CURRENT, final, name)
commit('F4: unify newest-active lead selection across branches')

# F5: lead-id gates and contextual warnings. Reply-activity gate is added now and connected in F8.
for name in ['M5 IF Lead ID', 'M6 IF Lead ID', 'M7 IF Lead ID', 'M7 IF Reply Activity Lead', 'M8 IF Lead ID']:
    copy_node(CURRENT, final, name)
for name in ['M5 Slack Warn', 'M6 Slack Warn', 'M7 Slack Warn']:
    copy_node(CURRENT, final, name)
for name in ['M5 Labels Compute', 'M5 IF Lead ID', 'M6 Build', 'M6 IF Lead ID', 'M7 Labels Compute', 'M7 IF Lead ID', 'M8 IF Transition', 'M8 IF Lead ID']:
    set_conn(CURRENT, final, name)
# Until F8 exists, a valid M7 lead patch continues directly to transition handling.
CURRENT['connections']['M7 Lead Patch'] = {
    'main': [[{'node': 'M8 IF Transition', 'type': 'main', 'index': 0}]]
}
commit('F5: gate all lead-bound writes and warn on missing lead')

# F6: skip empty-email searches and omit empty emails[] on Person create.
copy_node(CURRENT, final, 'Person Create')
for name in ['IF Email Present', 'M5 IF Email Present', 'M6 IF Email Present', 'M7 IF Email Present']:
    copy_node(CURRENT, final, name)
for name in ['Org From Search', 'Org From Create', 'Org None', 'IF Email Present',
             'M5 IF Email Present', 'M6 IF Email Present', 'M7 IF Email Present', 'Switch']:
    set_conn(CURRENT, final, name)
commit('F6: guard optional email searches and Person emails payload')

# F7: disable blind retries on all currently existing create POST nodes.
for name in ['Org Create', 'Person Create', 'Create Lead', 'Create Activity', 'M6 Activity', 'M8 Task']:
    copy_node(CURRENT, final, name)
commit('F7: disable retries on entity-creating POST requests')

# F8: completed reply activity on every reply, guarded by lead_id.
copy_node(CURRENT, final, 'M7 Reply Activity')
for name in ['M7 Lead Patch', 'M7 IF Reply Activity Lead', 'M7 Reply Activity']:
    set_conn(CURRENT, final, name)
commit('F8: add completed Pipedrive activity for every reply')

# Required export hygiene. Re-serialize connections in the deterministic final order.
CURRENT.pop('pinData', None)
CURRENT['connections'] = copy.deepcopy(final['connections'])
CURRENT['active'] = False
commit('chore: remove pins and stale connection records')

# Final byte-for-byte proof.
produced = (REPO / 'wf1.json').read_bytes()
expected = FINAL.read_bytes()
if produced != expected:
    (ROOT / 'audit_repo_final_mismatch.json').write_bytes(produced)
    raise SystemExit('Audit repo final workflow does not byte-match final patched JSON')

run('git', 'log', '--oneline', '--reverse')
print(f'Audit repository created at {REPO}')
