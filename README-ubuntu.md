# Ubuntu Deployment Guide (mcp-oci-integration)

This guide explains how to deploy the full stack on an Ubuntu machine using Docker Compose.

## 1. Project readiness

Yes, the project is already prepared for containerized deployment through:

- `deploy/compose/docker-compose.local.yml`
- `deploy/config/aggregator_config.docker.yaml`
- `Dockerfile`

Deployment works correctly only if you prepare the required local settings (`.env`, `config_private.py`, ADB wallet, OCI credentials).

## 2. Ubuntu prerequisites

Recommended: Ubuntu 22.04 LTS or 24.04 LTS.

Install base packages:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
```

Install Docker Engine + Docker Compose plugin (official Docker method):

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Enable Docker at boot and (optional) allow non-sudo usage:

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

After `usermod`, log out and back in.

## 3. Clone the repository

```bash
git clone <REPO-URL> mcp-oci-integration
cd mcp-oci-integration
```

## 4. Required local configuration

### 4.1 `.env` file

Create the file:

```bash
cp .env.example .env
```

Set at least these variables (required by compose):

- `VECTOR_DB_USER`
- `VECTOR_DB_PWD`
- `VECTOR_WALLET_PWD`
- `VECTOR_DSN`
- `VECTOR_WALLET_DIR_HOST` (absolute path on the Ubuntu server)

Also add these recommended deployment variables:

- `ENABLE_JWT_TOKEN=true` or `false`
- `OCI_CONFIG_DIR=/home/<user>/.oci`

Example `.env`:

```env
VECTOR_DB_USER=...
VECTOR_DB_PWD=...
VECTOR_WALLET_PWD=...
VECTOR_DSN=...
VECTOR_WALLET_DIR_HOST=/opt/oci/wallet

ENABLE_JWT_TOKEN=true
OCI_CONFIG_DIR=/home/ubuntu/.oci
```

### 4.2 `config_private.py`

This file must exist in the project root (it is imported by the UI/agent code). If missing, Python containers will fail at import time.

You can start from `config_private_template.py`, but include all fields currently used by the code.

Recommended minimal template:

```python
import os

def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default

VECTOR_DB_USER = _env_str("VECTOR_DB_USER", "")
VECTOR_DB_PWD = _env_str("VECTOR_DB_PWD", "")
VECTOR_DSN = _env_str("VECTOR_DSN", "")
VECTOR_WALLET_DIR = _env_str("VECTOR_WALLET_DIR", "/opt/oci/wallet")
VECTOR_WALLET_PWD = _env_str("VECTOR_WALLET_PWD", "")

CONNECT_ARGS = {
    "user": VECTOR_DB_USER,
    "password": VECTOR_DB_PWD,
    "dsn": VECTOR_DSN,
    "config_dir": VECTOR_WALLET_DIR,
    "wallet_location": VECTOR_WALLET_DIR,
    "wallet_password": VECTOR_WALLET_PWD,
}

COMPARTMENT_ID = _env_str("COMPARTMENT_ID", "")
JWT_SECRET = _env_str("JWT_SECRET", "oracle-ai")
JWT_ALGORITHM = _env_str("JWT_ALGORITHM", "HS256")
OCI_CLIENT_ID = _env_str("OCI_CLIENT_ID", "")
SECRET_OCID = _env_str("SECRET_OCID", "")
OCI_APM_DATA_KEY = _env_str("OCI_APM_DATA_KEY", "")

GITHUB_USERNAME = _env_str("GITHUB_USERNAME", "")
GITHUB_TOKEN = _env_str("GITHUB_TOKEN", "")
```

Note: `config_private.py` is already ignored by git in `.gitignore`.

### 4.3 OCI config (`~/.oci/config`)

Compose mounts your OCI directory into containers (`/root/.oci`).

Ensure the server has:

- `/home/<user>/.oci/config`
- all keys/files required by the OCI profile in use

If you use a different location, set `OCI_CONFIG_DIR` accordingly.

### 4.4 ADB wallet

Ensure `VECTOR_WALLET_DIR_HOST` points to an existing server directory containing wallet files (`tnsnames.ora`, `sqlnet.ora`, etc.).

Example:

```bash
sudo mkdir -p /opt/oci/wallet
sudo chown -R $USER:$USER /opt/oci/wallet
# copy wallet files here
```

## 5. How JWT is decided

In compose, this is set as:

- `ENABLE_JWT_TOKEN: "${ENABLE_JWT_TOKEN:-false}"`

So the `.env` (or shell) value takes precedence; if missing, it defaults to `false`.

Even if `deploy/config/aggregator_config.docker.yaml` has `enable_jwt_tokens: true`, runtime behavior can be overridden by the environment variable.

## 6. Start the stack

From project root:

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml up --build -d
```

Main endpoints:

- UI via nginx: `http://<SERVER_IP>:8194`
- MCP aggregator: `http://<SERVER_IP>:6000/mcp`

## 7. Quick checks

Show running containers:

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml ps
```

Follow all logs:

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f
```

Follow aggregator logs:

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_aggregator
```

## 8. Stop / restart / update

Stop and remove containers:

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml down
```

Rebuild and restart after code updates:

```bash
git pull
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml up --build -d
```

## 9. Ports and firewall

Open at least:

- `8194/tcp` (UI)
- optional `6000/tcp` if you want direct external access to the aggregator

UFW example:

```bash
sudo ufw allow 8194/tcp
sudo ufw allow 6000/tcp
sudo ufw enable
sudo ufw status
```

## 10. Quick troubleshooting

- `set in .env` error: one or more required variables are missing in `.env`.
- JWT appears disabled: set `ENABLE_JWT_TOKEN=true` in `.env` and restart.
- OCI auth errors: verify `OCI_CONFIG_DIR` mount and `~/.oci/config` contents.
- DB wallet errors: verify `VECTOR_WALLET_DIR_HOST` path and wallet files.
- `config_private` import crash: file missing or required fields not defined.

## 11. Production hardening suggestions

- Use a dedicated non-privileged OS user for deployment.
- Restrict network access (security lists / NSG / firewall) to required ports only.
- Avoid plaintext secrets in files where possible; use a secret manager.
- Put TLS in front of `8194` using a reverse proxy (Nginx/Traefik + certificates).
- Enable monitoring and log rotation for containers.
