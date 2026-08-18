"""Tests for GitHubConnector."""

import base64
import unittest
from unittest.mock import MagicMock, patch

from mm.connectors.github import GitHubConnector


def _make_connector(extra_config=None):
    config = {"username": "testuser", **(extra_config or {})}
    return GitHubConnector(config=config, user_config=None)


def mock_github_responses():
    """Return mock responses for profile, repos, readme, events."""
    profile = {
        "login": "testuser",
        "name": "Test User",
        "bio": "Developer",
        "company": "ACME",
        "location": "Sydney",
        "followers": 100,
        "following": 50,
        "public_repos": 10,
    }
    repos = [
        {
            "name": "my-repo",
            "description": "A great repo",
            "stargazers_count": 42,
            "language": "Python",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    readme = {
        "content": base64.b64encode(b"# My Repo\n\nA great project.").decode()
    }
    events = [
        {
            "type": "PushEvent",
            "repo": {"name": "testuser/my-repo"},
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    return profile, repos, readme, events


def _side_effect_factory(profile, repos, readme, events):
    """Return a _get side-effect function that dispatches by URL."""

    def _get(url, max_retries=3, progress_cb=None):
        if "/repos/" in url and "/readme" in url:
            return readme
        if url.endswith("/repos?sort=updated&per_page=30"):
            return repos
        if url.endswith("/events?per_page=30"):
            return events
        if "/users/" in url:
            return profile
        return None

    return _get


class TestGitHubConnectorIngest(unittest.TestCase):
    def setUp(self):
        self.profile, self.repos, self.readme, self.events = mock_github_responses()
        self.connector = _make_connector()

    _UNSET = object()

    def _patch_get(self, readme=_UNSET, events=_UNSET):
        _readme = self.readme if readme is self._UNSET else readme
        _events = self.events if events is self._UNSET else events
        side_effect = _side_effect_factory(self.profile, self.repos, _readme, _events)
        return patch.object(self.connector, "_get", side_effect=side_effect)

    def test_ingest_produces_profile_page(self):
        with self._patch_get():
            pages = self.connector.ingest()
        profile_pages = [p for p in pages if p.type == "github_profile"]
        self.assertEqual(len(profile_pages), 1)
        self.assertEqual(profile_pages[0].domain, "professional")
        self.assertIn("testuser", profile_pages[0].title)

    def test_ingest_produces_repo_pages(self):
        with self._patch_get():
            pages = self.connector.ingest()
        repo_pages = [p for p in pages if p.type == "github_repo"]
        self.assertEqual(len(repo_pages), 1)
        self.assertIn("my-repo", repo_pages[0].title)
        self.assertEqual(repo_pages[0].domain, "professional")

    def test_ingest_skips_missing_readme(self):
        """When readme returns None the repo is skipped, no exception raised."""
        with self._patch_get(readme=None):
            pages = self.connector.ingest()
        repo_pages = [p for p in pages if p.type == "github_repo"]
        self.assertEqual(len(repo_pages), 0)
        # Other pages still produced
        self.assertTrue(any(p.type == "github_profile" for p in pages))

    def test_ingest_contributions_page(self):
        with self._patch_get():
            pages = self.connector.ingest()
        contrib_pages = [p for p in pages if p.type == "github_contributions"]
        self.assertEqual(len(contrib_pages), 1)
        self.assertEqual(contrib_pages[0].domain, "professional")

    def test_all_pages_professional_domain(self):
        with self._patch_get():
            pages = self.connector.ingest()
        self.assertTrue(len(pages) > 0)
        for page in pages:
            self.assertEqual(page.domain, "professional", f"{page.id} has wrong domain")


class TestGitHubConnectorValidate(unittest.TestCase):
    def test_validate_success(self):
        connector = _make_connector()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"login": "testuser"}
        with patch("requests.get", return_value=mock_resp):
            ok, msg = connector.validate()
        self.assertTrue(ok)
        self.assertEqual(msg, "ok")

    def test_validate_user_not_found(self):
        connector = _make_connector()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.get", return_value=mock_resp):
            ok, msg = connector.validate()
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())


class TestGitHubConnectorRateLimit(unittest.TestCase):
    def test_rate_limit_retry(self):
        """First call returns 403 rate-limited, second returns 200."""
        connector = _make_connector()

        rate_resp = MagicMock()
        rate_resp.status_code = 403
        rate_resp.text = "API rate limit exceeded"

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"login": "testuser"}

        with patch("requests.get", side_effect=[rate_resp, ok_resp]):
            with patch("time.sleep"):  # don't actually sleep in tests
                result = connector._get(f"{connector.BASE_URL}/users/testuser")

        self.assertIsNotNone(result)
        self.assertEqual(result["login"], "testuser")
