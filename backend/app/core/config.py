import os


class Settings:
    """Minimal foundation configuration settings."""

    APP_NAME: str = "AI Code Reviewer API"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    AUTH_SECRET: str = os.getenv("AUTH_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_TOKEN_ENCRYPTION_KEY: str = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")
    GITHUB_REDIRECT_URI: str = os.getenv("GITHUB_REDIRECT_URI", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    STALE_RECLAMATION_INTERVAL_SECONDS: int = int(os.getenv("STALE_RECLAMATION_INTERVAL_SECONDS", "60"))

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        """Environment-driven CORS allowed origins with local development fallback."""
        raw = os.getenv("ALLOWED_ORIGINS", "")
        defaults = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
        if not raw:
            return defaults
        parsed = [o.strip() for o in raw.split(",") if o.strip()]
        for d in defaults:
            if d not in parsed:
                parsed.append(d)
        return parsed


settings = Settings()
