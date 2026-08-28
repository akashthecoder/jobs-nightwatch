"""Greenhouse job board adapter.

Public, unauthenticated, one HTTP call per company:

    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

The `content=true` parameter is MANDATORY. Without it the response carries
title/location/url but no description at all, which looks like it requires a
second fetch per job. It does not.
"""
from __future__ import annotations

import logging

import requests

from common.schema import JobPosting, clean_html

log = logging.getLogger(__name__)

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
TIMEOUT_SECONDS = 90


def fetch_board(board_token: str, company_name: str) -> list[JobPosting]:
    """Fetch and normalize every posting on one Greenhouse board.

    Raises requests.HTTPError if the board does not resolve, so the caller can
    mark that company failed without silently recording an empty board -- an
    empty list would otherwise look like "every posting was removed" and fire a
    flood of bogus removal alerts.
    """
    resp = requests.get(
        BOARD_URL.format(token=board_token),
        params={"content": "true"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()

    jobs = resp.json().get("jobs", [])
    postings = [_normalize(j, board_token, company_name) for j in jobs]
    log.info("greenhouse: %s -> %d postings", board_token, len(postings))
    return postings


def _normalize(job: dict, board_token: str, company_name: str) -> JobPosting:
    departments = job.get("departments") or []
    department = departments[0].get("name", "") if departments else ""

    location = (job.get("location") or {}).get("name", "") or ""

    return JobPosting(
        company=company_name,
        board_token=board_token,
        external_id=str(job.get("id", "")),
        title=(job.get("title") or "").strip(),
        location=location.strip(),
        department=department.strip(),
        url=job.get("absolute_url", ""),
        description_text=clean_html(job.get("content")),
        updated_at=job.get("updated_at", ""),
        source_ats="greenhouse",
    )
