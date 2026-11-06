"""Beginner-friendly research paper summarization with resumable chunk caching."""

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b"
CHUNK_SIZE = 4000
REQUEST_TIMEOUT = (10, 600)  # connect timeout, read timeout in seconds
PROGRESS_HEARTBEAT_SECONDS = 15
CACHE_DIR = Path(tempfile.gettempdir()) / "researchmate_summary_cache"

ProgressCallback = Callable[[int, str, dict[str, Any] | None], None] | None


def call_ollama(prompt: str, max_tokens: int = 200) -> str:
    """Send one prompt to Ollama and return its response text."""
    return stream_ollama(prompt, max_tokens, json_format=False)


def stream_ollama(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = True,
    heartbeat_callback: Callable[[], None] | None = None,
) -> str:
    """Generate a response while exposing each newly received text segment."""
    response_text = []
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []

    def report_heartbeat() -> None:
        while not heartbeat_stop.wait(PROGRESS_HEARTBEAT_SECONDS):
            try:
                heartbeat_callback()
            except Exception as exc:
                heartbeat_errors.append(exc)
                return

    heartbeat_thread = None
    if heartbeat_callback is not None:
        heartbeat_thread = threading.Thread(target=report_heartbeat, daemon=True)
        heartbeat_thread.start()

    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
                "num_predict": max_tokens,
            },
        }
        if json_format:
            payload["format"] = "json"

        with requests.post(
            OLLAMA_URL,
            json=payload,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            response.encoding = "utf-8"
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    update = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Ollama returned an invalid streaming response."
                    ) from exc
                if update.get("error"):
                    raise RuntimeError(f"Ollama generation failed: {update['error']}")
                text = update.get("response", "")
                if text:
                    response_text.append(text)
                    if progress_callback is not None:
                        progress_callback("".join(response_text))
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()

    if heartbeat_errors:
        raise heartbeat_errors[0]

    generated_text = "".join(response_text).strip()
    if not generated_text:
        raise RuntimeError("Ollama returned an empty response.")
    return generated_text


def split_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split extracted paper text into manageable chunks."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def _cache_path(paper_text: str) -> Path:
    """Return a stable cache filename for this exact paper and configuration."""
    cache_key = f"{MODEL_NAME}|{CHUNK_SIZE}|{paper_text}"
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _save_cache(path: Path, data: dict) -> None:
    """Write cache data atomically so interrupted writes do not corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def summarize_paper(
    paper_text: str,
    progress_callback: ProgressCallback = None,
) -> str:
    """Summarize a paper and resume completed chunks from the local cache.

    Progress allocation:
      0-5%: upload handled by main.py
      5-15%: PDF text extraction handled by main.py
      15-85%: chunk summaries
      90%: final summary generation started
      92%: final summary successfully generated
    """

    def report(
        progress: int,
        message: str,
        partial_result: dict[str, Any] | None = None,
    ) -> None:
        if progress_callback is not None:
            progress_callback(progress, message, partial_result)

    if not paper_text.strip():
        raise ValueError("No paper text was provided.")

    start_time = time.time()
    chunks = split_text(paper_text)
    if not chunks:
        raise ValueError("No text chunks were created from the paper.")

    cache_path = _cache_path(paper_text)

    try:
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            cache = {"chunk_summaries": {}, "final_summary": None}
    except (OSError, json.JSONDecodeError):
        cache = {"chunk_summaries": {}, "final_summary": None}

    # Reuse the final result if this exact paper was already summarized.
    if cache.get("final_summary"):
        print("[AI] Reusing cached final summary.", flush=True)
        report(92, "Summary loaded. Preparing paper classification...")
        return cache["final_summary"]

    total_chunks = len(chunks)
    print(f"[AI] Paper split into {total_chunks} chunks.", flush=True)
    chunk_summaries: list[str] = []

    try:
        for index, chunk in enumerate(chunks, start=1):
            cache_key = str(index)
            cached_summary = cache.get("chunk_summaries", {}).get(cache_key)

            if cached_summary:
                print(
                    f"[AI] Reusing cached chunk {index}/{total_chunks}.",
                    flush=True,
                )
                chunk_summaries.append(cached_summary)

            else:
                chunk_start = time.monotonic()
                print(
                    f"[AI] Summarizing chunk {index}/{total_chunks}...",
                    flush=True,
                )

                prompt = f"""You are ResearchMate, a research paper assistant.

Summarize this paper section in simple English. Keep only important methods,
facts, findings, and limitations. Do not invent information. This is only one
section of the paper. Return 3 to 5 concise bullet points.

PAPER SECTION:
{chunk}
"""

                partial_result = {
                    "partial_summary": "\n\n".join(chunk_summaries),
                    "chunks_completed": index - 1,
                    "total_chunks": total_chunks,
                }

                def report_chunk_heartbeat() -> None:
                    elapsed = int(time.monotonic() - chunk_start)
                    report(
                        15 + int(((index - 1) / total_chunks) * 70),
                        f"AI is analyzing section {index}/{total_chunks} "
                        f"({elapsed}s elapsed)...",
                        partial_result,
                    )

                report(
                    15 + int(((index - 1) / total_chunks) * 70),
                    f"AI is preparing section {index}/{total_chunks}...",
                    partial_result,
                )
                chunk_summary = stream_ollama(
                    prompt,
                    max_tokens=200,
                    json_format=False,
                    heartbeat_callback=report_chunk_heartbeat,
                )
                chunk_summaries.append(chunk_summary)

                cache.setdefault("chunk_summaries", {})[cache_key] = chunk_summary
                _save_cache(cache_path, cache)

                print(
                    f"[AI] Chunk {index} completed in "
                    f"{time.monotonic() - chunk_start:.1f} seconds.",
                    flush=True,
                )

            # Cached and newly generated chunks both count as completed.
            progress = 15 + int((index / total_chunks) * 70)
            report(
                progress,
                f"Processing chunk {index}/{total_chunks}",
                {
                    "partial_summary": "\n\n".join(chunk_summaries),
                    "chunks_completed": index,
                    "total_chunks": total_chunks,
                },
            )

        report(
            90,
            "Creating the final summary...",
            {
                "partial_summary": "\n\n".join(chunk_summaries),
                "chunks_completed": total_chunks,
                "total_chunks": total_chunks,
            },
        )
        print("[AI] Creating the final summary...", flush=True)

        combined_text = "\n\n".join(chunk_summaries)
        final_start = time.monotonic()

        def report_final_heartbeat() -> None:
            elapsed = int(time.monotonic() - final_start)
            report(
                90,
                f"AI is creating the final summary ({elapsed}s elapsed)...",
                {
                    "partial_summary": combined_text,
                    "chunks_completed": total_chunks,
                    "total_chunks": total_chunks,
                },
            )

        final_prompt = f"""You are ResearchMate, an AI research paper assistant.

Explain this research paper to a beginner using simple English.
Use these sections:
1. Paper Overview
2. Problem Being Solved
3. Methodology
4. Key Findings
5. Limitations
6. Important Technical Terms
7. Final Takeaway

Use clear headings and bullet points. Explain technical terms in plain English.
Do not invent facts, statistics, or findings. If information is missing, state
that clearly. Combine repeated information.

SECTION SUMMARIES:
{combined_text}

Write one clear, well-organized final summary.
"""
        final_summary = stream_ollama(
            final_prompt,
            max_tokens=700,
            json_format=False,
            heartbeat_callback=report_final_heartbeat,
        )

        cache["final_summary"] = final_summary
        _save_cache(cache_path, cache)

        print(
            f"[AI] Total processing time: {time.time() - start_time:.1f} seconds.",
            flush=True,
        )
        report(92, "Summary completed. Preparing paper classification...")
        return final_summary

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Cannot connect to Ollama. Ensure Ollama is running at localhost:11434."
        ) from exc

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Ollama timed out. Completed chunks were saved; "
            "retry the same PDF to resume."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
