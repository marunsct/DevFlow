#!/usr/bin/env bash
# Generate the secrets a first run needs, appending only what is missing.
#
# Safe to re-run: existing values are never overwritten, so this cannot rotate a
# secret out from under a running deployment by accident.
set -euo pipefail

ENV_FILE="${1:-.env}"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

add_if_missing() {
  local key="$1" value="$2" comment="${3:-}"
  if grep -qE "^${key}=." "$ENV_FILE" 2>/dev/null; then
    echo "  keeping existing ${key}"
    return
  fi
  # Replace an empty placeholder in place, otherwise append.
  if grep -qE "^${key}=$" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=$|${key}=${value}|" "$ENV_FILE"
  else
    [ -n "$comment" ] && printf '\n# %s\n' "$comment" >> "$ENV_FILE"
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
  echo "  set ${key}"
}

gen() { python3 -c "import secrets;print(secrets.token_hex(32))"; }
genpw() { python3 -c "import secrets;print(secrets.token_urlsafe(24))"; }

echo "Preparing $ENV_FILE"
fresh_jwt=1
grep -qE "^JWT_SECRET_KEY=." "$ENV_FILE" && fresh_jwt=0
add_if_missing JWT_SECRET_KEY     "$(gen)"   "Generated secrets - keep out of version control"
add_if_missing ADMIN_PASSWORD     "$(genpw)"
add_if_missing POSTGRES_PASSWORD  "$(genpw)"
add_if_missing POSTGRES_USER      "postgres"
add_if_missing POSTGRES_DB        "langchain"
add_if_missing ENV                "production"
add_if_missing CHECKPOINTER_TYPE  "postgres"
# The harness's Redis (its queue) takes a password: product commands run on the worker's network.
add_if_missing REDIS_PASSWORD     "$(genpw)"
# No object store is written here: with OBJECT_STORE_BUCKET unset, uploads and run artifacts are kept on the local
# filesystem under DATA_DIR. To use Amazon S3 or your own S3-compatible service, set OBJECT_STORE_BUCKET and its
# endpoint and keys by hand (see .env.example); the compose file no longer ships a MinIO for the bucket to name.
# Without a dedicated key this is derived from JWT_SECRET_KEY, which means
# rotating that one silently invalidates every stored provider credential.
# Only on a fresh file: an existing deployment's stored credentials were
# encrypted with the key derived from its JWT_SECRET_KEY, and a new key here
# would make every one of them unreadable at the next restart.
if [ "$fresh_jwt" = 1 ] || grep -qE "^SETTINGS_ENCRYPTION_KEY=." "$ENV_FILE"; then
  add_if_missing SETTINGS_ENCRYPTION_KEY "$(gen)"
else
  echo "  not setting SETTINGS_ENCRYPTION_KEY: stored credentials use the key derived from the existing JWT_SECRET_KEY"
fi

echo
echo "Done. Sign in as 'admin' with:"
grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-
