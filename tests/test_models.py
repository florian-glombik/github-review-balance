"""
Unit tests for ReviewStats dataclass
"""

import pytest
from src.models import ReviewStats


class TestReviewStats:
    """Test cases for ReviewStats dataclass."""

    def test_review_stats_initialization(self):
        """Test that ReviewStats initializes with default values."""
        stats = ReviewStats()
        assert stats.prs_reviewed == 0
        assert stats.lines_reviewed == 0
        assert stats.additions_reviewed == 0
        assert stats.deletions_reviewed == 0
        assert stats.review_events == 0
        assert stats.comments == 0
        assert stats.prs == []

    def test_review_stats_with_values(self):
        """Test ReviewStats with custom values."""
        pr_list = [{'title': 'Test PR', 'number': 123}]
        stats = ReviewStats(
            prs_reviewed=5,
            lines_reviewed=100,
            additions_reviewed=80,
            deletions_reviewed=20,
            review_events=3,
            comments=10,
            prs=pr_list
        )
        assert stats.prs_reviewed == 5
        assert stats.lines_reviewed == 100
        assert stats.additions_reviewed == 80
        assert stats.deletions_reviewed == 20
        assert stats.review_events == 3
        assert stats.comments == 10
        assert stats.prs == pr_list


class TestPRListStorage:
    """Test cases for storing PR lists in ReviewStats."""

    def test_pr_list_append(self):
        """Test appending PRs to stats."""
        stats = ReviewStats()

        pr1 = {'number': 1, 'title': 'PR 1'}
        pr2 = {'number': 2, 'title': 'PR 2'}

        stats.prs.append(pr1)
        stats.prs.append(pr2)

        assert len(stats.prs) == 2
        assert stats.prs[0]['number'] == 1
        assert stats.prs[1]['number'] == 2

    def test_pr_list_contains_details(self):
        """Test that PR list contains all necessary details."""
        stats = ReviewStats()

        pr_info = {
            'title': 'Test PR',
            'url': 'https://github.com/test/repo/pull/123',
            'number': 123,
            'lines': 500,
            'additions': 400,
            'deletions': 100
        }

        stats.prs.append(pr_info)

        stored_pr = stats.prs[0]
        assert stored_pr['title'] == 'Test PR'
        assert stored_pr['number'] == 123
        assert stored_pr['additions'] == 400
        assert stored_pr['deletions'] == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])