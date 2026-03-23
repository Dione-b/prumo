"""Crawler for documentation sites.

Two operating modes:
- crawl()        → Static HTTP (httpx + BeautifulSoup), for sites that serve plain HTML.
- crawl_github() → GitHub Contents API, for repositories with docs in .md / .mdx.
                   Bypasses the JS-Wall of sites like Docusaurus, VitePress, Next.js.

GitHub mode intelligence:
- Automatically ignores configuration/infrastructure directories.
- Auto-detects the docs directory when the user provides only the repo root URL.
- Prioritizes files with more actual text content before sending them to the exporter.
- Automatic fallback to individual file fetch when the `content` field is empty
  in the directory listing (normal GitHub API behavior for large directories).
- Transforms GitHub URLs to the published docs URL when --docs-base-url is provided.

Both modes return List[Page] — identical interface for the exporter.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


TIMEOUT_SECONDS = 10
MAX_RETRIES = 2
REMOVABLE_TAGS = ("nav", "footer", "aside", "script", "style", "header")

GITHUB_MD_EXTENSIONS = (".md", ".mdx")

GITHUB_IGNORED_FILENAMES = frozenset({
    "changelog", "changes", "release-notes", "releases",
    "license", "licence", "contributing", "code-of-conduct",
    "security", "crowdin", "readme",
})

GITHUB_IGNORED_DIRS = frozenset({
    ".github", ".husky", ".devcontainer", ".vscode",
    "node_modules", ".next", ".nuxt", "dist", "build", "out", ".cache",
    "src", "lib", "bin", "scripts", "patches",
    "nginx", "docker", "k8s", "helm", "terraform",
    "static", "public", "assets", "images", "img", "readme-imgs",
    "i18n", "locales",
    "openapi", "openrpc",
    "meeting-notes", "config",
})

DOCS_DIR_CANDIDATES = (
    "docs", "documentation", "doc", "content",
    "pages", "guide", "guides", "wiki",
    "knowledge", "manual", "handbook", "reference",
)

ProgressCallback = Callable[[int, str], None]


@dataclass
class Page:
    """A documentation page with cleaned content."""

    title: str
    url: str
    content: str


# ---------------------------------------------------------------------------
# HTTP mode — static crawling
# ---------------------------------------------------------------------------


def _is_same_docs_scope(candidate: str, root: str) -> bool:
    parsed_candidate = urlparse(candidate)
    parsed_root = urlparse(root)
    if parsed_candidate.netloc != parsed_root.netloc:
        return False
    return parsed_candidate.path.startswith(parsed_root.path)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.scheme in ("http", "https"):
            links.append(clean_url)
    return links


def _clean_html(soup: BeautifulSoup) -> str:
    for tag_name in REMOVABLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    main = soup.find("main")
    container = main if main else soup.find("body")
    if container is None:
        return soup.get_text(separator="\n", strip=True)
    return container.get_text(separator="\n", strip=True)


def _extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    h1_tag = soup.find("h1")
    if h1_tag and h1_tag.get_text(strip=True):
        return h1_tag.get_text(strip=True)
    return "Untitled"


def _fetch_page(client: httpx.Client, url: str) -> str | None:
    """GET with retries. Returns HTML or None on failure."""
    for _ in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, httpx.TimeoutException):
            pass
    return None


def crawl(
    root_url: str,
    max_pages: int = 50,
    on_progress: ProgressCallback | None = None,
) -> list[Page]:
    """Crawl a static documentation site starting from the root URL.

    Args:
        root_url: Root URL of the documentation site.
        max_pages: Maximum number of pages to crawl.
        on_progress: Optional callback invoked after each page: (total, page_title).

    Returns:
        List of pages with title, URL, and cleaned content.
    """
    visited: set[str] = set()
    pages: list[Page] = []
    queue: list[str] = [root_url]

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            html = _fetch_page(client, url)
            if html is None:
                continue

            soup = BeautifulSoup(html, "html.parser")
            for link in _extract_links(soup, url):
                if link not in visited and _is_same_docs_scope(link, root_url):
                    queue.append(link)

            title = _extract_title(soup)
            content = _clean_html(soup)

            if not content.strip():
                continue

            pages.append(Page(title=title, url=url, content=content))
            if on_progress:
                on_progress(len(pages), title)

    return pages


# ---------------------------------------------------------------------------
# GitHub mode — reading via Contents API
# ---------------------------------------------------------------------------


def _parse_github_url(url: str) -> tuple[str, str, str]:
    """Extracts owner, repo, and subpath from a GitHub URL."""
    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"URL is not a GitHub URL: {url}")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL (expected owner/repo): {url}")

    owner = parts[0]
    repo = parts[1]
    subpath = "/".join(parts[4:]) if len(parts) > 4 and parts[2] == "tree" else ""

    return owner, repo, subpath


def _is_ignored_dir(name: str) -> bool:
    return name.lower() in GITHUB_IGNORED_DIRS


def _is_ignored_file(filename: str) -> bool:
    stem = filename.lower().removesuffix(".md").removesuffix(".mdx")
    return stem in GITHUB_IGNORED_FILENAMES


def _decode_base64_content(encoded: str) -> str | None:
    """Decodes a base64 string returned by the GitHub API."""
    try:
        return base64.b64decode(encoded.replace("\n", "")).decode("utf-8")
    except Exception:
        return None


def _fetch_file_individually(
    client: httpx.Client,
    api_url: str,
    headers: dict[str, str],
) -> str | None:
    """Fetch a file individually when content is missing from the directory listing.

    The GitHub Contents API omits the `content` field when the directory response
    would be too large. In that case, we make a direct request to the file endpoint.
    """
    try:
        response = client.get(api_url, headers=headers)
        response.raise_for_status()
        encoded = response.json().get("content", "")
        return _decode_base64_content(encoded) if encoded else None
    except (httpx.HTTPError, httpx.TimeoutException):
        return None


def _transform_to_docs_url(html_url: str, subpath: str, docs_base_url: str) -> str:
    """Transforms a GitHub blob URL to the published documentation URL.

    Example:
        html_url:      https://github.com/stellar/stellar-docs/blob/main/docs/build/setup.mdx
        subpath:       docs
        docs_base_url: https://developers.stellar.org/docs
        result:        https://developers.stellar.org/docs/build/setup
    """
    match = re.search(r"/blob/[^/]+/(.+)$", html_url)
    if not match:
        return html_url

    file_path = match.group(1)

    if subpath:
        prefix = subpath.rstrip("/") + "/"
        if file_path.startswith(prefix):
            file_path = file_path[len(prefix):]

    for ext in (".mdx", ".md"):
        if file_path.endswith(ext):
            file_path = file_path[: -len(ext)]
            break

    return f"{docs_base_url.rstrip('/')}/{file_path}"


def _detect_docs_subpath(
    client: httpx.Client,
    owner: str,
    repo: str,
    headers: dict[str, str],
) -> str:
    """Inspects the top level of the repo and auto-detects the docs directory."""
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
    return next((c for c in DOCS_DIR_CANDIDATES if c in dir_names), "")


def _score_markdown_content(raw: str) -> int:
    """Calculates the volume of actual narrative text in a Markdown file.

    Strips frontmatter, code blocks, MDX imports, and JSX components to
    return a character count of meaningful prose. Higher score = richer content.
    """
    text = re.sub(r"^---[\s\S]*?---\s*", "", raw, count=1)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^(import|export)\s+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"<[A-Z][^>]*/>", "", text)
    text = re.sub(r"<[A-Z][^>]*>[\s\S]*?</[A-Z][^>]*>", "", text)
    text = re.sub(r"!?\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"^[#\-=*_>|` ]+$", "", text, flags=re.MULTILINE)
    return len(text.strip())


def _extract_title_from_markdown(content: str, filename: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return filename.removesuffix(".mdx").removesuffix(".md").replace("-", " ").title()


@dataclass
class _GitHubFile:
    name: str
    html_url: str
    content: str
    text_score: int = 0


def _list_github_files(
    client: httpx.Client,
    owner: str,
    repo: str,
    path: str,
    headers: dict[str, str],
    max_files: int,
    collected: list[_GitHubFile],
    on_progress: ProgressCallback | None = None,
) -> None:
    """Recursively lists .md/.mdx files and collects their content.

    Collection strategy (in order of preference):
    1. Decode the base64 `content` field inline from the directory listing.
    2. If `content` is empty, fetch the file individually via `item["url"]`.
    """
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
        name: str = item.get("name", "")

        if item_type == "dir":
            if not _is_ignored_dir(name):
                _list_github_files(
                    client, owner, repo, item["path"],
                    headers, max_files, collected, on_progress,
                )

        elif item_type == "file":
            if not any(name.lower().endswith(ext) for ext in GITHUB_MD_EXTENSIONS):
                continue
            if _is_ignored_file(name):
                continue

            encoded: str = item.get("content", "")
            decoded = (
                _decode_base64_content(encoded)
                if encoded
                else _fetch_file_individually(client, item["url"], headers)
            )

            if not decoded or not decoded.strip():
                continue

            collected.append(_GitHubFile(
                name=name,
                html_url=item.get("html_url", ""),
                content=decoded,
                text_score=_score_markdown_content(decoded),
            ))

            if on_progress:
                on_progress(len(collected), name)


def crawl_github(
    repo_url: str,
    github_token: str,
    max_pages: int = 50,
    docs_base_url: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[Page]:
    """Read .md/.mdx files from a GitHub repository via the Contents API.

    Args:
        repo_url: URL of the repo or a subdirectory within it.
        github_token: GitHub Personal Access Token.
        max_pages: Maximum number of files to process.
        docs_base_url: Base URL of the published documentation (optional).
                       When provided, links in llms.txt will point to the published
                       docs instead of the GitHub source.
                       Example: "https://developers.stellar.org/docs"
        on_progress: Callback (total_collected, file_name).

    Returns:
        List of pages sorted by actual text content volume (descending).
    """
    try:
        owner, repo, subpath = _parse_github_url(repo_url)
    except ValueError:
        return []

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    collected: list[_GitHubFile] = []

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        if not subpath:
            subpath = _detect_docs_subpath(client, owner, repo, headers)

        _list_github_files(
            client, owner, repo, subpath,
            headers, max_pages, collected, on_progress,
        )

    if not collected:
        return []

    collected.sort(key=lambda f: f.text_score, reverse=True)

    return [
        Page(
            title=_extract_title_from_markdown(file.content, file.name),
            url=_transform_to_docs_url(file.html_url, subpath, docs_base_url)
            if docs_base_url
            else file.html_url,
            content=file.content,
        )
        for file in collected
    ]