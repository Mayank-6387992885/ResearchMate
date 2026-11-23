import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

import summarizer


class FakeOllamaResponse:
    encoding = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        return [
            json.dumps({"response": "A concise "}),
            json.dumps({"response": "summary.", "done": True}),
        ]


class SummarizerTests(unittest.TestCase):
    def test_call_ollama_streams_plain_text(self):
        with patch.object(summarizer.requests, "post", return_value=FakeOllamaResponse()) as post:
            result = summarizer.call_ollama("paper section")

        self.assertEqual(result, "A concise summary.")
        payload = post.call_args.kwargs["json"]
        self.assertTrue(payload["stream"])
        self.assertNotIn("format", payload)

    def test_stream_reports_heartbeats_during_generation(self):
        class SlowResponse(FakeOllamaResponse):
            def iter_lines(self, decode_unicode=False):
                time.sleep(0.04)
                yield from super().iter_lines(decode_unicode)

        heartbeats = []
        with (
            patch.object(summarizer, "PROGRESS_HEARTBEAT_SECONDS", 0.005),
            patch.object(summarizer.requests, "post", return_value=SlowResponse()),
        ):
            result = summarizer.stream_ollama(
                "paper section",
                json_format=False,
                heartbeat_callback=lambda: heartbeats.append(True),
            )

        self.assertEqual(result, "A concise summary.")
        self.assertTrue(heartbeats)

    def test_retry_reuses_completed_chunk_cache(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            progress_updates = []
            responses = iter([
                "first section",
                requests.exceptions.Timeout(),
                "second section",
                "final summary",
            ])

            def generate_section(*_args, **kwargs):
                response = next(responses)
                heartbeat = kwargs.get("heartbeat_callback")
                if heartbeat is not None:
                    heartbeat()
                if isinstance(response, Exception):
                    raise response
                return response

            with (
                patch.object(summarizer, "CACHE_DIR", Path(cache_dir)),
                patch.object(summarizer, "split_text", return_value=["abcde", "fghij"]),
                patch.object(summarizer, "stream_ollama", side_effect=generate_section) as stream,
            ):
                with self.assertRaisesRegex(RuntimeError, "Completed chunks were saved"):
                    summarizer.summarize_paper(
                        "abcdefghij",
                        lambda *update: progress_updates.append(update),
                    )

                result = summarizer.summarize_paper(
                    "abcdefghij",
                    lambda *update: progress_updates.append(update),
                )

        self.assertEqual(result, "final summary")
        self.assertEqual(stream.call_count, 4)
        self.assertIn("fghij", stream.call_args_list[2].args[0])
        self.assertTrue(any(update[2] and update[2]["chunks_completed"] == 1
                            for update in progress_updates))
        self.assertTrue(any("AI is analyzing section" in update[1]
                            for update in progress_updates))

    def test_provider_selection_hierarchy(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(summarizer.get_active_provider(), "ollama")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}, clear=True):
            self.assertEqual(summarizer.get_active_provider(), "gemini")

        with patch.dict("os.environ", {"GROQ_API_KEY": "fake_key"}, clear=True):
            self.assertEqual(summarizer.get_active_provider(), "groq")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "k1", "GROQ_API_KEY": "k2", "AI_PROVIDER": "groq"}, clear=True):
            self.assertEqual(summarizer.get_active_provider(), "groq")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "k1", "AI_PROVIDER": "ollama"}, clear=True):
            self.assertEqual(summarizer.get_active_provider(), "ollama")

    def test_gemini_streaming_parses_sse(self):
        class FakeGeminiResponse:
            ok = True
            status_code = 200
            encoding = None
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def iter_lines(self, decode_unicode=False):
                return [
                    'data: {"candidates": [{"content": {"parts": [{"text": "Gemini "}]}}]}',
                    'data: {"candidates": [{"content": {"parts": [{"text": "summary."}]}}]}',
                ]

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test_gemini_key"}),
            patch.object(summarizer.requests, "post", return_value=FakeGeminiResponse()) as post_mock,
        ):
            result = summarizer.stream_ollama("test paper section")
            self.assertEqual(result, "Gemini summary.")
            self.assertIn("generativelanguage.googleapis.com", post_mock.call_args.args[0])

    def test_groq_streaming_parses_sse(self):
        class FakeGroqResponse:
            ok = True
            status_code = 200
            encoding = None
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def iter_lines(self, decode_unicode=False):
                return [
                    'data: {"choices": [{"delta": {"content": "Groq "}}]}',
                    'data: {"choices": [{"delta": {"content": "summary."}}]}',
                    'data: [DONE]',
                ]

        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "test_groq_key"}),
            patch.object(summarizer.requests, "post", return_value=FakeGroqResponse()) as post_mock,
        ):
            result = summarizer.stream_ollama("test paper section")
            self.assertEqual(result, "Groq summary.")
            self.assertIn("api.groq.com", post_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
