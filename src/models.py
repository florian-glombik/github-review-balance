"""Data models for GitHub PR review analysis."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ReviewStats:
    """Statistics for reviews between two users."""
    prs_reviewed: int = 0
    lines_reviewed: int = 0
    additions_reviewed: int = 0  # Total +lines reviewed
    deletions_reviewed: int = 0  # Total -lines reviewed
    review_events: int = 0  # approvals, change requests, etc.
    comments: int = 0
    prs: List[Dict] = field(default_factory=list)