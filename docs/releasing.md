# Releasing

This page is for whoever cuts a release, which so far is me. It covers the road to 1.0.0 first, since that release is special (the history gets squashed and the repo goes public), and then the shorter routine for every version after it. 1.0.0 is out, so the parts below marked 1.0.0 only are the record of how that went, and the routine at the end is what applies now.

The one rule that matters most: nothing tags v1.0.0, makes the repo public, or calls a build final until I say go. Until then the candidates are numbered 1.0.0rc1, 1.0.0rc2, and so on (PEP 440 spelling, so pip and the build scripts read them; Windows shows it as 1.0.0.1 in the file's Properties). Every commit that changes the program bumps the number (1.0.0rc2, 1.0.0rc3, and so on), the same rule as the 0.2.x patch bumps, so a build on the Mac or in CI says which commit it is from.

## The checks before any candidate

Every one of these must be green on the commit that becomes a candidate. The everyday suite runs in CI on every push (`.github/workflows/ci.yml`, Windows, macOS, and Linux); the rest are run by hand on the development laptop, from the repo root with the venv active.

- The full suite, output to a file and never a pipe: `QT_QPA_PLATFORM=offscreen pytest -q -p no:cacheprovider -o faulthandler_timeout=90 > suite.log 2>&1`. Any warning is a failure.
- The fuzz tier, which takes minutes: `QT_QPA_PLATFORM=offscreen pytest -q -m fuzz > fuzz.log 2>&1`.
- The scoring oracle and the Multi-Race oracle under `tools/scoring/`, and the mutation run whenever `madtracker/scoring/` changed since the last release. Their README says how to run each and what a clean result looks like. These are hand tools, not suite tests.
- Lint: `ruff check madtracker/ tests/ tools/` and `ruff format --check madtracker/ tests/ tools/`.
- The PDF/A check: veraPDF against the 2b profile on a results sheet, a program sheet, and a Multi-Race Standings sheet exported from the demo data file. Every Inter sheet passed on 2026-Oct-25 (the core-font fallback sheet is plain PDF by design and is expected to fail).
- The mockups: `python -m madtracker --mockup DIR` renders the windows headless; compare them against the previous release's by eye when a layout changed.
- `docs/changelog.md` has an entry for the version, and for 1.0.0 one entry ahead of the version list that sums up the release.

## The scan and the squash (1.0.0 only)

The repo's history before 2026-Oct-08 holds the venue's wordmark, and the public repo must not. The squash removes it, but only what's in the tree survives, so scan the tree first:

- Search every tracked file for real rider names and license numbers (CLAUDE.md: never in code, tests, or docs; the venue's files live in `local/`, which is gitignored), for anything that came from `local/scorer-files/`, and for the venue's name where it would read as the venue's endorsement rather than as the design target.
- Confirm `.gitignore` keeps `local/` and `.claude/` out, and that `git status --ignored` shows nothing surprising inside the tree.
- Squash to one commit on a fresh branch (`git checkout --orphan`), commit, and push it to a private GitHub repo. Keep the full history in a local clone in case something is needed from it; it never goes up. (Done: the full history is kept in a local clone, and the venue's wordmark is in none of the new repo's objects.)

## Release candidates (1.0.0 only)

The candidates are built by GitHub Actions in the private repo, so 1.0.0 is the first version anyone outside sees, and the same workflow later publishes the release.

- The candidate commit says 1.0.0rcN in `madtracker/__init__.py` and `pyproject.toml`. Run `release.yml` by hand (workflow_dispatch); a manual run uploads artifacts only, named with the commit's short hash so two builds of one candidate are told apart. Its Platform choice builds one platform alone, and Skip tests is on by default.
- The macOS job is pinned to `macos-26` with Xcode 26.6 as `DEVELOPER_DIR` (recheck that path in the runner image's README when the image moves). It sets `MADTRACKER_REQUIRE_ICON`, so the build fails rather than fall back when `compile_macos_icon.sh` writes no `Assets.car`, and a check step confirms the icon and uploads `tools/check_macos_icon.sh`'s report as the icon-check artifact. Trial the macOS job alone first; it's the one most likely to need a second try, and macOS minutes count ten times.
- Watch the Actions budget. A full three-platform run is roughly 200 to 300 counted minutes against the free plan's 2,000 a month for a private repo. Leave Skip tests on for the trials (the suite has already passed in CI and locally) and pause `ci.yml` while the repo is private.
- A fix is a new commit at the next candidate number and another manual run.

## Testing a candidate

I download the artifacts and test on my own machines; nothing runs on them remotely. Each package's own `--self-test` already ran inside its build script.

- Windows: install the setup exe over an installed 0.2.x and confirm the data file and its events are untouched; open the program, score a race, export a PDF and the CSV; uninstall and confirm the data folder is only removed when asked. Try the portable zip once too. Read the SmartScreen section of [Installing](installing.md) against what Windows 11 shows today, since the build is unsigned.
- macOS: open the dmg, drag the app in, get through Gatekeeper with Open Anyway as [Installing](installing.md) says, and check the Dock draws the Icon Composer icon. Unplug the TV with the board full screen: one disconnect box, which closes when the board is back.
- Old data files: open a copy of the venue's real 0.2.x file in the candidate and check its events, results, rulesets, and Multi-Race Standings come through. Every released build wrote schema version 4, so the open is a plain open; a file below 4 is refused on purpose.
- The venue night: score a real race night live on the candidate's package, have the scorer approve the results PDF, and get a USAC upload accepted from that build's CSV. This is the acceptance test nothing else can be.

## Tag and release

Only on my explicit go.

- Set the version to 1.0.0 in `madtracker/__init__.py` and `pyproject.toml`, with the changelog's 1.0.0 entry, and rerun `python tools/doc_screenshots.py` so the README's pictures and their footnote are from that build. Then tag `v1.0.0` on that commit and push the tag. Make the repo public (delete the trial Actions runs first if the same repo is going public, since their logs go with it).
- The tag run of `release.yml` rebuilds the same code and attaches the Windows installer and portable zip, the macOS dmg and zip, and the Linux tarball to the GitHub Release.
- The run's checksums job attaches `SHA256SUMS.txt` and adds the sums to the release notes; add the 1.0.0 changelog entry above them. A manual run uploads the same file as an artifact.
- Fallback, if CI can't build a platform: I build the Windows and macOS packages on my machines and hand them over, the Linux tarball comes from `packaging/build_linux.sh`, and the release is made by hand. In that case the tag must not also trigger `release.yml`, or two sets of files race for the same names; switch it to manual dispatch only before tagging.

## After 1.0.0

Versions bump again with every change, as they did before. A later release is the checks above, a changelog entry, a tag, and the tag run; no squash, no private repo, no candidates unless something big changed. The builds stay unsigned until signing is decided (SignPath for Windows is the likely first step), so the SmartScreen and Gatekeeper sections of [Installing](installing.md) stay in.
