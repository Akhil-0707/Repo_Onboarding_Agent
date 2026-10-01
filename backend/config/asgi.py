import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()

if os.environ.get("EMBEDDING_WARMUP", "1") == "1":
    # Chat answers run hybrid search in this process: load the embedding model now, in the
    # background, instead of during the first question (~10 s on CPU).
    from apps.search.warmup import warm_up_embeddings

    warm_up_embeddings()
