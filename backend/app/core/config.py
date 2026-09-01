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


settings = Settings()
