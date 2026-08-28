"""Pub/Sub publishing.

One message per detected change, deliberately. If Gemini is slow or errors on
posting #14, postings #15-40 still process and #14 retries on its own with
backoff. A plain loop over changes would give none of that: one timeout would
stall the batch and leave it ambiguously half-processed.
"""
from __future__ import annotations

import json
import logging
import os

from google.cloud import pubsub_v1

log = logging.getLogger(__name__)

_publisher: pubsub_v1.PublisherClient | None = None


def _client() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def topic_path() -> str:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    topic = os.environ.get("PUBSUB_TOPIC", "job-changes")
    return _client().topic_path(project, topic)


def publish_changes(messages: list[dict]) -> int:
    """Publish one Pub/Sub message per change. Returns the count published.

    Attributes are set so a subscription could filter server-side later
    (e.g. only 'removed' events) without changing the payload format.
    """
    if not messages:
        return 0

    path = topic_path()
    futures = []
    for msg in messages:
        data = json.dumps(msg).encode("utf-8")
        futures.append(
            _client().publish(
                path,
                data,
                change_type=str(msg.get("change_type", "")),
                board_token=str(msg.get("board_token", "")),
                doc_id=str(msg.get("doc_id", "")),
            )
        )

    # Block so the caller knows publishing actually succeeded before it marks
    # the company baselined or returns 200 to Cloud Scheduler.
    published = 0
    for f in futures:
        f.result(timeout=60)
        published += 1

    log.info("published %d change messages to %s", published, path)
    return published
