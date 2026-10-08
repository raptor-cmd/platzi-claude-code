from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Platziflix"
    version: str = "0.1.0"
    database_url: str = "postgresql://user:password@localhost:5432/platziflix"
    # Secreto para validar los JWT. Vacío = fail closed (se rechazan todos los tokens).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
