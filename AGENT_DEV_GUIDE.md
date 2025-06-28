# AGENT_DEV_GUIDE.md
A concise handbook for any engineer who continues work on **ContradictionClipper** (working name).

──────────────────────────────────────────────────────────────────────────────
1. CORE GOALS
──────────────────────────────────────────────────────────────────────────────
• Robustness  The pipeline must recover gracefully from network drops, corrupt
  files, model failures, or disk-space issues, leaving no half-baked DB rows.

• Efficiency  Minimize redundant work, hold only required objects in memory,
  and parallelize where safe (e.g., downloads, STT, embeddings).

• Dependability Every run is idempotent.  Running the exact same command twice
  should never duplicate rows, re-transcribe a file, or re-compile clips that
  already exist unless explicitly forced.

• Consistency  Follow the existing logging style, CLI ergonomics (argparse with
  positional→required, kw→optional), SQLite persistence, and on-disk layout.

──────────────────────────────────────────────────────────────────────────────
2. ABSOLUTE “NO DUPLICATE” RULES
──────────────────────────────────────────────────────────────────────────────
A. Never download the same *resolved* URL twice  
   • Maintain `videos(url PRIMARY KEY, video_id, dl_timestamp, file_path)`  
   • A UNIQUE constraint on `url` (or canonicalized URL) aborts duplicates.

B. Never transcribe the same *file content* twice  
   • After download and before STT, compute `sha256` of the **binary file**.  
   • Table `files(hash PRIMARY KEY, video_id, path, size_bytes, hash_ts)`  
   • If the hash exists, skip STT; ensure any new URL pointing to identical
     content links to that hash—no second entry, no second transcription.

C. Never embed or detect contradictions twice for the same transcript row  
   • Use `UNIQUE(transcript_id)` in `embeddings` and  
     `UNIQUE(segment_a_id, segment_b_id)` in `contradictions`.

──────────────────────────────────────────────────────────────────────────────
3. PIPELINE CHECKPOINTS (⊕ = must be idempotent)
──────────────────────────────────────────────────────────────────────────────
⊕ download → compute hash  
⊕ transcribe (only if hash unseen) → write JSON + `transcripts` rows  
⊕ embed (only rows whose embeddings don’t exist)  
⊕ detect contradictions (only new pairs)  
⊕ compile montage (deterministic ordering by `confidence DESC, hash ASC`)

Use transactions per major step; commit only when the sub-step finishes.

──────────────────────────────────────────────────────────────────────────────
4. CODING CONTRACT
──────────────────────────────────────────────────────────────────────────────
• argparse  All new flags documented via `--help` and follow UNIX patterns.  
• logging   Use logging with `[i]`, `[!]`, `[x]`, `[DEBUG]` prefixes (already
  established).  
• Error Handling  NEVER swallow exceptions; catch, log, and continue or abort
  cleanly.  
• Tests     Add basic unit tests (pytest) for hash detection, DB uniqueness,
  and duplicate skipping logic.  
• Documentation  Update README & this guide whenever the CLI or DB schema
  changes—single source of truth.

──────────────────────────────────────────────────────────────────────────────
5. FUTURE NICE-TO-HAVES (NOT YET MANDATORY)
──────────────────────────────────────────────────────────────────────────────
• Concurrent download + STT implemented via `--max_workers` flag.
• `--force` flags to override duplicate protections intentionally.  
• GUI wrapper (Flask/Electron) reading the same DB.  
• Pluggable STT and NLI back-ends (GPU Whisper, distilled NLI, etc.).  
• Integration tests in CI (GitHub Actions) using small public domain videos.

──────────────────────────────────────────────────────────────────────────────
6. HAND-OFF CHECKLIST
──────────────────────────────────────────────────────────────────────────────
☑  All schema migrations version-controlled via the `schema_version` table.
☐  Code passes pylint / flake8 with < 5 warnings.  
☐  `README.md` reflects every new CLI flag and environment prerequisite.  
☐  `CHANGELOG.md` updated with date, author, and high-level bullet points.  
☐  Manual test: run pipeline twice on same URL list → second run does **zero**
   work beyond log lines (“already exists — skipping”).

──────────────────────────────────────────────────────────────────────────────
This document is the contract for future contributors. Stick to it, expand it,
but never regress on robustness, efficiency, or idempotency.

