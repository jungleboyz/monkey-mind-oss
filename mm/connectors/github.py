"""GitHub connector — ingests profile, repos, and contribution patterns."""

import base64
import logging
import time
from typing import Any

import requests

from mm.connectors.base import BaseConnector, ConnectorPage

logger = logging.getLogger(__name__)


class GitHubConnector(BaseConnector):
    connector_id = "github"
    display_name = "GitHub Profile"
    description = (
        "Ingest your GitHub profile, repos, and contribution patterns into your professional context."
    )

    BASE_URL = "https://api.github.com"

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def schema(self) -> dict[str, Any]:
        return {
            "username": {"type": "string", "description": "GitHub username"},
            "github_token": {
                "type": "string",
                "description": "Optional token for higher rate limits",
            },
            "include_repos": {"type": "boolean", "default": True},
            "include_contributions": {"type": "boolean", "default": True},
        }

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(self) -> tuple[bool, str]:
        username = self.config.get("username", "")
        if not username:
            return False, "username is required"
        url = f"{self.BASE_URL}/users/{username}"
        try:
            result = self._get(url)
        except Exception as exc:  # noqa: BLE001
            return False, f"GitHub API unreachable: {exc}"
        if result is None:
            return False, f"GitHub user '{username}' not found (404)"
        return True, "ok"

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest(self, progress_cb=None) -> list[ConnectorPage]:
        pages: list[ConnectorPage] = []
        username = self.config["username"]

        # 1. Profile
        profile_data = self._get(f"{self.BASE_URL}/users/{username}", progress_cb=progress_cb)
        if profile_data:
            pages.append(self._build_profile_page(username, profile_data))

        # 2. Repos
        if self.config.get("include_repos", True):
            repos = self._get(
                f"{self.BASE_URL}/users/{username}/repos?sort=updated&per_page=30",
                progress_cb=progress_cb,
            )
            if repos:
                for repo in repos:
                    page = self._build_repo_page(username, repo, progress_cb=progress_cb)
                    if page:
                        pages.append(page)

        # 3. Contributions
        if self.config.get("include_contributions", True):
            events = self._get(
                f"{self.BASE_URL}/users/{username}/events?per_page=30",
                progress_cb=progress_cb,
            )
            if events is not None:
                pages.append(self._build_contributions_page(username, events))

        return pages

    # ------------------------------------------------------------------
    # Private builders
    # ------------------------------------------------------------------

    def _build_profile_page(self, username: str, data: dict) -> ConnectorPage:
        bio = data.get("bio") or ""
        location = data.get("location") or ""
        company = data.get("company") or ""
        followers = data.get("followers", 0)
        following = data.get("following", 0)
        public_repos = data.get("public_repos", 0)
        name = data.get("name") or username

        summary_parts = [p for p in [bio, location, company] if p]
        summary_parts.append(f"{followers} followers")
        summary = " | ".join(summary_parts)

        profile_text = (
            f"Name: {name}\n"
            f"Username: {username}\n"
            f"Bio: {bio}\n"
            f"Location: {location}\n"
            f"Company: {company}\n"
        )
        stats_text = (
            f"Followers: {followers}\n"
            f"Following: {following}\n"
            f"Public repos: {public_repos}\n"
        )

        return ConnectorPage(
            id=f"github::profile::{username}",
            domain="professional",
            type="github_profile",
            title=f"GitHub Profile: {name} (@{username})",
            summary=summary,
            detail_sections={"Profile": profile_text, "Stats": stats_text},
            source="github",
            source_ref=f"https://github.com/{username}",
            connector=self.connector_id,
        )

    def _build_repo_page(
        self, username: str, repo: dict, progress_cb=None
    ) -> ConnectorPage | None:
        repo_name = repo["name"]
        readme_data = self._get(
            f"{self.BASE_URL}/repos/{username}/{repo_name}/readme",
            progress_cb=progress_cb,
        )
        if readme_data is None:
            logger.warning("No README for %s/%s — skipping", username, repo_name)
            return None

        raw_content = readme_data.get("content", "")
        # GitHub encodes with newlines in the base64 string
        readme_text = base64.b64decode(raw_content.replace("\n", "")).decode("utf-8", errors="replace")

        description = repo.get("description") or ""
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language") or "unknown"
        updated_at = repo.get("updated_at", "")

        summary = f"{description} | ⭐ {stars} | {language} | updated {updated_at[:10]}"

        return ConnectorPage(
            id=f"github::repo::{username}::{repo_name}",
            domain="professional",
            type="github_repo",
            title=f"GitHub Repo: {username}/{repo_name}",
            summary=summary,
            detail_sections={"README": readme_text},
            source="github",
            source_ref=f"https://github.com/{username}/{repo_name}",
            connector=self.connector_id,
        )

    def _build_contributions_page(self, username: str, events: list) -> ConnectorPage:
        push_events = [e for e in events if e.get("type") == "PushEvent"]
        pr_events = [e for e in events if e.get("type") == "PullRequestEvent"]
        issue_events = [e for e in events if e.get("type") == "IssuesEvent"]

        lines = [
            f"Recent activity for @{username} (last {len(events)} events):",
            f"  Push events: {len(push_events)}",
            f"  Pull request events: {len(pr_events)}",
            f"  Issue events: {len(issue_events)}",
        ]

        # List repos touched
        repos_touched = sorted({e["repo"]["name"] for e in events if "repo" in e})
        if repos_touched:
            lines.append("Repos touched: " + ", ".join(repos_touched))

        activity_text = "\n".join(lines)
        summary = (
            f"{len(push_events)} pushes, {len(pr_events)} PRs, {len(issue_events)} issues "
            f"across {len(repos_touched)} repos"
        )

        return ConnectorPage(
            id=f"github::contributions::{username}",
            domain="professional",
            type="github_contributions",
            title=f"GitHub Contributions: @{username}",
            summary=summary,
            detail_sections={"Activity": activity_text},
            source="github",
            source_ref=f"https://github.com/{username}",
            connector=self.connector_id,
        )

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, url: str, max_retries: int = 3, progress_cb=None) -> dict | list | None:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token := self.config.get("github_token"):
            headers["Authorization"] = f"token {token}"

        for attempt in range(max_retries):
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                if progress_cb:
                    progress_cb(0, 0, f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        return None
