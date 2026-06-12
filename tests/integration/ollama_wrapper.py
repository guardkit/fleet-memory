#!/usr/bin/env python3
"""Simple OpenAI-compatible wrapper for Ollama embeddings.

Provides /v1/embeddings endpoint that translates to Ollama's /api/embeddings format.
Runs on port 9000 to match FLEET_MEMORY_EMBED_URL expectations.
"""

from __future__ import annotations

import asyncio

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request."""

    model: str
    input: list[str] | str


class EmbeddingResponse(BaseModel):
    """OpenAI-compatible embedding response."""

    object: str = "list"
    data: list[dict]
    model: str
    usage: dict


@app.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """Translate OpenAI-style request to Ollama format."""
    # Normalize input to list
    texts = [request.input] if isinstance(request.input, str) else request.input

    # Call Ollama for each text (Ollama's API takes one prompt at a time)
    embeddings_data = []
    async with httpx.AsyncClient() as client:
        for idx, text in enumerate(texts):
            ollama_request = {
                "model": "nomic-embed-text",  # Use Ollama model name
                "prompt": text,
            }
            try:
                response = await client.post(
                    "http://localhost:11434/api/embeddings",
                    json=ollama_request,
                    timeout=30.0,
                )
                response.raise_for_status()
                ollama_data = response.json()

                # Ollama returns {"embedding": [float, ...]}
                if "embedding" not in ollama_data:
                    raise HTTPException(
                        status_code=500,
                        detail="Ollama response missing embedding field",
                    )

                embeddings_data.append(
                    {
                        "object": "embedding",
                        "embedding": ollama_data["embedding"],
                        "index": idx,
                    }
                )
            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Ollama request failed: {e}",
                ) from e

    return EmbeddingResponse(
        data=embeddings_data,
        model=request.model,
        usage={
            "prompt_tokens": sum(len(t.split()) for t in texts),
            "total_tokens": sum(len(t.split()) for t in texts),
        },
    )


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "ollama-wrapper"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="warning")
