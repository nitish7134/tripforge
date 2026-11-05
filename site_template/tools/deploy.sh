#!/usr/bin/env bash
# Deploy the trip site. Gates: fresh build, node --check, privacy scan, SW cache bump; then copy + install -m 644.
# Usage: DEPLOY_HOST=myhost DEPLOY_ROOT=/var/www/my-trip [SITE_URL=https://example.org/my-trip] \
#        [PRIVATE=../private_patterns.txt] tools/deploy.sh [files...]   (default: index.html sw.js data/plans.json)
# Before announcing a deploy, open the page on a phone-sized viewport and read the console: the service worker
# can keep serving the old page on one device and hide a broken build.
set -euo pipefail
: "${DEPLOY_HOST:?set DEPLOY_HOST (an ssh host alias)}" "${DEPLOY_ROOT:?set DEPLOY_ROOT (web root on the host)}"
SITE=$(cd "$(dirname "$0")/.." && pwd); cd "$SITE"
FILES=("$@"); [ ${#FILES[@]} -eq 0 ] && FILES=(index.html sw.js data/plans.json)

python3 tools/build.py || exit 1                     # also runs node --check on the inlined script

PATS='[A-Z][0-9]{7}|passport (no|number)'           # always; add the trip's names, refs and PINs in $PRIVATE
if [ -n "${PRIVATE:-}" ]; then PATS="$PATS|$(grep -v '^\s*$' "$PRIVATE" | paste -sd'|' -)"; fi
if grep -nEi "$PATS" index.html data/*.json 2>/dev/null; then echo "PRIVATE DATA found, not deploying"; exit 1; fi

v=$(grep -o "trip-v[0-9]*" sw.js | head -1 | tr -dc 0-9); nv=$((v+1))
python3 - "$v" "$nv" <<'EOF'
import sys, pathlib; p = pathlib.Path('sw.js'); p.write_text(p.read_text().replace(f"trip-v{sys.argv[1]}'", f"trip-v{sys.argv[2]}'"))
EOF
echo "sw cache: trip-v$v -> trip-v$nv"

for im in img/*.jpg img/stays/*.jpg; do [ -f "$im" ] && FILES+=("$im"); done
STAGE=$(ssh "$DEPLOY_HOST" mktemp -d)
scp -q "${FILES[@]}" "$DEPLOY_HOST:$STAGE/"
for f in "${FILES[@]}"; do
  ssh "$DEPLOY_HOST" "sudo install -D -m 644 $STAGE/$(basename "$f") $DEPLOY_ROOT/$f"
done
ssh "$DEPLOY_HOST" "find $STAGE -mindepth 1 -delete; rmdir $STAGE"
[ -n "${SITE_URL:-}" ] && echo "live: $(curl -s "$SITE_URL/sw.js" | grep -o 'trip-v[0-9]*' | head -1) (expect trip-v$nv; the cookie gate may 302 this)"
