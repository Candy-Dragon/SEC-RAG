"""Connection checks must bypass loopback proxies and explain invalid responses."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sec_rag.evaluation.ollama_client import OllamaJudge


class OllamaConnectionTests(unittest.TestCase):
    def response(self, status=200, **kwargs):
        return httpx.Response(status, request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"), **kwargs)

    def test_loopback_bypasses_proxy(self):
        for host in ("127.0.0.1", "localhost", "[::1]"):
            judge = OllamaJudge(base_url=f"http://{host}:11434")
            response = self.response(json={"models": [{"name": judge.model, "digest": "test"}]})
            with patch("sec_rag.evaluation.ollama_client.httpx.get", return_value=response) as get:
                judge.check()
                self.assertIs(get.call_args.kwargs["trust_env"], False)
                self.assertEqual(judge.model_digest, "test")

    def test_html_is_explained(self):
        with patch("sec_rag.evaluation.ollama_client.httpx.get", return_value=self.response(text="<html>proxy</html>")):
            with self.assertRaisesRegex(RuntimeError, "non-JSON"):
                OllamaJudge().check()

    def test_http_error_precedes_json_parsing(self):
        with patch("sec_rag.evaluation.ollama_client.httpx.get", return_value=self.response(502, text="")):
            with self.assertRaisesRegex(RuntimeError, "HTTP 502"):
                OllamaJudge().check()

    def test_timeout_has_startup_guidance(self):
        with patch("sec_rag.evaluation.ollama_client.httpx.get", side_effect=httpx.ReadTimeout("timeout")):
            with self.assertRaisesRegex(RuntimeError, "ollama serve"):
                OllamaJudge().check()

    def test_bad_schema_is_explained(self):
        with patch("sec_rag.evaluation.ollama_client.httpx.get", return_value=self.response(json=[])):
            with self.assertRaisesRegex(RuntimeError, "Invalid Ollama"):
                OllamaJudge().check()
