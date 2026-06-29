# Gameplay Log Manifest

This folder is the allowlist boundary for gameplay logs.

Current commands:

```powershell
python scripts\validate_gameplay_logs.py --output data_manifest\gameplay_logs.json
python scripts\filter_current_gameplay_logs.py --manifest data_manifest\gameplay_logs.json --output data_manifest\current_gameplay_logs.txt
```

Rules:

- Current logs must be parseable replay JSON files with a `steps` list and at
  least one structured decision.
- Current logs must be on or after the configured minimum date, currently
  `2026-06-27`.
- Duplicate replay hashes are quarantined.
- Corrupt, incomplete, old, or schema-incompatible logs are not allowed into
  training, validation, or replay analysis.
- If a log is uncertain, move it under `logs/quarantine/` instead of deleting
  it.

`gameplay_logs.json` is the machine-readable audit. `current_gameplay_logs.txt`
is the current allowlist that downstream scripts should consume.

`scripts/filter_current_gameplay_logs.py` also writes allowlist integrity
metadata back into the manifest: generated timestamp, file count, file size,
and SHA256. `train.py` refuses to run if those checks disagree with the current
allowlist.
