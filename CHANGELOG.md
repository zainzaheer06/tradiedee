# Changelog

All notable changes to NevoxAI Voice Agent Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Pre-call webhook implementation
- New agent architecture improvements

---

## [1.5.0] - 2025-01-XX

### Added
- Pre-call webhook functionality for call preprocessing
- MCP (Model Context Protocol) server agents integration
- Workflow system for complex call handling

### Changed
- Improved agent architecture for better maintainability

---

## [1.4.0] - 2025-01-XX

### Added
- Temperature control from dashboard
- Website call support
- Saudi Arabia timezone support

### Fixed
- SIP status issue resolved
- Agent routes `/agent` endpoint fixes
- View campaign and call log INT/NOT-INT display issues

---

## [1.3.0] - 2024-12-XX

### Added
- Functional tools integration for agents
- MCP file support

### Changed
- Inbound architecture improvements
- Agent.py architecture refactoring
- Organized files and cleaned up project structure
- Prepared for inbound/outbound testing

---

## [1.2.0] - 2024-12-XX

### Added
- Call recording functionality
- RAG (Retrieval-Augmented Generation) support
- Campaign management system
- Inbound call handling
- Web call support
- Sentiment analysis integration

### Changed
- LLM temperature changed from 0.2 to 0.4
- Prompt page updates
- Webhook timing changed from 10s to 20s
- Changed call type from "min" to descriptive type

### Fixed
- Dependency fixes

---

## [1.1.0] - 2024-11-XX

### Added
- Google STT (Speech-to-Text) integration
- ElevenLabs TTS support
- OpenAI integration
- Load balancing for voice services
- Drain out time configuration
- User inactivity detection
- Room deletion management
- Call status tracking
- Greeting functionality

### Changed
- Settings optimized for ElevenLabs and OpenAI
- Dynamic agent configuration

---

## [1.0.0] - 2024-XX-XX

### Added
- Initial release of NevoxAI Voice Agent Server
- Real-time voice conversation support
- LiveKit integration for WebRTC
- Multiple LLM provider support (OpenAI, Gemini)
- Multiple TTS provider support (ElevenLabs, Resemble, OpenAI)
- Multiple STT provider support (OpenAI, Google, Deepgram)
- SIP trunk support for phone calls
- Redis caching for performance
- Prometheus metrics integration
- Grafana dashboard support

---

## How to Update This Changelog

When making changes to the project:

1. **Added** - for new features
2. **Changed** - for changes in existing functionality
3. **Deprecated** - for soon-to-be removed features
4. **Removed** - for now removed features
5. **Fixed** - for any bug fixes
6. **Security** - for vulnerability fixes

### Example Entry

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New feature description

### Fixed
- Bug fix description
```

---

## Version Guidelines

- **MAJOR** version (X.0.0): Incompatible API changes
- **MINOR** version (0.X.0): New functionality (backwards-compatible)
- **PATCH** version (0.0.X): Bug fixes (backwards-compatible)
