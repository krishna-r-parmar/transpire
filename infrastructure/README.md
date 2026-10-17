# Infrastructure

Docker and manually approved deployment configuration belongs here. The root `docker-compose.yml` is the local reference stack.

## QA deployment on EC2

The `Deploy QA` workflow targets `/home/ubuntu/transpire` on the configured
instance. GitHub Actions assembles the explicitly mapped repository secrets and defaults
into one `.env`, then writes it to the encrypted Standard Parameter Store parameter `/transpire/qa/env` in `ap-south-1`.
The parameter uses the AWS-managed `alias/aws/ssm` key. SSM starts the command as
root, downloads that exact parameter version with the EC2 instance role, and
atomically replaces `/home/ubuntu/transpire/.env` (owner `ubuntu`, mode `0600`).
Only the parameter name and version appear in the SSM command, never its value.
SSM then switches to `ubuntu`, fetches the
commit that triggered the workflow, and checks it out before running the tracked
`deploy/deploy.sh`. Before checkout, `git reset --hard HEAD` discards any staged
or unstaged edits to tracked server files. No backup or stash is created.
Ignored configuration and untracked files stay in place; a conflicting untracked
file still blocks checkout. A server-only root `deploy.sh` is not used. The
`ubuntu` user must have Git access to the repository and permission to use Docker
Compose.

The root `.env` is the sole production configuration file. Use
`deploy/transpire.env.example` as the combined template. It is passed to the
backend and email worker containers. Only the explicit public `NEXT_PUBLIC_*`
build arguments are passed to the frontend build; the root file is outside both
Docker build contexts. The production stack uses an existing PostgreSQL server;
`DATABASE_URL` must be reachable from inside Docker (`localhost` would refer to
the container itself).

Neither `backend/.env`, `frontend/.env`, nor `deploy/backend.env` is needed in
production. Existing copies are no longer read by this deployment. The root file
is ignored by Git and is not printed by the configuration check.
PostgreSQL must already be configured. Deployment builds the application, runs
migrations, and recreates only the backend, frontend, and email worker containers
with the new images. It finishes after that step. Nginx runs separately and is
not managed by this deployment. Compose explicitly uses project `transpire`.
No orphan removal or image/cache pruning runs.

## One-time setup

1. In **transform-imdcal/transpire → Settings → Secrets and variables → Actions →
   Repository secrets → New repository secret**, add these individually (enter
   raw values, without wrapping quotes):

   | Secret | Value |
   | --- | --- |
   | `APP_DOMAIN` | Public hostname, e.g. `transpire-qa.imdcal.com`, without `https://` or a path |
   | `DATABASE_URL` | Existing PostgreSQL connection URL reachable inside Docker; URL-encode special characters in credentials |
   | `OUTBOX_ENCRYPTION_KEY` | Existing encryption key; changing it makes queued email payloads unreadable |

   Keep the existing `APP_DIR`, `AWS_REGION`, `AWS_ROLE_ARN`, and `EC2_INSTANCE_ID`
   secrets. The workflow now uses them, with the previous values as defaults.
   `APP_DOMAIN` supplies the public URLs, allowed hosts, CORS origin, and default
   sender address. No combined `TRANSPIRE_ENV` secret is needed.
2. Optional settings can each be added under the same name shown in
   `deploy/transpire.env.example`. The workflow uses the template's defaults for
   omitted values and quotes/escapes supplied values automatically. For real
   email delivery, set `EMAIL_BACKEND=smtp`, `EMAIL_FROM_ADDRESS`, `SMTP_HOST`,
   and the provider's port/TLS settings. `SMTP_USERNAME` and `SMTP_PASSWORD` are
   optional and should be omitted for an IP-authorized relay. Without email
   overrides, email uses the console backend. `ENTRA_CLIENT_ID`
   and `ENTRA_CLIENT_SECRET` configure optional Microsoft SSO. Only named app
   settings are assembled; AWS settings and unrelated repository secrets are
   excluded from the `.env`.
3. In AWS IAM, open role `Actions-deploy-transpire`. Add the inline policy in
   `infrastructure/github-actions-env-policy.json`, named `TranspireWriteEnv`.
   Keep its existing deployment permissions and OIDC trust policy.
4. In EC2, select instance `i-0edc0d79289958bca`, follow its **IAM role** link, and
   add `infrastructure/ec2-env-policy.json` as inline policy `TranspireReadEnv`.
   This is the instance's role, not the GitHub Actions role. The default AWS-managed
   SSM key supports this setup without a custom KMS key policy.
5. Verify AWS CLI is installed for root on EC2 (`sudo -H sh -c 'command -v aws'`).
   Install AWS CLI v2 if missing. Verify `ubuntu` can use Git and Docker Compose.
6. Merge these workflow changes into the organization's `main` after setup.
   The push triggers **Deploy QA**. For later secret changes, update the relevant repository secret
   and select **Actions → Deploy QA → Run workflow → main**; rerunning an old
   workflow run can reuse its old deployment code.

The workflow creates the encrypted parameter automatically. GitHub remains the
configuration source; each deployment publishes a new parameter version and
installs that version on EC2 before running migrations and restarting services.
The workflow never embeds secret contents in SSM commands or prints the `.env`.

## IMDCAL email relay

Add the following individual repository secrets for the admin-provided relay:

| Secret | Value |
| --- | --- |
| `EMAIL_BACKEND` | `smtp` |
| `EMAIL_FROM_ADDRESS` | `transpire.app@imdcal.com` |
| `EMAIL_FROM_NAME` | `TRANSPIRE` |
| `SMTP_HOST` | `imdcal-com.mail.protection.outlook.com` |
| `SMTP_PORT` | `25` |
| `SMTP_START_TLS` | `true` |
| `SMTP_USE_TLS` | `false` |

Do not add `SMTP_USERNAME` or `SMTP_PASSWORD`; remove them if credentials were
previously configured. The app already supports sending without SMTP login.
STARTTLS upgrades the port 25 connection to TLS; `SMTP_USE_TLS` means implicit
TLS and remains false for this setup.

The hostname and port alone do not confirm the Microsoft 365 connector setup.
Have the mail admin confirm the supported route from this EC2 host and, for an
IP-authorized connector, the server's static public egress IP (possibly a NAT
gateway IP). The same MX endpoint can also be used for Direct Send, which only
delivers within the organization. Microsoft documents restrictions for relay
from third-party hosted services; the admin must confirm the approved route
for this AWS deployment before relying on external recipient delivery.

Outbound TCP port 25 must be reachable from EC2. AWS restricts port 25 by default;
an AWS restriction removal may be needed in addition to firewall/security group
egress rules. These are infrastructure prerequisites, not app credentials.

To deploy the current server checkout manually:

```bash
cd /home/ubuntu/transpire
bash deploy/deploy.sh
```
