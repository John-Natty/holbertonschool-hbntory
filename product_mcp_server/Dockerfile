FROM python:3.12-slim

# Évite la création de fichiers .pyc et affiche les logs immédiatement.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Installe uv pour gérer rapidement les dépendances Python.
RUN python -m pip install --no-cache-dir uv

# Copie d'abord les dépendances afin de profiter du cache Docker.
COPY requirements.txt .

# Installe les dépendances directement dans Python du conteneur.
RUN uv pip install \
    --system \
    --no-cache \
    -r requirements.txt

# Copie le code du serveur MCP.
COPY . .

EXPOSE 8000

CMD ["python", "server.py"]
