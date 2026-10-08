"""Model Step 01: make one minimal DeepSeek connectivity request.

No API key is printed or written. This check uses a very short prompt and
prints the returned model, token usage, latency, and response text.

RUN:
  python scripts/model/01_check_deepseek.py
"""

from __future__ import annotations

import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_rag.llm.deepseek_client import DeepSeekClient  # noqa: E402
from sec_rag.llm.types import ChatMessage  # noqa: E402


def main() -> int:
    print("Model - 01 check DeepSeek connectivity")
    print("=" * 45)
    client = DeepSeekClient()
    response = client.chat(
        [
            ChatMessage(role="system", content="请简洁回答。"),
            ChatMessage(role="user", content="只回复：连接成功"),
        ],
        max_tokens=20,
    )
    print(f"Requested model: {response.requested_model}")
    print(f"Returned model:  {response.returned_model}")
    print(f"Request ID set:  {bool(response.request_id)}")
    print(f"Finish reason:   {response.finish_reason}")
    print(f"Attempts:        {response.attempt_count}")
    print(f"Latency:         {response.latency_seconds}s")
    print(f"Token usage:     {response.usage.total_tokens}")
    print(f"Response:        {response.content}")
    if not response.content.strip():
        print("Connectivity failed: empty model response.")
        return 1
    print("\nModel 01 DeepSeek connectivity: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
