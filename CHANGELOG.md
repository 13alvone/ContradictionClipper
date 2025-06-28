# Changelog

All notable changes to this project will be documented in this file.

## [0.1.4] - 2025-07-01
### Added
- Parallel download and transcription via `--max_workers` flag.
- Per-worker logging and thread-safe database writes.
### Fixed
- Prevented duplicate entries during concurrent operations.

## [0.1.3] - 2025-06-30
### Added
- Lightweight NLI scoring via Hugging Face models.
- `--nli-model` CLI option to select the model.

## [0.1.2] - 2025-06-29
### Added
- `--transcribe` flag to invoke Whisper transcription.
- New `transcribe_videos` stage populates transcripts table from JSON output.
- Documentation updated with new flag and dependency notes.

## [0.1.1] - 2025-06-28
### Changed
- MoviePy is now imported lazily inside `extract_clip` and `compile_contradiction_montage`.
- Running other pipeline stages no longer requires MoviePy to be installed.

## [0.1.0] - 2025-06-27
### Added
- Initial release of Contradiction Clipper.
- Video download via `yt-dlp` with deduplication by URL and file hash.
- Transcript generation with Whisper.
- Embedding generation and contradiction detection.
- Automated montage compilation using MoviePy.

