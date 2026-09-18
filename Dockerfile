FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS web
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY dashboard/frontend/package*.json dashboard/frontend/
COPY docs/package*.json docs/
RUN npm --prefix dashboard/frontend ci --no-audit --no-fund && npm --prefix docs ci --no-audit --no-fund
COPY dashboard/frontend dashboard/frontend
COPY docs docs
COPY tokens.css ./
RUN npm --prefix dashboard/frontend run build && npm --prefix docs run build

FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS python-builder
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock && /opt/venv/bin/pip check

FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 tueka && useradd --uid 10001 --gid 10001 --no-create-home tueka && mkdir /data && chown 10001:10001 /data
COPY --from=python-builder /opt/venv /opt/venv
COPY automod automod
COPY cogs cogs
COPY community community
COPY dashboard dashboard
COPY database database
COPY discord_io discord_io
COPY docs docs
COPY engagement engagement
COPY guild_settings guild_settings
COPY jobs jobs
COPY migrations migrations
COPY moderation moderation
COPY reaction_roles reaction_roles
COPY runtime runtime
COPY scripts scripts
COPY social social
COPY suggestions suggestions
COPY tests tests
COPY ticketing ticketing
COPY *.py requirements.lock .env.example tokens.css tueka-icon.png banned_words.csv ./
COPY --from=web /app/dashboard/frontend/dist dashboard/frontend/dist
COPY --from=web /app/docs/.vitepress/dist docs/.vitepress/dist
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "runtime"]
CMD ["dashboard"]
