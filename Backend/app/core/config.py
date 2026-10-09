from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Platziflix"
    version: str = "0.1.0"
    database_url: str = "postgresql://user:password@localhost:5432/platziflix"
    # Secreto para validar los JWT. Vacío = fail closed (se rechazan todos los tokens).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Sesiones anónimas: vida del token y máximo de tokens por IP y minuto
    anonymous_token_ttl_seconds: int = 24 * 3600
    anonymous_tokens_per_minute: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
