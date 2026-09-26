# PassPhoto requirements

Passport, visa and ID photo requirements used by the PassPhoto iPhone app. Each document records its
official source page and the date its values were last confirmed there.

- `requirements/*.json`: one entry per document (format in [SCHEMA.md](SCHEMA.md)).
- `manifest.json`: what the app downloads first. It holds the data version, the "as of" date, and a
  SHA-256 for each file, so the app only accepts files that match.
- `tools/validate.py`: the checks every entry must pass, and the review report.

## How the requirements stay current

On 1 January, April, July and October, the [quarterly review](.github/workflows/quarterly-review.yml)
re-reads every document's official page:

- **Nothing changed:** the document's "as of" date moves forward and is published automatically.
- **Something changed:** a pull request opens with, for each change, the official link, the exact text
  quoted from that page, the old and new values, and what the change does in the app. Changes without
  a quote are flagged. **Nothing reaches the app until the pull request is merged.**
- **A page couldn't be read:** an issue lists it; that document's date stays at its last successful
  check, so the app keeps showing its true age.

### Reviewing a pull request

For each document in the pull request: open the official link, find the quoted text, and check that
the new value follows from it. Tick the box, then merge. To reject a change, edit it out of the branch
or close the pull request.

The review can also be run by hand from the Actions tab (**Quarterly requirements review → Run
workflow**), optionally for specific ids only.

## Setup

The review uses the Claude Code GitHub Action with a Claude subscription token. Create one with
`claude setup-token` and store it as the `CLAUDE_CODE_OAUTH_TOKEN` repository secret.
