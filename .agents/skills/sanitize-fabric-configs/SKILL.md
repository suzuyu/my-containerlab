---
name: sanitize-fabric-configs
description: Sanitize and inspect public lab network configurations under nxos_fabric. Use before adding, committing, pushing, or publishing NX-OS or cEOS configuration samples, and after regenerating as-changes configs. Remove username credential lines, reject globally routable management endpoints and private keys, and report intentionally retained SNMP, NTP, and logging sample settings.
---

# Sanitize Fabric Configs

## Establish scope

Inspect `git status --short` and limit changes to the requested files under `nxos_fabric/`. Preserve
unrelated and ignored runtime artifacts. Do not inspect or publish `operations/`, `raw/`, `logs/`,
`clab-*`, backup directories, credential inventories, or support bundles.

Treat device access, `containerlab deploy`, config push, and `write memory` as separate operations that
require an explicit user request. Sanitization is an offline file operation.

## Apply the publication policy

- Remove every active or commented `username` configuration line from public NX-OS and cEOS samples.
  Replace each consecutive block with `! credential lines omitted from public lab sample` so the
  omission remains visible. Rely on the documented containerlab default user at lab startup.
- Fail when a config contains a private key, an `enable secret`, or a globally routable IP endpoint.
- Retain SNMP communities and HomeLab-specific SNMP, NTP, and logging destinations only when the user
  confirms they are disposable lab samples and every destination is private, loopback, link-local,
  documentation, CGNAT, or otherwise non-global. Report retained directives; do not silently treat
  them as production-safe credentials.
- If a retained community or password is reused outside this disposable lab, stop and recommend
  rotation before publication.
- Do not copy raw credential values into reports, commit messages, or PR descriptions.

## Run the sanitizer

Check without modifying files:

```bash
python3 .agents/skills/sanitize-fabric-configs/scripts/sanitize_configs.py --root nxos_fabric
```

When the user has authorized sanitization, apply it and check again:

```bash
python3 .agents/skills/sanitize-fabric-configs/scripts/sanitize_configs.py \
  --root nxos_fabric --write
python3 .agents/skills/sanitize-fabric-configs/scripts/sanitize_configs.py --root nxos_fabric
```

Review the exact diff after writing. Never use a broad stage command as part of this skill.

## Handle generated configs

`nxos_fabric/nxos_multisite/scripts/generate_as_changes.py` is a maintained reproducibility tool. It
regenerates 28 `as-changes` configs from `as-equals`; include it in Git and rerun sanitization after
generation.

`standardize_nxos_management.py` is a local, hard-coded bulk management-policy rewrite. Keep it
ignored unless the repository deliberately adopts that policy as a maintained source transformation.

## Report results

Report files changed, omitted username blocks, retained sample-management directive counts, global
address findings, and checks not performed. Do not claim that removing current files removes secrets
from existing Git history.
