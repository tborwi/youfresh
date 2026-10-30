#!/bin/sh
# YouTube changes often; keep yt-dlp current. The server still starts if this can't reach PyPI.
if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
  pip install -q -U --no-cache-dir --root-user-action=ignore --disable-pip-version-check yt-dlp || true
fi
# Create the drop folders and give them to your user (PUID/PGID), so you can copy files in.
BASE="${YOUFRESH_DIR:-/youfresh}"
mkdir -p "$BASE/takeout" "$BASE/cookies" "$BASE/data"
chown "$PUID:$PGID" "$BASE" "$BASE/takeout" "$BASE/cookies" 2>/dev/null || true
chown -R "$PUID:$PGID" "$BASE/data" 2>/dev/null || true
chmod 700 "$BASE/cookies" 2>/dev/null || true
exec su-exec "$PUID:$PGID" python -u /app/youfresh.py
