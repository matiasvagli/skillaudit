"""Cliente de IA unificado — soporta Gemini, OpenAI y Anthropic."""

from .config import config


def _build_gemini_client():
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-2.0-flash")


def ask_ai(prompt: str) -> str:
    """
    Envía un prompt al LLM configurado y retorna la respuesta como string.
    Único punto de acceso a la IA en todo el proyecto.
    """
    provider = config.AI_PROVIDER

    if provider == "gemini":
        model = _build_gemini_client()
        response = model.generate_content(prompt)
        return response.text

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    else:
        raise ValueError(f"Proveedor de IA desconocido: {provider}")
