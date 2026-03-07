FROM node:20-slim

# Instalar herramientas de monitoring y utilidades
RUN apt-get update && apt-get install -y \
    strace \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo (el package npm se monta aquí como volume ro)
WORKDIR /app

# /tmp es el único lugar donde el MCP server puede escribir
VOLUME ["/tmp"]

# El entrypoint real lo especifica sandbox_runner.py via exec
CMD ["sleep", "infinity"]
