"""GitHub API crawler implementation."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from prumo.crawlers.base import Crawler
from prumo.models import Page, ProgressCallback

TIMEOUT_SECONDS = 10

GITHUB_MD_EXTENSIONS = (".md", ".mdx")

GITHUB_IGNORED_FILENAMES = frozenset(
    {
        "changelog",
        "changes",
        "release-notes",
        "releases",
        "license",
        "licence",
        "contributing",
        "code-of-conduct",
        "security",
        "crowdin",
        "readme",
    }
)

GITHUB_IGNORED_DIRS = frozenset(
    {
        ".github",
        ".husky",
        ".devcontainer",
        ".vscode",
        "node_modules",
        ".next",
        ".nuxt",
        "dist",
        "build",
        "out",
        ".cache",
        "src",
        "lib",
        "bin",
        "scripts",
        "patches",
        "nginx",
        "docker",
        "k8s",
        "helm",
        "terraform",
        "static",
        "public",
        "assets",
        "images",
        "img",
        "readme-imgs",
        "i18n",
        "locales",
        "openapi",
        "openrpc",
        "meeting-notes",
        "config",
    }
)

DOCS_DIR_CANDIDATES = (
    "docs",
    "documentation",
    "doc",
    "content",
    "pages",
    "guide",
    "guides",
    "wiki",
    "knowledge",
    "manual",
    "handbook",
    "reference",
)


@dataclass
class _GitHubFile:
    name: str
    html_url: str
    content: str
    text_score: int = 0


class GithubCrawler(Crawler):
    """Crawler that reads markdown files via GitHub Contents API."""

    def __init__(self, github_token: str, docs_base_url: str | None = None) -> None:
        self._github_token = github_token
        self._docs_base_url = docs_base_url

    def _parse_github_url(self, url: str) -> tuple[str, str, str]:
        parsed = urlparse(url)
        if parsed.netloc not in ("github.com", "www.github.com"):
            raise ValueError(f"URL is not a GitHub URL: {url}")

        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL (expected owner/repo): {url}")

        owner = parts[0]
        repo = parts[1]
        subpath = "/".join(parts[4:]) if len(parts) > 4 and parts[2] == "tree" else ""
        return owner, repo, subpath

    def _is_ignored_dir(self, name: str) -> bool:
        return name.lower() in GITHUB_IGNORED_DIRS

    def _is_ignored_file(self, filename: str) -> bool:
        stem = filename.lower().removesuffix(".md").removesuffix(".mdx")
        return stem in GITHUB_IGNORED_FILENAMES

    def _decode_base64_content(self, encoded: str) -> str | None:
        try:
            return base64.b64decode(encoded.replace("\n", "")).decode("utf-8")
        except Exception:
            return None

    def _fetch_file_individually(
        self,
        client: httpx.Client,
        api_url: str,
        headers: dict[str, str],
    ) -> str | None:
        try:
            response = client.get(api_url, headers=headers)
            response.raise_for_status()
            encoded = response.json().get("content", "")
            return self._decode_base64_content(encoded) if encoded else None
        except (httpx.HTTPError, httpx.TimeoutException):
            return None

    def _transform_to_docs_url(self, html_url: str, subpath: str, docs_base_url: str) -> str:
        match = re.search(r"/blob/[^/]+/(.+)$", html_url)
        if not match:
            return html_url

        file_path = match.group(1)
        if subpath:
            prefix = subpath.rstrip("/") + "/"
            if file_path.startswith(prefix):
                file_path = file_path[len(prefix) :]

        for extension in (".mdx", ".md"):
            if file_path.endswith(extension):
                file_path = file_path[: -len(extension)]
                break

        return f"{docs_base_url.rstrip('/')}/{file_path}"

    def _detect_docs_subpath(
        self,
        client: httpx.Client,
        owner: str,
        repo: str,
        headers: dict[str, str],
    ) -> str:
        try:
            response = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/",
                headers=headers,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException):
            return ""

        items = response.json()
        if not isinstance(items, list):
            return ""

        dir_names = {item["name"].lower() for item in items if item.get("type") == "dir"}
        return next((candidate for candidate in DOCS_DIR_CANDIDATES if candidate in dir_names), "")

    def _score_markdown_content(self, raw: str) -> int:
        text = re.sub(r"^---[\s\S]*?---\s*", "", raw, count=1)
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"^(import|export)\s+.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"<[A-Z][^>]*/>", "", text)
        text = re.sub(r"<[A-Z][^>]*>[\s\S]*?</[A-Z][^>]*>", "", text)
        text = re.sub(r"!?\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"^[#\-=*_>|` ]+$", "", text, flags=re.MULTILINE)
        return len(text.strip())

    def _extract_title_from_markdown(self, content: str, filename: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped.lstrip("# ").strip()
        return filename.removesuffix(".mdx").removesuffix(".md").replace("-", " ").title()

    def _list_github_files(
        self,
        client: httpx.Client,
        owner: str,
        repo: str,
        path: str,
        headers: dict[str, str],
        max_files: int,
        collected: list[_GitHubFile],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if len(collected) >= max_files:
            return

        try:
            response = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException):
            return

        items = response.json()
        if not isinstance(items, list):
            return

        for item in items:
            if len(collected) >= max_files:
                break

            item_type = item.get("type", "")
            name = item.get("name", "")

            if item_type == "dir":
                if not self._is_ignored_dir(name):
                    self._list_github_files(
                        client,
                        owner,
                        repo,
                        item["path"],
                        headers,
                        max_files,
                        collected,
                        on_progress,
                    )
            elif item_type == "file":
                if not any(name.lower().endswith(extension) for extension in GITHUB_MD_EXTENSIONS):
                    continue
                if self._is_ignored_file(name):
                    continue

                encoded = item.get("content", "")
                decoded = (
                    self._decode_base64_content(encoded)
                    if encoded
                    else self._fetch_file_individually(client, item["url"], headers)
                )
                if not decoded or not decoded.strip():
                    continue

                collected.append(
                    _GitHubFile(
                        name=name,
                        html_url=item.get("html_url", ""),
                        content=decoded,
                        text_score=self._score_markdown_content(decoded),
                    )
                )
                if on_progress:
                    on_progress(len(collected), name)

    def crawl(
        self,
        url: str,
        max_pages: int = 50,
        on_progress: ProgressCallback | None = None,
    ) -> list[Page]:
        try:
            owner, repo, subpath = self._parse_github_url(url)
        except ValueError:
            return []

        headers = {
            "Authorization": f"Bearer {self._github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        collected: list[_GitHubFile] = []
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            if not subpath:
                subpath = self._detect_docs_subpath(client, owner, repo, headers)

            self._list_github_files(
                client,
                owner,
                repo,
                subpath,
                headers,
                max_pages,
                collected,
                on_progress,
            )

        if not collected:
            return []

        collected.sort(key=lambda file: file.text_score, reverse=True)
        return [
            Page(
                title=self._extract_title_from_markdown(file.content, file.name),
                url=self._transform_to_docs_url(file.html_url, subpath, self._docs_base_url)
                if self._docs_base_url
                else file.html_url,
                content=file.content,
            )
            for file in collected
        ]
