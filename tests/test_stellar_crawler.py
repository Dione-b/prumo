from __future__ import annotations

import pytest

from app.adapters import stellar_crawler


class _FakeRobots:
    def can_fetch(self, _user_agent: str, _url: str) -> bool:
        return True


class _FakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        json_data: dict[str, object] | None = None,
    ) -> None:
        self.text = text
        self._json_data = json_data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._json_data


def test_stellar_crawler_helper_functions() -> None:
    html = """
        <html>
          <body>
            <main>
              <script>ignored()</script>
              <h1>Accounts</h1>
              <p>Balances and signers.</p>
            </main>
          </body>
        </html>
    """

    extracted_text = stellar_crawler._extract_text_from_html(html)

    assert "ignored" not in extracted_text
    assert "Balances and signers." in extracted_text
    assert stellar_crawler._extract_text_from_html("<html></html>") == ""
    assert (
        stellar_crawler._extract_title_from_html(
            "<html></html>",
            "https://developers.stellar.org/docs/build/apps/example-page",
        )
        == "Example Page"
    )
    assert stellar_crawler._normalize_docs_url(
        "https://developers.stellar.org/docs/page#fragment"
    ) == "https://developers.stellar.org/docs/page"
    assert stellar_crawler._should_skip_github_path("CHANGELOG.md") is True
    assert stellar_crawler._should_skip_github_path("README.md") is False
    assert stellar_crawler._should_skip_github_path("src/index.ts") is True


@pytest.mark.asyncio
async def test_crawl_stellar_docs_collects_internal_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    landing_url = "https://developers.stellar.org/docs"
    account_url = (
        "https://developers.stellar.org/docs/learn/fundamentals/"
        "stellar-data-structures/accounts"
    )

    async def fake_fetch_text(_client: object, url: str) -> str:
        pages = {
            landing_url: """
                <html>
                  <head><title>Stellar Docs</title></head>
                  <body>
                    <a
                      href="/docs/learn/fundamentals/stellar-data-structures/accounts"
                    >
                      Accounts
                    </a>
                    <a href="https://developers.stellar.org/docs/build/apps/example">Apps</a>
                    <a href="https://stellar.org/blog">External</a>
                  </body>
                </html>
            """,
            account_url: """
                <html>
                  <head><title>Accounts</title></head>
                  <body>
                    <main>
                      <h1>Accounts</h1>
                      <p>Accounts store balances and signers.</p>
                    </main>
                  </body>
                </html>
            """,
            "https://developers.stellar.org/docs/build/apps/example": """
                <html>
                  <head><title>Apps</title></head>
                  <body>
                    <article>
                      <p>Build apps on top of Stellar services.</p>
                    </article>
                  </body>
                </html>
            """,
        }
        return pages[url]

    async def fake_load_robot_parser(_client: object) -> _FakeRobots:
        return _FakeRobots()

    monkeypatch.setattr(stellar_crawler, "_fetch_text", fake_fetch_text)
    monkeypatch.setattr(
        stellar_crawler,
        "_load_robot_parser",
        fake_load_robot_parser,
    )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.adapters.stellar_crawler.asyncio.sleep", fake_sleep)

    documents = await stellar_crawler.crawl_stellar_docs()

    assert len(documents) == 3
    assert all(document["source_type"] == "docs" for document in documents)
    assert any("signers" in document["content"] for document in documents)


@pytest.mark.asyncio
async def test_crawl_stellar_github_repos_filters_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            params: dict[str, str] | None = None,
        ) -> _FakeResponse:
            del params
            if url.endswith("/repos/stellar/stellar-core"):
                return _FakeResponse(json_data={"default_branch": "master"})
            if url.endswith("/repos/stellar/x402-stellar"):
                return _FakeResponse(json_data={"default_branch": "main"})
            if url.endswith("/repos/stellar/stellar-docs"):
                return _FakeResponse(json_data={"default_branch": "main"})
            if "/git/trees/" in url:
                return _FakeResponse(
                    json_data={
                        "tree": [
                            {"path": "README.md", "type": "blob"},
                            {"path": "docs/guide.mdx", "type": "blob"},
                            {"path": "CHANGELOG.md", "type": "blob"},
                        ]
                    }
                )
            return _FakeResponse(text="# Guide\n\nUseful Stellar SDK docs.")

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "app.adapters.stellar_crawler.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    monkeypatch.setattr("app.adapters.stellar_crawler.asyncio.sleep", fake_sleep)

    documents = await stellar_crawler.crawl_stellar_github_repos()

    assert documents
    assert all(document["source_type"] == "github" for document in documents)
    assert all("CHANGELOG" not in document["title"] for document in documents)
    assert any(document["title"].endswith("README.md") for document in documents)
