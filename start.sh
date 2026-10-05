#!/bin/sh
# YouTube changes often; refreshing yt-dlp on start fixes most "download failed" errors.
if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
  pip install --user -q -U "yt-dlp[default]" || echo "yt-dlp update skipped"
  export PATH="$HOME/.local/bin:$PATH"   # user site-packages already take priority
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*'
