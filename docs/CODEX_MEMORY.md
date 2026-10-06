# Project memory

## Goal and scope
- 文枢 is a local research library with bilingual Markdown reading and an AI-assisted PDF ingestion workflow.
- The public client uses an independently implemented interface; commercial template source and assets are excluded.

## Modules
- `wenshu-pro/`: React client, Tauri desktop shell, optional self-hosted API.
- `skills/paper-ingest/`: source-reviewed PDF ingestion; `skills/pdf-to-wenshu/`: legacy jobs and maintenance.
- `skills/paper-writing/`: attributed scientific writing skill.
- `examples/vault/`: one CC BY 4.0 paper and derivative reading material.

## Decisions
- Code is licensed under AGPL-3.0-only; separately attributed materials retain their licenses.
- Private `vault/`, AI workspaces, environment files, database files and generated mirrors are ignored by Git.
- Runtime API credentials have no build-time default.
- The open source desktop app has its own application identifier and bundles the example library.
- Source and layout checks do not prove semantic accuracy. Formulas, tables and translation require source review.

