# Use a slim Python image
FROM python:3.12-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/downloads \
    && chown -R appuser:appuser /app

# Copy dependency files first to leverage caching
COPY pyproject.toml uv.lock ./

# Sync dependencies (excluding the project itself)
RUN uv sync --frozen --no-install-project

# Copy the rest of the application files
COPY src ./src
COPY README.md ./

# Sync project
RUN uv sync --frozen

USER appuser

# Expose FastMCP default port
EXPOSE 6969

# Environment configuration defaults
ENV PORT=6969
ENV MOODLE_API_BASE=http://ekursy-zero:8080
ENV FASTMCP_HOME=/app/data

# The environment is fully synchronized at build time. Running Python directly
# avoids a runtime package/cache mutation under the unprivileged account.
CMD ["/app/.venv/bin/python", "src/main.py"]
