# SPDX-FileCopyrightText: 2026 CERN
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the read-replica session routing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from zenodo_rdm.db import routed_bind

ALLOWLISTED_ENDPOINT = "records.read"


@pytest.fixture()
def flask_app():
    """Bare Flask app (no Invenio stack needed for routing logic)."""
    app = Flask(__name__)
    app.config["ZENODO_READ_REPLICA_ENDPOINTS"] = [
        ALLOWLISTED_ENDPOINT,
        "invenio_search_ui.search",
    ]
    return app


@pytest.fixture()
def db_session():
    """Mock SQLAlchemy session with a configured read replica bind."""
    replica_engine = MagicMock(name="replica_engine")
    session = MagicMock(name="session")
    session._db.engines = {"read_replica": replica_engine, None: MagicMock()}
    return session


def _run(flask_app, session, method, endpoint, anonymous):
    """Run routed_bind with a mocked request (no Invenio URL map needed)."""
    user = MagicMock()
    user.is_anonymous = anonymous
    with flask_app.test_request_context("/", method=method):
        with patch("zenodo_rdm.db.request") as mock_request, patch(
            "zenodo_rdm.db.current_user", user
        ):
            mock_request.method = method
            mock_request.endpoint = endpoint
            # bool(request) must be truthy to simulate an active request
            mock_request.__bool__.return_value = True
            return routed_bind(session)


def test_anonymous_get_allowlisted_goes_to_replica(flask_app, db_session):
    """Anonymous GET on an allowlisted endpoint uses the replica."""
    bind = _run(flask_app, db_session, "GET", ALLOWLISTED_ENDPOINT, True)
    assert bind is db_session._db.engines["read_replica"]


def test_anonymous_head_allowlisted_goes_to_replica(flask_app, db_session):
    """Anonymous HEAD on an allowlisted endpoint uses the replica."""
    bind = _run(flask_app, db_session, "HEAD", ALLOWLISTED_ENDPOINT, True)
    assert bind is db_session._db.engines["read_replica"]


def test_non_allowlisted_endpoint_falls_back_to_primary(flask_app, db_session):
    """Anonymous GET on a non-allowlisted endpoint stays on primary."""
    assert (
        _run(flask_app, db_session, "GET", "invenio_communities.members", True)
        is None
    )


def test_authenticated_user_falls_back_to_primary(flask_app, db_session):
    """Authenticated GET on an allowlisted endpoint stays on primary."""
    assert _run(flask_app, db_session, "GET", ALLOWLISTED_ENDPOINT, False) is None


def test_post_falls_back_to_primary(flask_app, db_session):
    """POST on an allowlisted endpoint stays on primary."""
    assert _run(flask_app, db_session, "POST", ALLOWLISTED_ENDPOINT, True) is None


def test_missing_bind_falls_back_to_primary(flask_app):
    """Missing read_replica bind fails open to primary instead of KeyError."""
    session = MagicMock(name="session")
    session._db.engines = {}
    assert _run(flask_app, session, "GET", ALLOWLISTED_ENDPOINT, True) is None


def test_outside_request_context_falls_back_to_primary(flask_app, db_session):
    """CLI/celery usage (no request context) stays on primary without crashing."""
    with flask_app.app_context():
        assert routed_bind(db_session) is None


def test_no_context_at_all_falls_back_to_primary(db_session):
    """No Flask context at all stays on primary without crashing."""
    assert routed_bind(db_session) is None


def test_endpoint_allowlist_has_no_duplicates():
    """Guard against copy-paste duplicates in the invenio.cfg endpoint lists."""
    cfg = (Path(__file__).resolve().parents[2] / "invenio.cfg").read_text()
    for var in ("ZENODO_UI_READ_ONLY_ENDPOINTS", "ZENODO_API_READ_ONLY_ENDPOINTS"):
        block = cfg.split(f"{var} = [", 1)[1].split("]", 1)[0]
        endpoints = [
            line.split('"')[1]
            for line in block.splitlines()
            if line.strip().startswith('"')
        ]
        assert len(endpoints) == len(set(endpoints)), f"duplicates in {var}"


def test_members_endpoint_not_routed():
    """invenio_communities.members must not be in the replica allowlist."""
    cfg = (Path(__file__).resolve().parents[2] / "invenio.cfg").read_text()
    block = cfg.split("ZENODO_READ_REPLICA_ENDPOINTS", 1)[0]
    assert '"invenio_communities.members"' not in block
