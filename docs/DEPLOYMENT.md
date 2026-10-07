# Free hosted setup

The source repository is [sneaxhuh/loop](https://github.com/sneaxhuh/loop). [`render.yaml`](../render.yaml) defines a free Python web service and free Postgres database in Singapore. The local version needs no database; hosted circles, private invitations, reviews, live rankings, and redacted request evidence should use Postgres so they survive web-service restarts.

## Deploy a clean instance

Use [Render's Blueprint creation page](https://dashboard.render.com/select-repo?type=blueprint), select the repository, and review the **free** service and database plans. Supply `QLOO_API_KEY` and `GEMINI_API_KEY` in Render's secret prompts. The Blueprint generates `LOOP_ADMIN_PASSWORD` and binds `LOOP_DATABASE_URL` to the database's internal connection string. Do not commit these values.

The build command is `pip install -r requirements.txt`. The start command is `python -m loop_app --host 0.0.0.0 --port $PORT`. `/healthz` is the health endpoint. `.python-version` selects Python 3.12. The only installed runtime package is the Postgres driver; the agent and Qloo adapters use Python's standard library.

If creating resources separately, select the same workspace and region for both. Set `LOOP_DATABASE_URL` on the web service to the **internal** connection URL from the `loop-data` database's Connections panel. The Render connector used for this build can create the database but does not expose that URL. Use the Dashboard to copy it directly between the two fields; do not paste it into source, browser code, logs, or chat.

## Open the app

Visit the web service URL. Use the generated `LOOP_ADMIN_PASSWORD` from the service's Environment tab to sign in as the organizer. Hosted organizer APIs require that login and a CSRF token. Localhost stays immediately accessible unless you explicitly set an organizer password.

Click **Invite readers**. Send each person their own private `/join#token=...` link. A reader can inspect only their proposed handoffs, own offers, and own references. They can accept, pass, withdraw/restore their own copies, or change their favorites. A pass and offer/profile change trigger deterministic replanning. New proposals clear reviews. Readers can review saved circles even when the organizer opens a different circle.

Private link tokens stay in fragments and bearer request bodies, and are stored separately from public evidence. Anyone holding a link can act as that reader. **Replace private links** revokes the previous links. Organizer-recorded reviews and reviews through reader links are labeled separately; neither method independently verifies identity.

The web service starts only when a public bind has a password of at least sixteen characters. Keep one service instance and one Python process: this prototype has one shared organizer workspace and one active action at a time. Do not configure multiple workers against the same namespace.

## Storage and export

Without `LOOP_DATABASE_URL`, data is written to `local/loop-workspace/` with private file permissions. With it, the app uses a `loop_documents` JSONB table. SQL is parameterized and the database URL is included in credential redaction. `LOOP_DATABASE_NAMESPACE` optionally separates a restored workspace from existing documents.

**Download exchange** exports the current proposal, reviews, inventory, and ranking evidence. **Back up circles** exports all saved circles and captured live evidence, excluding invitation tokens and credentials. These downloads may contain participants' names and personal inventory; keep real-circle exports private.

Restore into a fresh local workspace:

```sh
python3 -m loop_app --workspace local/restored-circle --restore-backup /path/to/loop-workspace-backup.json
```

For a fresh hosted database/namespace, use the same command with `LOOP_DATABASE_URL` configured and the backup made available privately. Restore rejects an existing active workspace and invalid exchange proposals. Reader links are regenerated after restoration.

## Free-tier lifecycle

[Render free web services](https://render.com/docs/free) sleep after fifteen minutes without traffic; the next request can take about a minute to start. The web filesystem is temporary, which is why Postgres holds the hosted workspace. Free Postgres expires after thirty days and has no provider backups. Download a workspace backup before expiration. The database created for this hackathon on October 7 expires **November 6, 2026**, after the October 30 submission target.

The workspace's free compute-hour allowance is shared with other services. No existing unrelated services were changed for this project. Hosting on a free plan does not establish a provider API account's billing entitlement or remaining quota; the app's request budget bounds each server run.

See the official [Blueprint reference](https://render.com/docs/blueprint-spec) and [Python version settings](https://render.com/docs/python-version) for hosting configuration.
