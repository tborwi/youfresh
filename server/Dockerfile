FROM python:3.12-alpine
RUN apk add --no-cache su-exec tzdata && pip install --no-cache-dir --root-user-action=ignore yt-dlp
WORKDIR /app
COPY youfresh.py channels.html entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh
ENV YOUFRESH_DIR=/youfresh PORT=8099 PUID=1000 PGID=1000
EXPOSE 8099
VOLUME ["/youfresh"]
ENTRYPOINT ["/app/entrypoint.sh"]
