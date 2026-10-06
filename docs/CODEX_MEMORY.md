# Project memory

## Goal and scope
- 文枢 is a local research library with bilingual Markdown reading and an AI-assisted PDF ingestion workflow.
- The public client uses an independently implemented interface; commercial template source and assets are excluded.
- The open source app is a literature workspace for users' own papers. The included paper is an ordinary library entry, not a separate demonstration workflow.

## Modules
- `app/`: React client, Tauri desktop shell, optional self-hosted API.
- `skills/paper-ingest/`: the single supported source-reviewed PDF import workflow.
- `skills/paper-writing/`: attributed scientific writing skill.
- `examples/vault/`: one CC BY 4.0 paper and derivative reading material.

## Decisions
- Code is licensed under AGPL-3.0-only; separately attributed materials retain their licenses.
- Private `vault/`, AI workspaces, environment files, database files and generated mirrors are ignored by Git.
- Runtime API credentials have no build-time default.
- The open source desktop app has its own application identifier and bundles the example library.
- Source and layout checks do not prove semantic accuracy. Formulas, tables and translation require source review.
- GitHub Pages uses `pages` mode, `/wenshu/` assets and HashRouter; local Web and Tauri retain root-path operation.
- Hosting mode only changes asset roots and routing. Product screens and client capabilities are shared; AI and synchronization depend on the user's runtime configuration.
- GitHub Pages hosts static source data, not a PDF-processing or synchronization server. PDF import runs locally; personal annotations remain local unless the user configures synchronization.
- EasyRead (`Edwardxlai/easyread`) informed reading and onboarding; its source is only kept in the ignored reference workspace.

