from __future__ import annotations

from fastapi import APIRouter, Query

from ..mock_data import search_catalog
from ..schemas import SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/classic", response_model=SearchResponse)
def classic_search(q: str = Query(default="amor impossible", min_length=1, max_length=120)) -> SearchResponse:
    return search_catalog(q, mode="classic")


@router.get("/smart", response_model=SearchResponse)
def smart_search(q: str = Query(default="songs for a nostalgic night drive", min_length=1, max_length=160)) -> SearchResponse:
    return search_catalog(q, mode="smart")
