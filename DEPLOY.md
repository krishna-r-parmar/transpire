# Deploying TRANSPIRE to AWS EC2 with Docker

This guide runs the frontend, backend and email worker as Docker containers on one EC2 instance, deployed by **GitHub Actions**. Two things are **not** containerised:

- **Nginx** is installed on the host and handles TLS and reverse proxying (configured manually; a reference config is provided).
- **PostgreSQL** runs as a standalone service, either natively on the same EC2 host (the default below) or on a separate server.

```
Internet ──▶ :443 Nginx on host (TLS)
               ├── /api/*, /health/*  ──▶ 127.0.0.1:8000  backend container  (FastAPI, 2 workers)
               └── everything else    ──▶ 127.0.0.1:3000  frontend container (Next.js)
             backend, email-worker   ──▶ PostgreSQL (outside Docker)
```

The containers publish ports only on `127.0.0.1`, so they can be reached only through Nginx on the same host.

### How a release flows

```
push to main ──▶ CI workflow (lint, typecheck, tests, build)
                   │ success
                   ▼
                 Deploy workflow
                   ├─ assume IAM role via GitHub OIDC              (no AWS keys stored in GitHub)
                   ├─ EC2 Instance Connect: push a 60-second SSH key (no SSH key stored in GitHub)
                   ├─ SSH tunnelled through SSM Session Manager     (no inbound port 22 needed)
                   ├─ build backend + frontend images on the runner, tagged with the commit SHA
                   │    (skipped if the server already has that SHA, e.g. a rollback)
                   ├─ stream images to EC2:  docker save | gzip | ssh … docker load
                   ├─ push the deploy/ files from that commit to /opt/transpire/deploy
                   ├─ write deploy/backend.env on EC2 from the GitHub environment secrets/variables
                   ├─ run deploy/deploy.sh <sha> on EC2
                   │    ├─ alembic upgrade head
                   │    ├─ docker compose up -d
                   │    ├─ wait for health checks (restore previous version on failure)
                   │    └─ keep the last 5 releases' images for rollback
                   └─ smoke test https://<APP_DOMAIN>/health/ready
```

There is no container registry and no git checkout on the server. The server never builds images: it only loads what the workflow sends. Rollback is a manual run of the Deploy workflow with an earlier commit SHA.

The frontend and API share one origin (`https://<APP_DOMAIN>`). This is required: the browser reads the CSRF cookie set by the API, which only works when both are on the same host.

Production files live in [`deploy/`](deploy):

| File | Purpose |
| --- | --- |
| `.github/workflows/deploy.yml` | Builds images, pushes them and the deploy files to EC2, rolls out, smoke-tests |
| `.github/scripts/ec2-ssh-open.sh` | Opens the SSH-over-SSM connection with an Instance Connect key |
| `.github/scripts/render-backend-env.sh` | Builds `deploy/backend.env` from GitHub secrets/variables, with defaults and validation |
| `deploy/deploy.sh` | Server-side rollout: migrate, restart, health check, auto-restore, prune |
| `deploy/docker-compose.prod.yml` | Production stack (locally loaded images; no database or proxy service; ports bound to loopback) |
| `deploy/nginx/transpire.conf` | Reference Nginx site (routing, headers, TLS, body size) |
| `deploy/compose.env.example` | Template for `deploy/.env` (current and previous release; maintained by `deploy.sh`) |

The steps assume **Ubuntu 24.04** on the EC2 host and an install path of `/opt/transpire`. Commands prefixed with `sudo` run on the server.

---

## 0. Before you start

Have these ready:

- [ ] An AWS account with permission to manage EC2, security groups, Elastic IPs, IAM and Systems Manager
- [ ] Admin access to the GitHub repository (to create an environment and variables)
- [ ] A domain or subdomain you control, e.g. `transpire.your-company.com`
- [ ] A TLS certificate for it: either a company-issued certificate (full chain + private key) or a plan to use Let's Encrypt via certbot
- [ ] The PostgreSQL superuser login on the server (or a DBA who can create a database and role)
- [ ] SMTP credentials (optional at first; email stays in `console` mode until set)
- [ ] Microsoft Entra app registration details (optional; only if using SSO)

---

## 1. AWS: instance, network and DNS

Skip any sub-step that is already done for your existing server.

### 1.1 Security group

1. Open **EC2 → Security Groups → Create security group**.
2. Name it `transpire-web`.
3. Add these inbound rules:

   | Type | Port | Source | Why |
   | --- | --- | --- | --- |
   | SSH | 22 | **My IP** (not `0.0.0.0/0`), or omit entirely | Optional admin access. Deploys don't use it, and admins can use **Session Manager** instead |
   | HTTP | 80 | `0.0.0.0/0`, `::/0` | Redirect to HTTPS (and Let's Encrypt validation, if used) |
   | HTTPS | 443 | `0.0.0.0/0`, `::/0` | The app |

4. Do **not** add 3000, 8000 or 5432. If PostgreSQL is on a separate server, open 5432 on *that* server's security group, with this instance's security group as the source.
5. Leave outbound as "All traffic".

### 1.2 Instance

1. **EC2 → Launch instance**.
2. AMI: **Ubuntu Server 24.04 LTS (x86_64)**.
3. Instance type: **t3.large** (2 vCPU, 8 GB) if PostgreSQL shares the host. Use **t3.medium** (4 GB) if the database is on another server. Images are built on GitHub's runners, so the server needs no build headroom.
4. Key pair: choose or create one and keep the `.pem` file safe.
5. Network: attach the `transpire-web` security group.
6. Storage: **40 GB gp3** (Docker images and PostgreSQL data).
7. Under **Advanced details → IAM instance profile**, choose `transpire-ec2` (create it first in step 6.2, or attach it later with **Actions → Security → Modify IAM role**).
8. Launch.

### 1.3 Elastic IP

1. **EC2 → Elastic IPs → Allocate Elastic IP address → Allocate**.
2. Select it → **Actions → Associate** → pick the instance → **Associate**.
3. Note the IP. It is called `<ELASTIC_IP>` below.

### 1.4 DNS

1. In your DNS provider, create an **A record**: `transpire.your-company.com → <ELASTIC_IP>`.
2. Use a short TTL (300 s) while setting up.
3. Confirm it resolves from your laptop:

   ```bash
   dig +short transpire.your-company.com
   ```

   It must print `<ELASTIC_IP>` before you request a Let's Encrypt certificate in step 9.3.

---

## 2. Prepare the server

### 2.1 Connect

```bash
chmod 400 ~/Downloads/transpire.pem
```

```bash
ssh -i ~/Downloads/transpire.pem ubuntu@<ELASTIC_IP>
```

### 2.2 Update the OS

```bash
sudo apt update && sudo apt -y upgrade
```

```bash
sudo timedatectl set-timezone Asia/Kolkata
```

Reboot if the upgrade asks for it (`sudo reboot`), then reconnect.

### 2.3 Add swap (headroom for PostgreSQL and containers)

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
```

```bash
sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Check with `free -h`: the Swap row should show 4.0Gi.

### 2.4 Install Docker Engine and the Compose plugin

```bash
sudo apt -y install ca-certificates curl git
```

```bash
sudo install -m 0755 -d /etc/apt/keyrings && sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
```

```bash
sudo apt update && sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

```bash
sudo systemctl enable --now docker
```

```bash
sudo usermod -aG docker ubuntu
```

Log out (`exit`) and SSH back in so the group change applies. Then verify:

```bash
docker run --rm hello-world
```

```bash
docker compose version
```

### 2.5 Check the SSM agent and EC2 Instance Connect

GitHub Actions reaches the server through the SSM agent and authenticates with EC2 Instance Connect. Both are preinstalled on Ubuntu AMIs; confirm:

```bash
sudo snap services amazon-ssm-agent
```

The agent must show `active`. If it does not, run `sudo snap start --enable amazon-ssm-agent`.

```bash
dpkg -s ec2-instance-connect | grep Status
```

It must print `Status: install ok installed`. If it does not, install it:

```bash
sudo apt -y install ec2-instance-connect
```

---

## 3. Prepare PostgreSQL

Pick **3A** if PostgreSQL runs on this EC2 host, or **3B** if it runs on another server.

### 3.1 Create the database and application role (both cases)

Generate a strong URL-safe password and keep it for step 5:

```bash
openssl rand -base64 32 | tr -d '/+=' | cut -c1-32
```

Open `psql` as the superuser (on the database server):

```bash
sudo -u postgres psql
```

Run, replacing `<db-password>`:

```sql
CREATE ROLE transpire LOGIN PASSWORD '<db-password>';
CREATE DATABASE transpire OWNER transpire;
\c transpire
ALTER SCHEMA public OWNER TO transpire;
\q
```

The `transpire` role must **not** be a superuser or have `BYPASSRLS`, otherwise tenant row-level security is silently skipped. Confirm:

```bash
sudo -u postgres psql -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname='transpire';"
```

Both flags must be `f`.

### 3A. PostgreSQL on the same EC2 host

Containers reach the host at `host.docker.internal`, and their traffic comes from the fixed Docker subnet `172.30.0.0/24`.

1. Find the config files:

   ```bash
   sudo -u postgres psql -tc "SHOW config_file;"
   ```

   ```bash
   sudo -u postgres psql -tc "SHOW hba_file;"
   ```

2. Edit `postgresql.conf` (path from the first command) and set:

   ```
   listen_addresses = '*'
   ```

   Port 5432 stays closed to the internet because the security group does not allow it.

3. Append this line to `pg_hba.conf` (path from the second command):

   ```
   host    transpire    transpire    172.30.0.0/24    scram-sha-256
   ```

4. Restart PostgreSQL:

   ```bash
   sudo systemctl restart postgresql
   ```

5. If the host firewall `ufw` is active (`sudo ufw status`), allow the Docker subnet:

   ```bash
   sudo ufw allow from 172.30.0.0/24 to any port 5432 proto tcp
   ```

6. The `DATABASE_URL` host in step 5 is `host.docker.internal`.

### 3B. PostgreSQL on a separate server

1. On the database server, set `listen_addresses` to include its private IP (or `'*'`).
2. In its `pg_hba.conf`, allow this EC2 instance's **private** IP:

   ```
   host    transpire    transpire    <EC2_PRIVATE_IP>/32    scram-sha-256
   ```

3. Restart PostgreSQL and open 5432 in the database server's security group with source `transpire-web`.
4. The `DATABASE_URL` host in step 5 is the database server's private IP or DNS name.

---

## 4. Prepare the app directory

The workflow pushes the `deploy/` folder to `/opt/transpire/deploy` and writes `deploy/backend.env` from GitHub on every release. Nothing in this directory needs editing by hand.

```bash
sudo mkdir -p /opt/transpire/deploy && sudo chown -R ubuntu:ubuntu /opt/transpire
```

Add a shortcut for the production Compose command. Later manual steps use `dc`:

```bash
echo "alias dc='docker compose --project-directory /opt/transpire/deploy -f /opt/transpire/deploy/docker-compose.prod.yml'" >> ~/.bashrc && source ~/.bashrc
```

---

## 5. Application settings (GitHub secrets)

### 5.1 How settings reach the server

All backend settings live in the GitHub **`production` environment** (created in step 6.4). On every deploy, the workflow:

1. reads each setting from the environment's **secrets**, falling back to its **variables** (a secret wins if both exist),
2. fills in defaults for anything optional that is unset, and derives the URL settings from `APP_DOMAIN`,
3. checks that required values are present and contain no single quotes or line breaks,
4. writes `/opt/transpire/deploy/backend.env` on the server (mode `600`), replacing the previous file,
5. restarts the containers. Compose recreates them whenever the file's contents change.

So **never edit `backend.env` on the server**: the next deploy overwrites it. To change a setting, update it in GitHub and run the Deploy workflow (step 13.4).

You can store every setting as a secret. Putting the non-sensitive ones in **variables** instead is optional, but it lets you see their current values in GitHub; secrets are write-only.

### 5.2 Generate the values you need

1. **`DATABASE_URL`**: use the password created in step 3.1. Build the value as:

   ```
   postgresql+asyncpg://transpire:<db-password>@host.docker.internal:5432/transpire
   ```

   Use `host.docker.internal` when PostgreSQL is on this EC2 host (3A), or the database server's private IP or DNS name (3B).

2. **`OUTBOX_ENCRYPTION_KEY`**: generate a Fernet key on your laptop and copy the output:

   ```bash
   python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```

   **Save this key in your password manager as well.** GitHub secrets can't be read back, and if the key is lost, emails still queued can't be decrypted. Never change it while emails are queued.

3. Keep the database password in your password manager too, for the same reason.

### 5.3 Settings reference

Add these in **repository → Settings → Environments → production**. **Secret** means use *Environment secrets*. **Secret or variable** means either works.

**Required**

| Name | Store as | Guide value | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | Secret | `postgresql+asyncpg://transpire:<db-password>@host.docker.internal:5432/transpire` | Step 5.2. Use only URL-safe password characters. |
| `OUTBOX_ENCRYPTION_KEY` | Secret | 44-character key ending in `=`, e.g. `q3J…Xw8=` | Step 5.2. Back it up. |
| `EMAIL_FROM_ADDRESS` | Secret or variable | `no-reply@your-company.com` | Sender for all emails. Must be allowed by your SMTP provider. |
| `APP_DOMAIN` | **Variable** (deployment, step 6.4) | `transpire.your-company.com` | Shared with the frontend build. No `https://`, no trailing slash. |

**Email** (leave `EMAIL_BACKEND` unset until step 11; emails are then only logged)

| Name | Store as | Guide value | Default if unset |
| --- | --- | --- | --- |
| `EMAIL_BACKEND` | Secret or variable | `smtp` (or `console` to only log) | `console` |
| `EMAIL_FROM_NAME` | Secret or variable | `TRANSPIRE` | `TRANSPIRE` |
| `SMTP_HOST` | Secret or variable | `email-smtp.ap-south-1.amazonaws.com` or `smtp.office365.com` | empty (required when `EMAIL_BACKEND=smtp`) |
| `SMTP_PORT` | Secret or variable | `587` (STARTTLS) or `465` (implicit TLS) | `587` |
| `SMTP_USERNAME` | Secret | SMTP user name / SES SMTP access key | empty |
| `SMTP_PASSWORD` | Secret | SMTP password / SES SMTP secret | empty |
| `SMTP_START_TLS` | Secret or variable | `true` with port 587 | `true` |
| `SMTP_USE_TLS` | Secret or variable | `true` only with port 465 (then `SMTP_START_TLS=false`) | `false` |
| `SMTP_TIMEOUT_SECONDS` | Secret or variable | `15` | `15` |

**Microsoft Entra SSO** (optional; see step 12)

| Name | Store as | Guide value | Default if unset |
| --- | --- | --- | --- |
| `ENTRA_CLIENT_ID` | Secret or variable | Application (client) ID GUID, e.g. `1b2c3d4e-…` | empty (SSO off) |
| `ENTRA_CLIENT_SECRET` | Secret | Client secret **value** (not the secret ID) | empty |
| `OIDC_STATE_MINUTES` | Secret or variable | `10` | `10` |
| `SSO_RECOVERY_MINUTES` | Secret or variable | `15` | `15` |

**Sessions and sign-in security** (defaults are sensible; set only to change them)

| Name | Guide value | Default if unset | Meaning |
| --- | --- | --- | --- |
| `SESSION_HOURS` | `12` | `12` | Normal session lifetime |
| `REMEMBERED_SESSION_DAYS` | `30` | `30` | Lifetime with "remember me" |
| `PASSWORD_RESET_MINUTES` | `30` | `30` | Reset link validity |
| `INVITATION_EXPIRY_HOURS` | `48` | `48` | Invitation link validity |
| `WORKSPACE_SELECTION_MINUTES` | `5` | `5` | Time to pick a workspace after sign-in |
| `SIGN_IN_RATE_LIMIT` | `10` | `10` | Sign-in attempts per window |
| `PASSWORD_RESET_RATE_LIMIT` | `5` | `5` | Reset requests per window |
| `AUTH_RATE_WINDOW_SECONDS` | `900` | `900` | Rate-limit window |
| `AUTH_RATE_BLOCK_SECONDS` | `900` | `900` | Block duration after hitting the limit |
| `ACCOUNT_LOCKOUT_ATTEMPTS` | `5` | `5` | Failed passwords before lockout |
| `ACCOUNT_LOCKOUT_MINUTES` | `15` | `15` | Lockout duration |

**Email queue and currency conversion** (defaults are sensible)

| Name | Guide value | Default if unset | Meaning |
| --- | --- | --- | --- |
| `OUTBOX_MAX_ATTEMPTS` | `5` | `5` | Delivery attempts per email |
| `OUTBOX_RETRY_BASE_SECONDS` | `30` | `30` | First retry delay (backs off) |
| `OUTBOX_LEASE_SECONDS` | `300` | `300` | How long the worker holds an email |
| `FX_API_BASE_URL` | `https://api.frankfurter.dev/v2` | same | Reference FX rate source |
| `FX_CACHE_MINUTES` | `360` | `360` | FX rate cache duration |

All settings in these two tables can be stored as a secret or a variable.

**Derived automatically from `APP_DOMAIN`** (set only to override)

| Name | Value written | Override only if |
| --- | --- | --- |
| `ALLOWED_HOSTS` | `<APP_DOMAIN>,localhost,127.0.0.1` | More hostnames serve the app. Keep `localhost,127.0.0.1`: the health checks need them. |
| `CORS_ORIGINS` | `https://<APP_DOMAIN>` | Another origin must call the API |
| `CORS_ORIGIN_REGEX` | empty | as above |
| `PUBLIC_APP_URL` | `https://<APP_DOMAIN>` | Links in emails must point elsewhere |
| `PUBLIC_API_URL` | `https://<APP_DOMAIN>/api/v1` | SSO callbacks must point elsewhere |

**Fixed by the workflow** (not configurable): `ENVIRONMENT=production`, `DEBUG=false`, `SESSION_COOKIE_SECURE=true`, `SESSION_COOKIE_NAME=transpire_session`, `CSRF_COOKIE_NAME=transpire_csrf` and `SSO_SELECTION_COOKIE_NAME=transpire_sso_selection`. The frontend reads the CSRF cookie by that exact name.

**Not stored in GitHub:** the `DEV_*` values. They are used only once, by the seed command in step 8.

---

## 6. Set up GitHub Actions deployment

Replace `<account-id>`, `<region>` (e.g. `ap-south-1`), `<instance-id>` and `<org>/<repo>` throughout.

### 6.1 Add GitHub as an identity provider (once per AWS account)

1. **IAM → Identity providers → Add provider**.
2. Provider type: **OpenID Connect**.
3. Provider URL: `https://token.actions.githubusercontent.com`.
4. Audience: `sts.amazonaws.com`.
5. **Add provider**.

Skip this if the provider already exists in the account.

### 6.2 Create the EC2 instance role `transpire-ec2`

1. **IAM → Roles → Create role → AWS service → EC2**.
2. Attach the managed policy `AmazonSSMManagedInstanceCore`. This lets the instance register with Systems Manager so sessions can reach it.
3. Name it `transpire-ec2` and create it.
4. Attach it to the instance: **EC2 → instance → Actions → Security → Modify IAM role → `transpire-ec2`**.
5. After a minute, check **Systems Manager → Fleet Manager**: the instance must be listed as **Online**. If not, reboot the instance and check again.

### 6.3 Create the GitHub Actions role `transpire-github-deploy`

1. **IAM → Roles → Create role → Custom trust policy**, and paste:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
             "token.actions.githubusercontent.com:sub": "repo:<org>/<repo>:environment:production"
           }
         }
       }
     ]
   }
   ```

   The `sub` condition means only jobs running in the repository's `production` environment can assume this role.

2. Skip the managed policies, name the role `transpire-github-deploy`, and create it.
3. Open the role → **Add permissions → Create inline policy → JSON**, and paste:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "PushOneTimeSshKey",
         "Effect": "Allow",
         "Action": "ec2-instance-connect:SendSSHPublicKey",
         "Resource": "arn:aws:ec2:<region>:<account-id>:instance/<instance-id>",
         "Condition": {
           "StringEquals": { "ec2:osuser": "ubuntu" }
         }
       },
       {
         "Sid": "OpenSshTunnel",
         "Effect": "Allow",
         "Action": "ssm:StartSession",
         "Resource": [
           "arn:aws:ec2:<region>:<account-id>:instance/<instance-id>",
           "arn:aws:ssm:<region>::document/AWS-StartSSHSession"
         ]
       },
       {
         "Sid": "ManageOwnSessions",
         "Effect": "Allow",
         "Action": ["ssm:TerminateSession", "ssm:ResumeSession"],
         "Resource": "arn:aws:ssm:<region>:<account-id>:session/transpire-deploy-*"
       }
     ]
   }
   ```

   The role can reach only this one instance, only as `ubuntu`, and only through the SSH session document. `transpire-deploy` is the role session name the workflow uses.

4. Name the policy `transpire-deploy` and save. Copy the role ARN.

### 6.4 Configure the GitHub `production` environment

1. In GitHub: **repository → Settings → Environments → New environment**, and name it `production` (exactly; the trust policy depends on it).
2. Under **Deployment branches and tags**, choose **Selected branches and tags** and add `main`. This stops other branches deploying.
3. Optional: under **Required reviewers**, add people who must approve each deploy.
4. Under **Environment variables**, add:

   | Name | Value |
   | --- | --- |
   | `AWS_REGION` | `<region>` |
   | `AWS_ROLE_ARN` | ARN of `transpire-github-deploy` |
   | `EC2_INSTANCE_ID` | `<instance-id>` (e.g. `i-0abc...`) |
   | `APP_DOMAIN` | `transpire.your-company.com` (no scheme, no slash) |
   | `APP_DIR` | `/opt/transpire` (optional; this is the default) |

   No secrets are needed for AWS access (OIDC) or SSH (a fresh key per run).

5. Under **Environment secrets** (and optionally **Environment variables**), add the application settings from **section 5.3**. At minimum: `DATABASE_URL`, `OUTBOX_ENCRYPTION_KEY` and `EMAIL_FROM_ADDRESS`.

6. The Deploy workflow runs after the `CI` workflow succeeds on `main`. Both workflow files must be on `main` for the trigger to fire.

---

## 7. First deployment

1. Commit and push to `main` (or, if the code is already there, open **Actions → Deploy → Run workflow**, keep **Branch: main**, leave **commit_sha** empty, and run it).
2. Watch **Actions → CI**, then **Actions → Deploy**. The first run takes 6–12 minutes: building both images, then streaming roughly 250–400 MB to the server. Later runs reuse the build cache.
3. Open the **Roll out** step. A successful run ends with the `docker compose ps` table and `==> Deployed <sha>`. If **Write backend settings on the server** fails with `Missing required production settings: …`, add those settings (section 5.3) and re-run the job. If the images were already pushed, the re-run skips the build.
4. On the server, confirm the recorded tag and the running containers:

   ```bash
   grep IMAGE_TAG /opt/transpire/deploy/.env
   ```

   ```bash
   dc ps
   ```

   `backend` and `frontend` should show `(healthy)` and `email-worker` should show `Up`.

5. Check the containers answer on loopback:

   ```bash
   curl -s http://127.0.0.1:8000/health/ready
   ```

   ```bash
   curl -sI http://127.0.0.1:3000/ | head -1
   ```

   Expect `{"status":"ready"}` and `HTTP/1.1 200 OK`.

6. Confirm the migrations reached the latest revision:

   ```bash
   dc run --rm --no-deps backend alembic current
   ```

   The output should end with `(head)`.

The **Smoke test** step fails on this first run, because Nginx isn't set up until step 9. That's expected: re-run the job after step 9.

If the **Roll out** output shows a database error during `alembic upgrade head`, see **Troubleshooting → Database connection**.

---

## 8. Create the first tenant and platform administrator (one time only)

The seed script creates one active tenant with the default workflow, master data and idea-bank policy, plus a platform administrator who is also its tenant admin. It is blocked when `ENVIRONMENT=production`, so this one run overrides the environment to `development`. It runs against the production database and creates **no** sample data.

1. Read the admin password without it appearing in shell history (minimum 12 characters):

   ```bash
   read -rs -p "Admin password: " DEV_ADMIN_PASSWORD && export DEV_ADMIN_PASSWORD && echo
   ```

2. Run the seed, adjusting the tenant slug, tenant name, admin email and admin name:

   ```bash
   dc run --rm --no-deps -e ENVIRONMENT=development -e DEV_ADMIN_PASSWORD -e DEV_TENANT_SLUG=dishman -e "DEV_TENANT_NAME=Dishman Group" -e DEV_ADMIN_EMAIL=admin@your-company.com -e "DEV_ADMIN_NAME=TRANSPIRE Administrator" backend python scripts/seed_development.py
   ```

3. Clear the password from the session:

   ```bash
   unset DEV_ADMIN_PASSWORD
   ```

Do **not** run this again later: re-running resets that admin's password and display name. Add further tenants and people from the admin console.

---

## 9. Configure Nginx (reverse proxy and TLS)

The reference config is [`deploy/nginx/transpire.conf`](deploy/nginx/transpire.conf). Whatever you change, keep these requirements, or the app will break:

| Requirement | Why |
| --- | --- |
| `/api/` and `/health/` → `127.0.0.1:8000`; everything else → `127.0.0.1:3000` | Frontend and API must share one origin for the CSRF cookie |
| `proxy_set_header Host $host` | The backend rejects hosts not in `ALLOWED_HOSTS` |
| `X-Forwarded-For` and `X-Forwarded-Proto` headers | Real client IPs for sign-in rate limiting and audit logs |
| `client_max_body_size` of at least `5m` | Profile photo uploads are up to 2 MB (Nginx defaults to 1 MB) |
| HTTPS only, with port 80 redirecting | Session cookies are `Secure` and are not sent over HTTP |

### 9.1 Install Nginx

```bash
sudo apt -y install nginx
```

```bash
sudo systemctl enable --now nginx
```

If `ufw` is active (`sudo ufw status`), open the web ports:

```bash
sudo ufw allow 'Nginx Full'
```

### 9.2 Install the site config

```bash
sudo cp /opt/transpire/deploy/nginx/transpire.conf /etc/nginx/sites-available/transpire.conf
```

```bash
sudo sed -i 's/transpire.your-company.com/<APP_DOMAIN>/g' /etc/nginx/sites-available/transpire.conf
```

```bash
sudo ln -s /etc/nginx/sites-available/transpire.conf /etc/nginx/sites-enabled/transpire.conf
```

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

### 9.3 Provide the TLS certificate

Choose **one** option.

**Option A: company-issued certificate**

1. Create the directory:

   ```bash
   sudo mkdir -p /etc/ssl/transpire && sudo chmod 700 /etc/ssl/transpire
   ```

2. Copy the full chain (server certificate followed by intermediates) to `/etc/ssl/transpire/fullchain.pem` and the private key to `/etc/ssl/transpire/privkey.pem`.
3. Lock down the key:

   ```bash
   sudo chmod 600 /etc/ssl/transpire/privkey.pem
   ```

**Option B: Let's Encrypt with certbot**

1. Install certbot:

   ```bash
   sudo apt -y install certbot
   ```

2. Comment out the whole `listen 443` server block in `/etc/nginx/sites-available/transpire.conf` (Nginx won't start while the certificate files are missing), then reload:

   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. Request the certificate using the webroot already served on port 80:

   ```bash
   sudo certbot certonly --webroot -w /var/www/html -d <APP_DOMAIN> --email <ops-email> --agree-tos --no-eff-email
   ```

4. Point the config at the certificate: set `ssl_certificate` to `/etc/letsencrypt/live/<APP_DOMAIN>/fullchain.pem` and `ssl_certificate_key` to `/etc/letsencrypt/live/<APP_DOMAIN>/privkey.pem`, then uncomment the 443 block.
5. Make renewals reload Nginx:

   ```bash
   echo 'systemctl reload nginx' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh && sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
   ```

6. Test renewal:

   ```bash
   sudo certbot renew --dry-run
   ```

### 9.4 Enable the site

```bash
sudo nginx -t
```

It must report `syntax is ok` and `test is successful`. Then:

```bash
sudo systemctl reload nginx
```

---

## 10. Verify the deployment

1. Health endpoints (run from your laptop):

   ```bash
   curl -s https://transpire.your-company.com/health/live
   ```

   ```bash
   curl -s https://transpire.your-company.com/health/ready
   ```

   Expect `{"status":"ok"}` and `{"status":"ready"}`.

2. HTTP redirects to HTTPS:

   ```bash
   curl -sI http://transpire.your-company.com | head -3
   ```

   Expect a `301 Moved Permanently`.

3. Internal ports are not reachable from outside (both should time out or be refused):

   ```bash
   curl -m 5 http://<ELASTIC_IP>:8000/health/live
   ```

   ```bash
   curl -m 5 http://<ELASTIC_IP>:3000/
   ```

4. Open `https://transpire.your-company.com/sign-in` in a browser and sign in with the admin from step 8.
5. Open DevTools → Application → Cookies: `transpire_session` must be `Secure` and `HttpOnly`.
6. Create a test idea to confirm writes (and so CSRF) work end to end.
7. Confirm the backend sees real client IPs rather than `172.30.0.1` (the Docker gateway):

   ```bash
   dc logs backend --tail 20
   ```

   If you only see `172.30.0.1`, the `X-Forwarded-For` header is missing from the Nginx config.

---

## 11. Turn on real email

1. Get SMTP credentials (e.g. Amazon SES SMTP, or Microsoft 365 / Exchange relay).
2. In **GitHub → Settings → Environments → production**, set:

   | Name | Value |
   | --- | --- |
   | `EMAIL_BACKEND` | `smtp` |
   | `SMTP_HOST` | e.g. `email-smtp.ap-south-1.amazonaws.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USERNAME` (secret) | your SMTP user |
   | `SMTP_PASSWORD` (secret) | your SMTP password |
   | `SMTP_START_TLS` | `true` |
   | `SMTP_USE_TLS` | `false` |

3. Apply the change by redeploying the current version (step 13.4). This takes about a minute and needs no rebuild.

4. Trigger a password reset for a test user and watch delivery:

   ```bash
   dc logs -f email-worker
   ```

If using SES, verify the sender domain and move the account out of the SES sandbox first.

---

## 12. Microsoft Entra SSO (optional)

1. In the Entra app registration → **Authentication → Web → Redirect URIs**, add:
   - `https://<APP_DOMAIN>/api/v1/auth/sso/global/callback`
   - `https://<APP_DOMAIN>/api/v1/t/<tenant-slug>/auth/sso/callback`, once for each tenant that uses SSO
2. In the GitHub `production` environment, set `ENTRA_CLIENT_ID` and the secret `ENTRA_CLIENT_SECRET`.
3. Apply by redeploying the current version (step 13.4).

---

## 13. Deploying updates

### 13.1 Normal releases

1. Merge or push to `main`.
2. CI runs; if it passes, **Deploy** starts on its own (after approval, if reviewers are configured).
3. Check the Deploy run: every step green, ending with **Smoke test**.

Only one deploy runs at a time; later runs queue behind it.

**When code adds a new backend setting**, add it in the same change to:

- `.github/scripts/render-backend-env.sh`: one `emit NAME "${NAME:-default}"` line,
- the `env:` block of the **Write backend settings on the server** step in `.github/workflows/deploy.yml`: `NAME: ${{ secrets.NAME || vars.NAME }}`,
- the table in section 5.3 of this guide.

Then set its value in GitHub before merging.

**Changing the domain** means updating the `APP_DOMAIN` GitHub variable and Nginx (the backend URLs follow automatically). The frontend image for the current commit must then be rebuilt: push a new commit to `main` (an empty commit is fine: `git commit --allow-empty -m "Rebuild for new domain"`).

### 13.2 What happens if a deploy fails

- **Build or image transfer fails:** nothing changes on the running app.
- **Migration fails:** `deploy.sh` stops before restarting the containers, so the old version keeps running.
- **Health checks fail after restart:** `deploy.sh` restores the containers to the previous tag, prints the logs into the workflow output, and marks the run failed. Database migrations are **not** reverted.

### 13.3 Rolling back or redeploying a specific version

1. Find the commit SHA to return to. `PREVIOUS_IMAGE_TAG` in `/opt/transpire/deploy/.env` is the last version before the current one, or use any earlier successful Deploy run.
2. **Actions → Deploy → Run workflow**, **Branch: main**, and paste the full 40-character SHA into **commit_sha**.
3. Run it. The server keeps the last 5 releases' images, so for those the build is skipped and the rollback takes about a minute. Older SHAs are rebuilt from that commit first.

The `deploy/` files (compose file, `deploy.sh`) from that commit are pushed too, so the server matches the version you roll back to.

Migrations are **not** reversed automatically. If the release you are leaving added a migration the older code can't handle, restore the pre-release backup (step 14) or, after reviewing it, run:

```bash
dc run --rm --no-deps backend alembic downgrade -1
```

### 13.4 Applying a settings change without a new release

1. Update the secret or variable in **GitHub → Settings → Environments → production**.
2. Copy the deployed SHA, shown as `IMAGE_TAG` in `/opt/transpire/deploy/.env`, or the commit of the last successful Deploy run.
3. **Actions → Deploy → Run workflow**, **Branch: main**, and paste that SHA into **commit_sha**.

The images are already on the server, so the build is skipped. The workflow rewrites `backend.env`, and Compose recreates only the containers whose settings changed.

### 13.5 Manual rollback on the server (if GitHub Actions is unavailable)

This works for any SHA whose images are still on the server. It uses the `backend.env` already there:

```bash
docker image ls transpire-backend
```

```bash
bash /opt/transpire/deploy/deploy.sh <sha>
```

---

## 14. Backups

### 14.1 Nightly database dump (PostgreSQL on this host)

1. Create the backup directory:

   ```bash
   sudo mkdir -p /var/backups/transpire && sudo chown postgres:postgres /var/backups/transpire
   ```

2. Add a cron job for the `postgres` user:

   ```bash
   sudo crontab -u postgres -e
   ```

   Append:

   ```
   15 2 * * * pg_dump -Fc transpire > /var/backups/transpire/transpire-$(date +\%F).dump && find /var/backups/transpire -name '*.dump' -mtime +14 -delete
   ```

3. Next day, check a dump exists:

   ```bash
   ls -lh /var/backups/transpire
   ```

### 14.2 Off-host copies

- Copy dumps to S3, e.g. with `aws s3 sync /var/backups/transpire s3://<bucket>/transpire/` from cron. Attach an IAM instance role that can only write to that bucket.
- Enable **EBS snapshots** with Amazon Data Lifecycle Manager (daily, keep 7).
- Keep `OUTBOX_ENCRYPTION_KEY` and the database password in a password manager as well as GitHub: GitHub secrets can't be read back.

### 14.3 Test a restore (do this once)

```bash
sudo -u postgres createdb transpire_restore_test
```

```bash
sudo -u postgres pg_restore -d transpire_restore_test /var/backups/transpire/<file>.dump
```

```bash
sudo -u postgres dropdb transpire_restore_test
```

---

## 15. Day-to-day operations

| Task | Command |
| --- | --- |
| Status | `dc ps` |
| Follow all logs | `dc logs -f --tail 100` |
| One service's logs | `dc logs -f backend` |
| Restart one service | `dc restart backend` |
| Apply settings changes | Update GitHub, then redeploy the current SHA (step 13.4) |
| Stop everything | `dc down` |
| Start everything | `dc up -d` |
| Shell in backend | `dc exec backend sh` |
| Disk usage | `docker system df` and `df -h` |
| Currently deployed version | `grep IMAGE_TAG /opt/transpire/deploy/.env` |
| Test and reload Nginx | `sudo nginx -t && sudo systemctl reload nginx` |
| Nginx logs | `sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log` |

Containers use `restart: unless-stopped`, so they come back after a reboot. Logs rotate at 5 × 10 MB per container.

---

## 16. Troubleshooting

**Database connection fails (`alembic current` errors)**
- `Connection refused`: PostgreSQL isn't listening on the Docker-facing interface. Recheck `listen_addresses` and restart PostgreSQL (3A step 2).
- `no pg_hba.conf entry`: the `172.30.0.0/24` line is missing or below a conflicting `reject` line (3A step 3).
- Timeout: `ufw` is blocking the subnet (3A step 5), or for 3B a security group or `pg_hba` doesn't allow the EC2 private IP.
- `password authentication failed`: the password in `DATABASE_URL` is wrong or contains characters that need URL-encoding. Regenerate it with the `tr -d '/+='` command from 3.1.

**Deploy job: `Could not assume role` / `Not authorized to perform sts:AssumeRoleWithWebIdentity`**
The trust policy `sub` doesn't match. It must be exactly `repo:<org>/<repo>:environment:production`, and the workflow job must use the `production` environment.

**`TargetNotConnected` or `is not connected` when opening the SSH session**
The instance isn't registered with SSM. Check Fleet Manager (step 6.2), that the `transpire-ec2` role is attached, and that the SSM agent is running (step 2.5).

**`AccessDeniedException` calling `StartSession` or `SendSSHPublicKey`**
The inline policy's region, account ID or instance ID doesn't match (step 6.3).

**`Permission denied (publickey)`**
EC2 Instance Connect isn't installed on the server (step 2.5), or more than 60 seconds passed between pushing the key and connecting. Re-run the job; if it persists, check `sudo journalctl -u ssh --since "10 min ago"` on the server.

**`Image transpire-backend:<sha> is not on this host`**
A manual rollback named a release that has been pruned. Run **Actions → Deploy** with that `commit_sha` instead, which rebuilds it.

**Image transfer is very slow or the session drops**
SSM tunnels are slower than direct SSH. Check the instance has outbound internet (or VPC endpoints for `ssm`, `ssmmessages` and `ec2messages`), then re-run.

**`Commit must be a full 40-character SHA`**
When rolling back, paste the full SHA, not the short one.

**Backend exits immediately**
Run `dc logs backend`. `OUTBOX_ENCRYPTION_KEY is invalid` means the secret isn't a valid Fernet key; regenerate it as in step 5.2 (only if no emails are queued). `validation error` names the setting with a wrong value in GitHub (section 5.3).

**Write backend settings step: `Missing required production settings`**
Add the named secrets or variables to the `production` environment (section 5.3). Names are case-sensitive.

**Write backend settings step: `… must not contain single quotes or line breaks`**
Re-enter the value without `'` or a trailing newline. For a password, regenerate it with the command in step 3.1.

**`400 Invalid host header`**
The site is being reached on a hostname other than `APP_DOMAIN` (or an `ALLOWED_HOSTS` override leaves it out), or Nginx isn't sending `proxy_set_header Host $host`. Fix the GitHub setting and redeploy (step 13.4), or fix and reload Nginx.

**Browser calls `localhost:8000` or the wrong domain, or shows CORS errors**
The `APP_DOMAIN` GitHub variable was wrong or missing when the frontend image was built. Fix it, then follow **Changing the domain** in step 13.1 to force a rebuild.

**Sign-in works but saving anything returns 403 (CSRF)**
The site is being opened on a different hostname from `APP_DOMAIN` (e.g. the raw IP). Always use the domain.

**`502 Bad Gateway` from Nginx**
A container is down or not yet healthy. Run `dc ps`, then `curl http://127.0.0.1:8000/health/live` on the server. Check `sudo tail -50 /var/log/nginx/error.log`.

**`413 Request Entity Too Large` when uploading a profile photo**
`client_max_body_size` is missing or below `5m` in the Nginx site.

**certbot fails**
DNS doesn't point at the Elastic IP yet, port 80 is closed in the security group, or the port-80 server block isn't serving `/.well-known/acme-challenge/` from `/var/www/html`. Let's Encrypt rate-limits repeated failures, so check DNS first.

**Users are logged out immediately, or the browser shows "Not secure"**
The site is being served over plain HTTP. Session cookies are `Secure`, so it must be HTTPS end to end at Nginx.


**Emails stay queued**
Run `dc logs email-worker`. Check the SMTP settings, and that `OUTBOX_ENCRYPTION_KEY` has not changed since the emails were queued.

---

## 17. Hardening checklist (after go-live)

- [ ] SSH (22) removed from the security group, or restricted to your office/VPN IP. Deploys don't need it
- [ ] Unattended security upgrades: `sudo apt -y install unattended-upgrades`
- [ ] CloudWatch alarm on instance status checks and disk usage
- [ ] Uptime check on `https://<APP_DOMAIN>/health/ready`
- [ ] TLS expiry monitoring (certbot renewals succeed, or the company certificate renewal is on the calendar)
- [ ] Backups copied off-host and a restore tested (step 14)
- [ ] `OUTBOX_ENCRYPTION_KEY` and the database password backed up outside GitHub
- [ ] Required reviewers set on the GitHub `production` environment
- [ ] DNS TTL raised back to 3600 once stable
