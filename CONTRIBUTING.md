# Contributing to PMAS

Thank you for considering a contribution — PMAS is a small, independent
telepharmacy research project, and careful external contributions are very
welcome.

## How to contribute

1. **Open an issue first** describing the bug or proposal.
2. **Fork the repository** and create a branch named for the issue
   (`fix/issue-12-short-description` or `feat/short-description`).
3. **Keep pull requests small and single-purpose.** One concern per PR is
   far easier to review than a batch.
4. **Verify before you open the PR:**
   - Backend: `ruff check .` and `pytest` from `backend/` (see
     `backend/requirements-dev.txt`; the suite needs no database).
   - Frontend: `node --check` on any file you touched.
   - If your PR changes a page precached by a service worker
     (`patient-app/sw.js` for the demo app, `patient-app/…/sw.js` for the
     platform pages), bump `CACHE_NAME` in the same PR — otherwise returning
     visitors never receive your change.
5. **Reference the issue** in the PR body (`Fixes #NN`) so it auto-closes on
   merge, and describe what you changed, why, and how you verified it.

## Code review expectations

Every PR is verified by execution before merge — the maintainers run the
code, not just read the diff. Expect review comments asking for verification
steps; that is the project's quality bar, not a judgment of your work.

## License for contributions

PMAS itself does not yet adopt an open-source license. **By submitting a
pull request, you agree that your contribution is licensed for use in PMAS**
(including its research outputs) under whatever license the project adopts
in the future. If you need different terms, raise it in the issue before
submitting code.
