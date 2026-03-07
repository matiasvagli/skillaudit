"""Configuración global de SkillAudit vía variables de entorno."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    AI_PROVIDER: str = os.getenv("SKILLAUDIT_AI_PROVIDER", "gemini")
    RISK_THRESHOLD: int = int(os.getenv("SKILLAUDIT_RISK_THRESHOLD", "70"))

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Imagen Docker del sandbox
    SANDBOX_IMAGE: str = "skillaudit-sandbox:latest"
    SANDBOX_TIMEOUT: int = int(os.getenv("SKILLAUDIT_TIMEOUT", "120"))  # segundos

    @classmethod
    def validate(cls) -> None:
        """Valida que la configuración mínima esté presente."""
        provider = cls.AI_PROVIDER
        key_map = {
            "gemini": cls.GEMINI_API_KEY,
            "openai": cls.OPENAI_API_KEY,
            "anthropic": cls.ANTHROPIC_API_KEY,
        }
        if provider not in key_map:
            raise ValueError(
                f"Proveedor de IA desconocido: '{provider}'. "
                "Opciones: gemini, openai, anthropic"
            )
        if not key_map[provider]:
            env_var = f"{provider.upper()}_API_KEY"
            raise ValueError(
                f"Falta la API key para {provider}. "
                f"Definila con: export {env_var}=<tu_key>"
            )


config = Config()
