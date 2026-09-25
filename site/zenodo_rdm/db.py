# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# ZenodoRDM is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Database helpers."""

import logging

from flask import current_app, request
from flask_login import current_user

logger = logging.getLogger(__name__)

READ_REPLICA_BIND_KEY = "read_replica"


def routed_bind(session, *args, **kwargs):
    """Route session to the appropriate database depending on the request context.

    Routes unauthenticated/anonymous GET and HEAD requests of configured endpoints to
    the configured read replica SQLAlchemy bind.

    Falls back to the primary database (by returning ``None``) when outside a
    request/app context, for non-read HTTP methods, for authenticated users, for
    endpoints not listed in ``ZENODO_READ_REPLICA_ENDPOINTS``, or when the read
    replica bind is not configured.
    """
    if not request:
        return None
    if request.method not in ["GET", "HEAD"]:
        return None
    if not current_app:
        return None
    read_endpoints = current_app.config.get("ZENODO_READ_REPLICA_ENDPOINTS", [])
    if request.endpoint not in read_endpoints:
        return None
    if not current_user.is_anonymous:
        return None
    engines = session._db.engines
    if READ_REPLICA_BIND_KEY not in engines:
        logger.warning(
            "Read replica bind %r is not configured, falling back to primary.",
            READ_REPLICA_BIND_KEY,
        )
        return None
    return engines[READ_REPLICA_BIND_KEY]
