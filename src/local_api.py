#!/usr/bin/env python3
"""API-call code for the two local OpenAI-compatible servers."""

from future import annotations

import asyncio
import os

import httpx
from openai import AsyncOpenAI

OSS_MODEL = "gpt-oss-120b"
OSS_HOST = "https://text-sum-gpt-oss-120b-runai-text-sum.runai-inference.cyberspace.vn"
QWEN_MODEL = "Qwen3-14B-Instruct"
QWEN_HOST = "https://text-sum-qwen14b-runai-text-sum.runai-inference.cyberspace.vn"

TEMPERATURE = 0.0
TOP_P = 0.9
MAX_TOKENS = 4096
REQUEST_TIMEOUT = 180.0


def make_vllm_client(host: str, api_key: str) -> AsyncOpenAI:
    """Create a client compatible with the internal vLLM endpoints."""
    return AsyncOpenAI(
        api_key=api_key,
        base_url=f"{host.rstrip('/')}/v1",
        http_client=httpx.AsyncClient(verify=False),
        timeout=REQUEST_TIMEOUT,
    )


async def call_model(
    client: AsyncOpenAI,
    model: str,
    system_message: str,
    user_message: str,
    retries: int = 3,
) -> str:
    """Call one local model with a small retry loop."""
    last_error = None
    for attempt in range(retries):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_tokens=MAX_TOKENS,
            )
            return response.choices[0].message.content or ""
        except Exception as error:
            last_error = error
            if attempt + 1 < retries:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"{model} failed after {retries} attempts: {last_error}")


async def main() -> None:
    oss_client = make_vllm_client(OSS_HOST, os.getenv("OSS_API_KEY", "EMPTY"))
    qwen_client = make_vllm_client(QWEN_HOST, os.getenv("QWEN_API_KEY", "EMPTY"))

    oss_reply = await call_model(
        oss_client,
        OSS_MODEL,
        "You are a helpful assistant.",
        "Hello",
    )
    print(oss_reply)

    qwen_reply = await call_model(
        qwen_client,
        QWEN_MODEL,
        "You are a helpful assistant.",
        "Hello",
    )
    print(qwen_reply)


if name == "main":
    asyncio.run(main())