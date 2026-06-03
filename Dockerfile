# Use a slim Python image
FROM python:3.12-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage caching
COPY pyproject.toml uv.lock ./

# Sync dependencies (excluding the project itself)
RUN uv sync --frozen --no-install-project

# Copy the rest of the application files
COPY src ./src
COPY README.md ./

# Sync project
RUN uv sync --frozen

# Expose FastMCP default port
EXPOSE 6969

# Environment configuration defaults
ENV PORT=6969
ENV MOODLE_API_BASE=http://ekursy-zero:8080

# Run the application using uv
CMD ["uv", "run", "src/main.py"]
