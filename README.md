# NEXUS — Local Reliability Platform

A local working model of the NEXUS platform for Engineering Challenge NX-CH-001.

NEXUS is a small reliability platform that accepts background work, persists it, dispatches it to workers, retries failed work with limits, handles duplicate delivery, records events, monitors worker health, and provides an operator dashboard.

## Scope

This implementation focuses on the core reliability requirements:

- Persistent accepted work
- Work delivery and completion
- Retry with bounded attempts
- Dead-letter / failed work visibility
- Idempotent duplicate handling
- Worker crash recovery
- Worker health and restart limits
- Event history for investigation
- Local operator dashboard
- Basic release and rollback workflow
- Deliberate failure simulation

The implementation is intentionally local and deterministic.

## Requirements

- Python 3.11+ recommended
- Windows PowerShell or a Unix-like shell
- No cloud services
- No API keys
- No internet connection is required at runtime

## Start

From the repository root:

### Windows PowerShell

```powershell
.\start.ps1