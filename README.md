# Aerospace LinkedIn Job Hunter

This bot searches LinkedIn's public job listings for roles matching your configured keywords, filters the results, avoids notifying you about the same listing twice, and sends matching opportunities by email.

The bot is designed to run automatically through GitHub Actions, triggered by an external scheduler such as cron-job.org. It can also be run manually or locally.

## Features

- Search for up to **10 keywords per configured search**.
- Restrict results by location, employer, and exclusion terms.
- Support multiple independent searches and recipient lists.
- Filter listings by posting date and avoid duplicate notifications.
- Send notifications by email or optionally through ntfy.
- Run without LinkedIn credentials by using LinkedIn's public guest job-search endpoint.

## 1. Configure email delivery

For Gmail, create an app password. Your regular Google account password will not work for SMTP.

1. Enable two-step verification on your Google account: <https://myaccount.google.com/signinoptions/two-step-verification>.
2. Create an app password: <https://myaccount.google.com/apppasswords>.
3. Copy the generated 16-character password and store it securely.

For another email provider, use its SMTP server and port instead. For example, Outlook commonly uses `smtp.office365.com` on port `587`.

## 2. Add GitHub Actions secrets

In the repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Purpose | Required |
|---|---|---|
| `SMTP_USERNAME` | Email account used to send notifications | Yes |
| `SMTP_PASSWORD` | SMTP password or Gmail app password | Yes |
| `SMTP_HOST` | SMTP server (defaults to `smtp.gmail.com`) | No |
| `SMTP_PORT` | SMTP port (defaults to `587`) | No |
| `SMTP_FROM` | Optional sender address; otherwise the username is used | No |
| `EMAIL_RECIPIENTS` | Comma-separated notification recipients | Recommended |
| `NTFY_TOPIC` | ntfy topic, only if ntfy notifications are enabled | Only for ntfy |

**Keep email addresses and credentials out of committed files.** If this repository is public, anything written directly in `config.yaml` can be viewed by anyone. Leave each search's `recipients` list empty and store recipient addresses in the `EMAIL_RECIPIENTS` GitHub secret.

For example:

```text
alerts@example.com,another@example.com
```

Never commit SMTP passwords, app passwords, personal access tokens, or other credentials.

## 3. Configure searches

Edit `config.yaml`. The current configuration contains two searches:

- **Airbus Toulouse:** French-language avionics engineering listings in Toulouse, restricted to employers whose company name contains `Airbus`.
- **Singapore civil aviation avionics engineering:** a broader set of civil aviation systems, avionics, flight controls, and technical support roles in Singapore.

The main search fields are:

| Field | Meaning |
|---|---|
| `name` | Display name for the search |
| `keywords` | LinkedIn search terms; maximum 10 per search |
| `location` | Target location |
| `company_include` | Optional company-name allowlist |
| `match_mode` | `any` matches at least one keyword; `all` requires every keyword |
| `exclude` | Terms that disqualify a listing |
| `exclude_locations` | Locations to exclude |
| `remote_only` | Apply LinkedIn's remote-workplace filter |
| `recipients` | Optional addresses for this search only |
| `max_results` | Maximum number of results returned for each LinkedIn query |
| `enabled` | Set to `false` to pause a search |

Keyword matching is currently performed against the **job title**, not the full job description. French equivalents for selected aerospace terms are also checked locally. The employer filter checks the company name returned on the listing; it does not verify a specific Airbus facility or legal entity.

## 4. Run the workflow

Open the repository's **Actions** tab and select **LinkedIn Job Search**.

Choose **Run workflow**. For a safe test, enable `dry_run`. This searches and logs matching listings but does not send notifications or update the seen-job history.

Once the results look correct, run it again with `dry_run` disabled.

The workflow also supports these optional inputs:

- `only_search`: run only the search whose name contains the supplied text.
- `hours`: override the configured posting-age window for this run.
- `max_results`: override the maximum results per query for this run.

## 5. Schedule automatic runs

The GitHub Actions workflow is intentionally configured for manual dispatch and does **not** use GitHub's built-in `schedule` trigger. This repository has used cron-job.org as its external scheduler.

To configure an external scheduler:

1. Create a fine-grained personal access token at <https://github.com/settings/personal-access-tokens/new>.
2. Grant access only to this repository and give it **Actions: Read and write** permission.
3. Store the token securely in the scheduler; do not commit it to the repository.
4. Create a cron-job.org job that sends a `POST` request to:

   ```text
   https://api.github.com/repos/Lordikea/linkedin_job_hunter_aerospace/actions/workflows/job-hunt.yml/dispatches
   ```

5. Use this request body:

   ```json
   {"ref":"main"}
   ```

6. Add these headers:

   ```text
   Accept: application/vnd.github+json
   Authorization: Bearer YOUR_GITHUB_TOKEN
   X-GitHub-Api-Version: 2022-11-28
   Content-Type: application/json
   ```

Set the schedule to the desired interval (the previously configured interval was 15 minutes). A successful GitHub workflow-dispatch request normally returns HTTP `204`.

The workflow uses a concurrency lock to prevent overlapping runs from processing the same job history at the same time.

## 6. Run locally

Install the dependencies:

```bash
pip install -r requirements.txt
```

Set the required environment variables. For example, in a Bash shell:

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=your-address@gmail.com
export SMTP_PASSWORD=your-app-password
export EMAIL_RECIPIENTS=your-address@gmail.com
```

Run a dry test:

```bash
python -m job_hunter --config config.yaml --dry-run
```

Run with email notifications enabled:

```bash
python -m job_hunter --config config.yaml
```

Use `--verbose` (or `-v`) for detailed logs. Use `--hours 48` to widen the posting-age window for a one-off run, or `--only-search Singapore` to run a single configured search.

## 7. Send different searches to different people

A search can have its own `recipients` list. You can also use a dedicated GitHub secret through `recipients_secret`.

For example:

```yaml
searches:
  - name: "My search"
    keywords: ["avionics"]
    location: "Singapore"
    recipients: []

  - name: "A colleague's search"
    keywords: ["flight controls"]
    location: "Toulouse"
    recipients_secret: COLLEAGUE_EMAIL
    enabled: true
```

If you add a `recipients_secret`, add the same secret to the `env` section of `.github/workflows/job-hunt.yml`, for example:

```yaml
COLLEAGUE_EMAIL: ${{ secrets.COLLEAGUE_EMAIL }}
```

A search with its own recipient list sends only to those recipients. A search without its own recipients uses the global `notifications.email.recipients` or `EMAIL_RECIPIENTS` list.

To pause a search without deleting its settings, set `enabled: false`.

## 8. Optional ntfy notifications

ntfy push notifications are available but disabled by default. To enable them:

```yaml
notifications:
  ntfy:
    enabled: true
    topic: "choose-a-long-random-topic-name"
```

If the topic is hosted on the public `ntfy.sh` service, anyone who knows or guesses the topic name may be able to read notifications or publish messages to it. Use a long, unpredictable topic name or host your own ntfy server. Store the topic in the `NTFY_TOPIC` GitHub secret when possible.

## How the bot works and important limitations

- **No official LinkedIn jobs API is used.** The bot reads LinkedIn's public guest job-search pages. LinkedIn may change these pages or temporarily rate-limit requests.
- **Requests are deliberately paced.** The configured delay between requests defaults to three seconds. If LinkedIn returns HTTP 429, the current search is stopped rather than repeatedly sending requests.
- **Results are checked locally.** LinkedIn's own location and date filters may return irrelevant results, so the bot applies additional checks before notifying you.
- **Posting dates may be approximate.** LinkedIn often provides a date without a precise time. The age filter includes a one-day allowance to avoid dropping genuinely recent listings.
- **Keyword matching uses job titles only.** The full description is not fetched. A role whose title does not contain a configured keyword may therefore be missed even if the description mentions relevant skills.
- **Location matching is explicit.** A listing must contain the configured target location. Excluded locations are also checked against the configured exclusion list.
- **Company matching is a name filter.** For searches using `company_include`, the returned company name must contain one of the configured terms.
- **Duplicate notifications are avoided.** Successfully notified listings are stored in `state/seen_jobs.json`. The workflow merges concurrent state updates before saving the file.
- **Failed email delivery does not mark jobs as sent.** The next run can retry those listings.
- **Do not remove the concurrency lock casually.** Overlapping runs could send duplicate notifications or interfere with the shared history file.

## Project structure

```text
job_hunter/
  cli.py                    Command-line entry point
  config.py                 Configuration loading and validation
  freshness.py              Posting-age checks
  linkedin.py               LinkedIn search requests and listing parsing
  matching.py               Keyword and exclusion matching
  storage.py                Previously notified job history
  runner.py                 Search, filtering, and notification workflow
  notifiers/
    email_notifier.py       Email delivery
    ntfy_notifier.py        Optional ntfy push notifications
    render.py               Plain-text and HTML email templates
.github/workflows/
  job-hunt.yml              Main job-search workflow
  email-test.yml            Manual SMTP test workflow
  tests.yml                 Automated test workflow
config.yaml                 Search and notification settings
state/                      Persisted job history
tests/                      Automated tests
```

## Run the tests

Install development dependencies and run the test suite:

```bash
pip install -r requirements-dev.txt
pytest -q
```

