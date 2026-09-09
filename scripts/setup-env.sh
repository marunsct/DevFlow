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
add_if_missing JWT_SECRET_KEY     "$(gen)"   "Generated secrets - keep out of version control"
add_if_missing ADMIN_PASSWORD     "$(genpw)"
add_if_missing POSTGRES_PASSWORD  "$(genpw)"
add_if_missing POSTGRES_USER      "postgres"
add_if_missing POSTGRES_DB        "langchain"
add_if_missing ENV                "production"
add_if_missing CHECKPOINTER_TYPE  "postgres"

echo
echo "Done. Sign in as 'admin' with:"
grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-
