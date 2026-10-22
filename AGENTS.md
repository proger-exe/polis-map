# Repository Guidelines

## Project Structure & Module Organization

This repository uses `docs/TECHTASK.md` as the product contract. Keep implementation organized around the planned political roleplay system:

- `backend/` for API, domain logic, persistence, map generation, and moderation.
- `frontend/` for the interactive world map, player views, admin tools, and mapper panel.
- `bot/` for Telegram account linking, notifications, and action confirmations.
- `assets/maps/` for base map images and generated map exports.
- `tests/` or package-local test folders for backend, frontend, and bot coverage.
- `docs/` for architecture notes, API examples, and setup.

Store map coordinates normalized as `{ "x": 0.421, "y": 0.683 }`, not raw pixels.

## Build, Test, and Development Commands

No build system is committed yet. Add commands with the first scaffold. Prefer simple repo-root entry points:

- `make dev` or `npm run dev` to start local API, web UI, and bot workers.
- `make test` or package-native test commands to run the full suite.
- `make lint` to run formatters, linters, and type checks.
- `make migrate` for database schema migrations once persistence exists.

Use the selected package manager/runtime; do not swap stacks without approval.

## Coding Style & Naming Conventions

Keep domain names explicit: `state`, `territory`, `capital`, `colony`, `claim`, `conflict`, `political_event`. Use normalized coordinate helpers for all map objects. Keep mapper editing logic separate from moderation approval logic and Telegram confirmation flows.

Prefer small modules with clear ownership: API handlers should validate and delegate; services should own game rules; persistence code should not render maps.

## Testing Guidelines

Add regression tests for territory edits, coordinate normalization, role permissions, moderation approvals, and Telegram confirmation state. Name tests by behavior, for example `test_colonization_request_requires_leader` or `territoryPolygon.canMoveVertex`.

Include fixture maps or tiny synthetic polygons when testing geometry. Avoid tests that depend on a large production image.

## Commit & Pull Request Guidelines

This checkout is not a git repository, so no local history is available. Use Conventional Commits once git is initialized, for example `feat: add mapper polygon editor` or `test: cover claim approval flow`.

Pull requests should describe gameplay impact, data migrations, test results, and screenshots for map/admin UI changes. Link related tasks and call out Telegram bot or database configuration changes.

## Security & Configuration

Never commit bot tokens, admin credentials, or database URLs. Use `.env.example` for required keys and keep real secrets in the deployment secret store.
