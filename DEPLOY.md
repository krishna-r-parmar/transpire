# Deploying TRANSPIRE to AWS EC2 with Docker

This guide runs the frontend, backend and email worker as Docker containers on one EC2 instance. **GitHub Actions** deploys them through **AWS Systems Manager (SSM)**. Two things are **not** containerised:

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
                 Deploy workflow (GitHub Actions)
                   ├─ assume IAM role via GitHub OIDC          (no AWS keys stored in GitHub)
                   ├─ aws ssm send-command  ──▶ EC2             (no SSH, no inbound port)
                   │     cd /opt/transpire
                   │     git fetch && git checkout <sha>        (repo cloned on EC2)
                   │     deploy/deploy.sh
                   │        ├─ docker compose build
                   │        ├─ alembic upgrade head
                   │        ├─ docker compose up -d             (restart containers)
                   │        └─ wait for health checks
                   ├─ wait for the SSM command, print its output
                   └─ smoke test https://<APP_DOMAIN>/health/ready
```

The frontend and API share one origin (`https://<APP_DOMAIN>`). This is required: the browser reads the CSRF cookie set by the API, which only works when both are on the same host.

Production files:

| File | Purpose |
| --- | --- |
| `.github/workflows/deploy.yml` | After CI passes on `main`: runs the deploy on EC2 via SSM, then smoke-tests |
| `deploy/deploy.sh` | On EC2: build, migrate, restart, health check, clean up |
| `deploy/docker-compose.prod.yml` | Production stack (no database or proxy service; ports bound to loopback) |
| `deploy/nginx/transpire.conf` | Reference Nginx site (routing, headers, TLS, body size) |
| `deploy/compose.env.example` | Template for `deploy/.env` (public domain) |
| `deploy/backend.env.example` | Template for `deploy/backend.env` (backend settings and secrets) |

The steps assume **Ubuntu 24.04** on the EC2 host and an install path of `/opt/transpire`. Commands prefixed with `sudo` run on the server.

---

## 0. Before you start

Have these ready:

- [ ] An AWS account with permission to manage EC2, security groups, Elastic IPs, IAM and Systems Manager
- [ ] Admin access to the GitHub repository (to add a deploy key, an environment and variables)
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
   | SSH | 22 | **My IP** (not `0.0.0.0/0`), or omit entirely | Optional admin access. Deploys go through SSM, and admins can use **Session Manager** instead |
   | HTTP | 80 | `0.0.0.0/0`, `::/0` | Redirect to HTTPS (and Let's Encrypt validation, if used) |
   | HTTPS | 443 | `0.0.0.0/0`, `::/0` | The app |

4. Do **not** add 3000, 8000 or 5432. If PostgreSQL is on a separate server, open 5432 on *that* server's security group, with this instance's security group as the source.
5. Leave outbound as "All traffic".

### 1.2 Instance

1. **EC2 → Launch instance**.
2. AMI: **Ubuntu Server 24.04 LTS (x86_64)**.
3. Instance type: **t3.large** (2 vCPU, 8 GB) if PostgreSQL shares the host. Use **t3.medium** (4 GB) if the database is on another server. The server builds the images itself, so allow memory headroom (and add swap, step 2.3).
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

### 2.3 Add swap (prevents the image build running out of memory)

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

### 2.5 Check the SSM agent

GitHub Actions runs the deploy through the SSM agent, which is preinstalled on Ubuntu AMIs. Confirm:

```bash
sudo snap services amazon-ssm-agent
```

The agent must show `active`. If it does not, run `sudo snap start --enable amazon-ssm-agent`.

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

## 4. Clone the repository on the server

The server keeps a git checkout of the repo. Each deploy fetches and checks out the commit being released.

```bash
sudo mkdir -p /opt/transpire && sudo chown ubuntu:ubuntu /opt/transpire
```

Create a read-only deploy key so the server can fetch from GitHub:

```bash
ssh-keygen -t ed25519 -N '' -C transpire-ec2-deploy -f ~/.ssh/transpire_deploy
```

```bash
cat ~/.ssh/transpire_deploy.pub
```

In GitHub: **repository → Settings → Deploy keys → Add deploy key**. Paste the key, title it `transpire-ec2`, and leave **Allow write access unchecked**.

Tell SSH to use it for GitHub:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/transpire_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
```

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
```

```bash
ssh -T git@github.com
```

Expect `You've successfully authenticated, but GitHub does not provide shell access.` Then clone with the **SSH** URL:

```bash
git clone git@github.com:<org>/<repo>.git /opt/transpire
```

Add a shortcut for the production Compose command. Later manual steps use `dc`:

```bash
echo "alias dc='docker compose --project-directory /opt/transpire/deploy -f /opt/transpire/deploy/docker-compose.prod.yml'" >> ~/.bashrc && source ~/.bashrc
```

---

## 5. Configure environment files

Both files live only on the server. They are gitignored, so `git checkout` during deploys never touches them.

### 5.1 Compose settings (domain)

```bash
cp /opt/transpire/deploy/compose.env.example /opt/transpire/deploy/.env
```

```bash
nano /opt/transpire/deploy/.env
```

Set `APP_DOMAIN` to your domain (no `https://`, no trailing slash). It is baked into the frontend at build time, and must be the exact hostname Nginx serves.

### 5.2 Backend settings and secrets

```bash
cp /opt/transpire/deploy/backend.env.example /opt/transpire/deploy/backend.env && chmod 600 /opt/transpire/deploy/backend.env
```

Generate the outbox encryption key (a Fernet key) and copy the output:

```bash
python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Edit the file:

```bash
nano /opt/transpire/deploy/backend.env
```

Change these values:

| Setting | Guide value |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://transpire:<db-password>@host.docker.internal:5432/transpire` (3A), or with the DB server address (3B) |
| `ALLOWED_HOSTS` | `<APP_DOMAIN>,localhost,127.0.0.1` |
| `CORS_ORIGINS` | `https://<APP_DOMAIN>` |
| `PUBLIC_APP_URL` | `https://<APP_DOMAIN>` |
| `PUBLIC_API_URL` | `https://<APP_DOMAIN>/api/v1` |
| `OUTBOX_ENCRYPTION_KEY` | the generated key |
| `EMAIL_FROM_ADDRESS` | your sender address, e.g. `no-reply@your-company.com` |

Leave `ENVIRONMENT=production` and `SESSION_COOKIE_SECURE=true`. The backend refuses to start in production without a secure cookie and an encryption key. Leave the cookie names as they are: the frontend reads the CSRF cookie by that exact name.

**Back up `OUTBOX_ENCRYPTION_KEY` and the database password in a password manager.** If the key is lost, queued emails can no longer be decrypted.

Check for leftover placeholders. This should print nothing:

```bash
grep -n '<\|your-company' /opt/transpire/deploy/backend.env /opt/transpire/deploy/.env
```

---

## 6. Set up GitHub Actions → SSM

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
2. Attach the managed policy `AmazonSSMManagedInstanceCore`. This lets the instance receive SSM commands.
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
             "token.actions.githubusercontent.com:sub": "repo:<org>/<repo>:ref:refs/heads/main"
           }
         }
       }
     ]
   }
   ```

   The `sub` condition means only workflow runs from the `main` branch of this repository can assume this role. Runs from other branches or pull requests are refused by AWS.

2. Skip the managed policies, name the role `transpire-github-deploy`, and create it.
3. Open the role → **Add permissions → Create inline policy → JSON**, and paste:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "RunDeployOnInstance",
         "Effect": "Allow",
         "Action": "ssm:SendCommand",
         "Resource": [
           "arn:aws:ec2:<region>:<account-id>:instance/<instance-id>",
           "arn:aws:ssm:<region>::document/AWS-RunShellScript"
         ]
       },
       {
         "Sid": "ReadDeployResult",
         "Effect": "Allow",
         "Action": "ssm:GetCommandInvocation",
         "Resource": "*"
       }
     ]
   }
   ```

   The role can only run shell commands on this one instance and read their results.

4. Name the policy `transpire-deploy` and save. Copy the role ARN.

### 6.4 Add the GitHub Actions variables

1. In GitHub: **repository → Settings → Secrets and variables → Actions → Variables tab → New repository variable**.
2. Add each of these:

   | Name | Guide value |
   | --- | --- |
   | `AWS_REGION` | `<region>`, e.g. `ap-south-1` |
   | `AWS_ROLE_ARN` | `arn:aws:iam::<account-id>:role/transpire-github-deploy` |
   | `EC2_INSTANCE_ID` | `<instance-id>`, e.g. `i-0abc1234def567890` |
   | `APP_DOMAIN` | `transpire.your-company.com` (used only by the smoke test) |
   | `APP_DIR` | `/opt/transpire` (optional; this is the default) |

   No GitHub secrets are needed: AWS access uses OIDC.

3. The Deploy workflow runs after the `CI` workflow succeeds on `main`. Both workflow files must be on `main` for the trigger to fire.

---

## 7. First deployment

1. Commit and push to `main`. If the code is already there, open **Actions → Deploy → Run workflow**, keep **Branch: main**, leave **commit_sha** empty, and run it.
2. Watch **Actions → CI**, then **Actions → Deploy**. The first run takes 5–10 minutes, because the server builds both images from scratch. Later builds reuse Docker's cache.
3. Expand **Server output** in the deploy step. A successful run ends with the `docker compose ps` table and `==> Deployed`.

   You can also see each run in **AWS → Systems Manager → Run Command → Command history**.

4. On the server, confirm the deployed commit and the running containers:

   ```bash
   git -C /opt/transpire log -1 --oneline
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

If the server output shows a database error during `alembic upgrade head`, see **Troubleshooting → Database connection**.

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
2. Edit `/opt/transpire/deploy/backend.env`:

   ```
   EMAIL_BACKEND=smtp
   SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
   SMTP_PORT=587
   SMTP_USERNAME=<smtp-user>
   SMTP_PASSWORD=<smtp-password>
   SMTP_START_TLS=true
   SMTP_USE_TLS=false
   ```

3. Apply the change. Settings-only changes need no rebuild:

   ```bash
   dc up -d backend email-worker
   ```

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
2. Set `ENTRA_CLIENT_ID` and `ENTRA_CLIENT_SECRET` in `/opt/transpire/deploy/backend.env`.
3. Apply:

   ```bash
   dc up -d backend
   ```

---

## 13. Deploying updates

### 13.1 Normal releases

1. Merge or push to `main`.
2. CI runs; if it passes, **Deploy** starts on its own.
3. Check the Deploy run: the SSM step and **Smoke test** are green.

Only one deploy runs at a time; later runs queue behind it.

**When a change adds backend settings**, add the new keys to `/opt/transpire/deploy/backend.env` on the server **before** merging. Deploys don't edit that file. To see what changed in the template, run this on your laptop:

```bash
git diff <deployed-sha> origin/main -- deploy/backend.env.example
```

**Changing the domain:** update `APP_DOMAIN` in `deploy/.env` (it is baked into the frontend), `backend.env`, Nginx and the GitHub variable, then redeploy.

### 13.2 What happens if a deploy fails

- **`git fetch` or build fails:** the running containers are untouched.
- **Migration fails:** the script stops before restarting, so the old containers keep running.
- **Health checks fail after restart:** the script prints the logs into the workflow output and the run fails. Roll back with step 13.3.

### 13.3 Rolling back

1. Find the last good commit SHA, from an earlier successful Deploy run or `git log` on your laptop.
2. **Actions → Deploy → Run workflow**, **Branch: main**, and paste the full 40-character SHA into **commit_sha**.
3. Run it. The server checks out that commit, rebuilds and restarts. Docker's cache usually makes this quick.

Migrations are **not** reversed automatically. If the release you are leaving added a migration the older code can't handle, restore the pre-release backup (step 14) or, after reviewing it, run:

```bash
dc run --rm --no-deps backend alembic downgrade -1
```

### 13.4 Manual deploy on the server (if GitHub Actions is unavailable)

```bash
cd /opt/transpire && git fetch origin && git checkout --detach origin/main && bash deploy/deploy.sh
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
- Keep `deploy/.env`, `deploy/backend.env` and `OUTBOX_ENCRYPTION_KEY` in a password manager or secret store. They are not in Git.

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
| Apply `backend.env` changes | `dc up -d backend email-worker` |
| Stop everything | `dc down` |
| Start everything | `dc up -d` |
| Shell in backend | `dc exec backend sh` |
| Disk usage | `docker system df` and `df -h` |
| Currently deployed commit | `git -C /opt/transpire log -1 --oneline` |
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
The trust policy `sub` doesn't match. It must be exactly `repo:<org>/<repo>:ref:refs/heads/main` (owner and repo names are case-sensitive), and the run must be from `main`. A manual run with **Branch** set to anything else is refused.

**`InvalidInstanceId` from `send-command`**
The instance isn't registered with SSM. Check Fleet Manager (step 6.2), that the `transpire-ec2` role is attached, and that the SSM agent is running (step 2.5).

**`AccessDeniedException` calling `SendCommand`**
The inline policy's region, account ID or instance ID doesn't match (step 6.3).

**Server output: `Permission denied (publickey)` during `git fetch`**
The deploy key isn't set up for the `ubuntu` user (step 4). Test with `ssh -T git@github.com` as `ubuntu`.

**Server output: `detected dubious ownership in repository`**
`/opt/transpire` isn't owned by `ubuntu`. Fix with `sudo chown -R ubuntu:ubuntu /opt/transpire`.

**SSM status `TimedOut`, or the build is killed (exit code 137)**
The build ran out of memory or time. Confirm swap is active (`free -h`, step 2.3) or use a larger instance.

**`Commit must be a full 40-character SHA`**
When rolling back, paste the full SHA, not the short one.

**Backend exits immediately**
Run `dc logs backend`. `SESSION_COOKIE_SECURE must be true` or `OUTBOX_ENCRYPTION_KEY is required` means a value in `deploy/backend.env` is missing.

**`400 Invalid host header`**
`ALLOWED_HOSTS` in `backend.env` doesn't contain the exact `APP_DOMAIN`, or Nginx isn't sending `proxy_set_header Host $host`. Fix it, then run `dc up -d backend` (or reload Nginx).

**Browser calls `localhost:8000` or the wrong domain, or shows CORS errors**
`APP_DOMAIN` in `deploy/.env` was wrong when the frontend was built. Fix it, then run `bash /opt/transpire/deploy/deploy.sh` (or redeploy from GitHub).

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
- [ ] `OUTBOX_ENCRYPTION_KEY` and the database password backed up off the server
- [ ] DNS TTL raised back to 3600 once stable
