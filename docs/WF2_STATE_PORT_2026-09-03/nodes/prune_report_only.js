const p = $input.first().json;
const unknown = Object.keys(p.unknown_families || {});
return [{ json: { ...p, deleted: 0,
  outcome: p.dry_run ? 'DRY RUN - nothing deleted'
         : (p.expired_found === 0 ? 'nothing past its family retention' : 'no rows selected'),
  note: unknown.length
      ? 'RETAINED AND REPORTED: ' + unknown.length + ' family/families this prune does not know ('
        + unknown.join(', ') + '). Add a retention before they grow without bound.'
      : null } }];
