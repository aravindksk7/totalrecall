from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel


class RagChunk(ContractModel):
    chunk_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    chunk_text: str = Field(min_length=1)
    similarity: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChunkIngestRequest(ContractModel):
    tenant_id: str = ""
    source_ref: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    chunk_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
