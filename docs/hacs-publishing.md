# Publishing and maintaining HACS releases

Users can install this public repository as a HACS **custom repository** now.
Default catalog inclusion is a separate process reviewed by the HACS team;
publishing a GitHub release does not automatically add it to that catalog.

## Repository settings

Use the gear beside **About** on
https://github.com/danwoodsy/autel-maxicharger-ha to set:

- Description: `Local HTTPS control and sensors for Autel MaxiCharger in Home Assistant.`
- Topics: `home-assistant`, `hacs`, `autel`, `ev-charger`.

Keep the repository public and GitHub Issues enabled. The integration already
has a README, MIT license, `hacs.json`, manifest, and bundled `brand/icon.png`.
Bundled brand images satisfy the current HACS requirement; a separate submission
to the Home Assistant brands repository is unnecessary.

## Validation

The **Validate** workflow runs tests/lint, the official HACS action, and the
official Hassfest action on main pushes, pull requests, weekly, and on demand.
No HACS checks are ignored.

Open https://github.com/danwoodsy/autel-maxicharger-ha/actions/workflows/validate.yml
and verify all three jobs pass. If the HACS check ran before topics were added,
use **Re-run failed jobs** after adding them.

## First release

1. Make sure the Validate workflow passes on the intended main commit.
2. Open https://github.com/danwoodsy/autel-maxicharger-ha/actions/workflows/release.yml.
3. Select **Run workflow**, leave the branch set to **main**, and run it.
4. The workflow runs all three checks again, checks that release notes match
   the manifest version, builds the ZIP, and publishes **v0.1.6** only after
   validation succeeds. It also creates the tag at that exact commit.

The repository's normal GitHub Actions token supplies the required access;
there is no additional release secret to configure. If an organization policy
blocks write permissions, the owner must enable the workflow's requested
`contents: write` permission before publishing.

Release notes are prepared in [releases/v0.1.6.md](releases/v0.1.6.md).
The ZIP uses the manual-install `/config/custom_components/autel_http` layout.
HACS installs the integration from the release's repository tag; `zip_release`
is not enabled, so the manual ZIP layout does not affect HACS installation.

After publishing, verify
https://github.com/danwoodsy/autel-maxicharger-ha/releases/tag/v0.1.6
shows a full release with the ZIP attached. Check HACS custom-repository
downloads offer that version. A Git tag alone is insufficient.

## Default catalog submission

Read the current requirements:

- https://www.hacs.xyz/docs/publish/start/
- https://www.hacs.xyz/docs/publish/include/

Once the checks and release exist:

1. As the owner, fork https://github.com/hacs/default to your personal account.
2. Create a branch from its current `master`, for example
   `add-autel-maxicharger-ha`. Leave **Allow edits by maintainers** enabled.
3. In the root `integration` JSON list, add
   `"danwoodsy/autel-maxicharger-ha"` in alphabetical order.
4. Open a pull request back to `hacs/default:master`, titled
   `Add Autel MaxiCharger over HTTPS`.
5. Fill out its checklist truthfully and provide the links below. Do not submit
   until every required check has passed and the release is published.

Use this body after substituting links to the successful workflow runs:

```markdown
## Checklist

- [x] I've read the publishing documentation.
- [x] I've added the HACS action to my repository.
- [x] I've added the hassfest action to my repository.
- [x] The actions are passing without any disabled checks in my repository.
- [x] I've added links to the action runs below.
- [x] I've created a new release after the validation actions ran successfully.

## Links

Link to current release: https://github.com/danwoodsy/autel-maxicharger-ha/releases/tag/v0.1.6
Link to successful HACS action (without the ignore key): <paste successful run URL>
Link to successful hassfest action: <paste successful run URL>
```

Both checks can link to the same successful Validate or Release workflow run
when it contains their successful jobs. HACS reviews new submissions; its docs
warn that inclusion can take months. Custom-repository installation remains
available during review.

## Future versions

1. Bump `custom_components/autel_http/manifest.json`, such as `0.1.6` → `0.1.7`.
2. Add a matching changelog entry and `docs/releases/v0.1.7.md`.
3. Commit and push, wait for Validate to pass, then run Release from main.

Alternatively, pushing a matching `v0.1.7` tag starts the same gated release
workflow. Version mismatches and missing release notes stop publication.
Do not change already-published tags or releases. HACS uses published releases
to present available versions; the README explains compatibility, while the
manifest is the authoritative installed version.
