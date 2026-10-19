Cut a release candidate or stable release.

Usage:
- `/release rc` — tag the current `develop` HEAD as the next RC (e.g. `0.13.0-rc2`)
- `/release stable` — merge `develop` into `main` and tag the final release

## RC release (`/release rc`)

1. Confirm the current branch is `develop` and is up to date with `origin/develop`.
2. Read CHANGELOG.md to find the version being prepared (the top-most `## X.Y.Z` entry).
3. List existing tags to determine the next RC number (e.g. if `0.13.0-rc1` exists, use `rc2`).
4. Run `poetry run pytest tests` and check that CI on `develop` HEAD is green (`gh run list --branch develop --limit 3`) — do not tag if either fails.
5. Tag `develop` HEAD as `<version>-rc<N>` and push the tag.
6. Create the GitHub pre-release with generated notes:
   `gh release create <tag> --verify-tag --prerelease --title <tag> --generate-notes --notes-start-tag <prev-tag>`
7. Report the tag name, the release URL and the `git log --oneline <prev-tag>..HEAD` summary. Mention that the "build dev images" run was started by the tag.

## Stable release (`/release stable`)

1. Confirm CHANGELOG.md has a section for the version being released.
2. Open a PR from `develop` → `main` titled `chore: release <version>`.
3. After the user confirms the PR is merged, tag `main` HEAD as `<version>` and push.
4. Create the GitHub release with generated notes, starting from the previous stable tag (not an RC) so the notes cover the whole release:
   `gh release create <version> --verify-tag --latest --title <version> --generate-notes --notes-start-tag <prev-stable-tag>`
5. Report the tag and the GitHub release URL.

**RC tags always go on `develop`. Stable tags always go on `main`.**
