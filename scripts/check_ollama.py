#!/usr/bin/env python3
"""Ollama Diagnostic Script — validates handshake, models, and PriorityQueue.

Usage:
    uv run python scripts/check_ollama.py

Checks:
    1. API reachability (handshake)
    2. Presence of required models (llama3.2:3b, qwen3-embedding:0.6b)
    3. Concurrent P2 (Chat) + P3 (Embed) through the PriorityQueue worker
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services.ollama_client import (  # noqa: E402
    OllamaClient,
)

REQUIRED_MODELS = {settings.ollama_business_model, settings.ollama_embedding_model}

DIVIDER = "─" * 60


def _header(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


async def check_handshake() -> bool:
    """Step 1: Verify Ollama API is reachable."""
    _header("1. Ollama API Handshake")
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            available = {m["name"] for m in data.get("models", [])}
            print(f"  ✅ Ollama API is reachable at {settings.ollama_base_url}")
            print(f"  📦 Models installed: {sorted(available)}")
            return True
    except httpx.ConnectError:
        print(f"  ❌ UNREACHABLE — Cannot connect to {settings.ollama_base_url}")
        print("     Ensure `ollama serve` is running.")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False


async def check_models() -> bool:
    """Step 2: Verify required models are present."""
    _header("2. Required Models Check")
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
    except Exception as e:
        print(f"  ❌ Failed to fetch model list: {e}")
        return False

    available = {m["name"] for m in data.get("models", [])}
    all_present = True

    for model in sorted(REQUIRED_MODELS):
        if model in available:
            print(f"  ✅ {model} — PRESENT")
        else:
            print(f"  ❌ {model} — MISSING (run: ollama pull {model})")
            all_present = False

    return all_present


async def check_priority_queue() -> bool:
    """Step 3: Fire concurrent P2 (Chat) and P3 (Embed) through the scheduler."""
    _header("3. PriorityQueue Worker Test (P2 Chat + P3 Embed)")

    client = OllamaClient()
    # Start the scheduler workers
    await client._scheduler.start()

    async def run_chat() -> dict[str, object]:
        start = time.monotonic()
        print("  🔵 [P2 Chat] Enqueued...")
        result = await client.chat(
            model=settings.ollama_business_model,
            messages=[{"role": "user", "content": "Reply with only: OK"}],
            think=False,
            options={"num_predict": 5},
        )
        elapsed = time.monotonic() - start
        content = result.get("message", {}).get("content", "").strip()
        print(f"  🔵 [P2 Chat] Response: {content!r} ({elapsed:.2f}s)")
        return {"ok": True, "elapsed": elapsed, "content": content}

    async def run_embed() -> dict[str, object]:
        start = time.monotonic()
        print("  🟠 [P3 Embed] Enqueued...")
        result = await client.embed(
            model=settings.ollama_embedding_model,
            input_texts=["Test embedding for diagnostic."],
        )
        elapsed = time.monotonic() - start
        embeddings = result.get("embeddings", [])
        dim = len(embeddings[0]) if embeddings else 0
        print(f"  🟠 [P3 Embed] Dimension: {dim} ({elapsed:.2f}s)")
        return {"ok": True, "elapsed": elapsed, "dim": dim}

    try:
        chat_result, embed_result = await asyncio.gather(
            run_chat(), run_embed(), return_exceptions=True
        )

        success = True
        if isinstance(chat_result, Exception):
            print(f"  ❌ [P2 Chat] FAILED: {chat_result}")
            success = False
        if isinstance(embed_result, Exception):
            print(f"  ❌ [P3 Embed] FAILED: {embed_result}")
            success = False

        if success:
            print("\n  ✅ PriorityQueue processed both tasks successfully.")
            # Validate aging: P2 should generally complete before P3
            # because P2 has higher priority (lower number)
            if isinstance(chat_result, dict) and isinstance(embed_result, dict):
                chat_t = chat_result["elapsed"]
                embed_t = embed_result["elapsed"]
                if isinstance(chat_t, float) and isinstance(embed_t, float):
                    if chat_t < embed_t:
                        print(
                            f"  📊 Priority ordering confirmed: "
                            f"P2 ({chat_t:.2f}s) < P3 ({embed_t:.2f}s)"
                        )
                    else:
                        print(
                            f"  ⚠️  P3 finished before P2"
                            f" (P2={chat_t:.2f}s,"
                            f" P3={embed_t:.2f}s)."
                            f" Acceptable with"
                            f" concurrent workers."
                        )
        return success
    except Exception as e:
        print(f"  ❌ PriorityQueue test failed: {e}")
        return False


async def check_db_counts() -> None:
    """Step 4: Show database persistence counts."""
    _header("4. Database Persistence Check")
    try:
        from sqlalchemy import text

        from app.database import async_session_factory

        async with async_session_factory() as session:
            tables = [
                "projects",
                "knowledge_documents",
                "graph_nodes",
                "graph_edges",
                "business_rules",
                "generated_prompts",
            ]
            for table in tables:
                result = await session.execute(text(f"SELECT count(*) FROM {table}"))
                count = result.scalar_one()
                icon = "✅" if count > 0 else "⚪"
                print(f"  {icon} {table}: {count} rows")
    except Exception as e:
        print(f"  ❌ Database check failed: {e}")


async def main() -> None:
    print("\n🔍 Prumo — Ollama & Persistence Diagnostic")
    print("=" * 60)

    handshake_ok = await check_handshake()
    if not handshake_ok:
        print("\n🛑 Aborting: Ollama API is unreachable.")
        sys.exit(1)

    models_ok = await check_models()
    if not models_ok:
        print("\n⚠️  Some required models are missing. Queue test may fail.")

    queue_ok = await check_priority_queue()

    await check_db_counts()

    _header("Summary")
    results = {
        "Handshake": handshake_ok,
        "Models": models_ok,
        "PriorityQueue": queue_ok,
    }
    for name, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")

    if all(results.values()):
        print("\n🎉 All checks passed!")
    else:
        print("\n⚠️  Some checks failed. Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
