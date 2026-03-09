FROM node:20-slim

# Instalar herramientas de monitoring, utilidades y Python
RUN apt-get update && apt-get install -y \
    strace \
    procps \
    curl \
    python3 \
    python3-pip \
     python3-venv \
     && rm -rf /var/lib/apt/lists/*
 
 # Instalar dependencias base de MCP para Python
 RUN pip3 install --no-cache-dir mcp tzdata tzlocal pydantic --break-system-packages
 
 # Directorio de trabajo
WORKDIR /app

# /tmp es el único lugar donde el MCP server puede escribir
VOLUME ["/tmp"]

# El entrypoint real lo especifica sandbox_runner.py via exec
CMD ["sleep", "infinity"]
