# Vela source upload status (phase 12)

**Status: INCOMPLETE — development preview, not for production.**

- Target repository: `smgsp6/3x-ui`; development branch: `vela-dev`; `main` remains unchanged.
- Reviewed upstream base commit: `5297fd3c8495d80fab97ae511553fa545c69e913`.
- Full 79-file development-preview ZIP: `vela-phase12-dev-preview.zip`, SHA-256 `3d0c33a8c7d046a4f00527687eec64efe179f8a3ede957de05d0ea57395de0fd`.
- The **ZIP itself and the Vela source changes have NOT yet been committed to this branch**. The files currently under `vela-development/` are durable project documentation and checksums ONLY.
- The release has not passed complete Go/React/Docker builds, Telegram device tests, real ACME renewal, or production deployment.
- To complete source import: first review the development ZIP for private information; check out this exact branch (or a new feature branch based on the audited base) and apply the reviewed `apply_to_repo.py` against a clean checkout, then run project builds, audits and review before committing. Do not commit the development ZIP, local secrets, runtime databases or backups indiscriminately.
- Keep original 3x-ui Git origin and Go module; preserve upstream license and attribution.

This status is deliberately explicit so future contributors do not mistake documentation-only uploads for source publication.
