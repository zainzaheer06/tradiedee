# Configuration Files

This directory contains all configuration files for external services.

## Structure

### 📁 livekit/
LiveKit SIP trunk and routing configurations:
- `exacall-trunk.json` - ExaCall SIP trunk config
- `exacall-trunk-fixed.json` - Fixed trunk configuration
- `exacall-trunk-udp.json` - UDP trunk configuration
- `inbound-rule.json` - Inbound call routing rules

### 📁 google/
Google Cloud service credentials:
- `aimeetingassistant-448613-1ff1fc705734.json` - Google Cloud service account key
  - **IMPORTANT:** Never commit this file to version control
  - Add to `.gitignore` if not already included

## Usage

These configuration files are referenced by:
- **LiveKit configs**: Used by LiveKit Cloud for SIP trunk setup
- **Google credentials**: Used by `agent.py` and `agent-inbound.py` for Speech-to-Text

## Security Notes

⚠️ **IMPORTANT:**
- Never share Google credentials publicly
- Rotate keys regularly
- Use environment variables for sensitive data when possible
- Ensure `.gitignore` includes `config/google/*.json`
