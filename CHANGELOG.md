# Changelog

All notable changes to this project will be documented in this file.

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

