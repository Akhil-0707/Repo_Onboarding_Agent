"""Raw PyMongo access for high-volume collections (chunks, blobs, edges, logs).

The client is shared with django-mongodb-backend's connection so there is a single
connection pool and a single source of configuration.
"""

from __future__ import annotations

from django.db import connections
from pymongo.database import Database


def get_db(alias: str = "default") -> Database:
    return connections[alias].get_database()
