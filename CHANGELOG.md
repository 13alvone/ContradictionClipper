# Changelog

All notable changes to this project will be documented in this file.

## [0.1.11] - 06-27-2025
### Added
- `--whisper-bin` CLI option to specify the path to the Whisper binary.

## [0.1.12] - 06-27-2025
### Fixed
- Handled `sqlite3.IntegrityError` when recording files to avoid crashes and
  cleanup temporary duplicates.

## [0.1.10] - 06-27-2025
### Changed
- NLI models are now cached in memory by `load_nli_model` to avoid repeated
  loading on subsequent runs.

## [0.1.9] - 06-27-2025
### Changed
- Enabled SQLite WAL mode before threaded writes in `process_videos` and `transcribe_videos` to reduce lock contention.

## [0.1.7] - 06-27-2025
### Added
- Database schema versioning via `schema_version` table and migration helpers.

## [0.1.8] - 06-27-2025
### Changed
- Schema bumped to v2 introducing a `files` table keyed by SHA256 hashes.
- `videos` now reference `files` instead of storing paths and hashes directly.

## [0.1.6] - 06-27-2025
### Added
- Text summary generation via `summarize_contradictions`.
- `--summary` CLI flag to write contradiction summaries to a file.

## [0.1.5] - 06-27-2025
### Added
- Flask dashboard for browsing videos, transcripts, and contradictions.
- `--dashboard` CLI option to launch the web interface.

## [0.1.4] - 06-27-2025
### Added
- Parallel download and transcription via `--max_workers` flag.
- Per-worker logging and thread-safe database writes.
### Fixed
- Prevented duplicate entries during concurrent operations.

## [0.1.3] - 06-27-2025
### Added
- Lightweight NLI scoring via Hugging Face models.
- `--nli-model` CLI option to select the model.

## [0.1.2] - 06-27-2025
### Added
- `--transcribe` flag to invoke Whisper transcription.
- New `transcribe_videos` stage populates transcripts table from JSON output.
- Documentation updated with new flag and dependency notes.

## [0.1.1] - 06-27-2025
### Changed
- MoviePy is now imported lazily inside `extract_clip` and `compile_contradiction_montage`.
- Running other pipeline stages no longer requires MoviePy to be installed.

## [0.1.0] - 06-27-2025
### Added
- Initial release of Contradiction Clipper.
- Video download via `yt-dlp` with deduplication by URL and file hash.
- Transcript generation with Whisper.
- Embedding generation and contradiction detection.
- Automated montage compilation using MoviePy.

