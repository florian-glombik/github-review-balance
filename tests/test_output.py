"""
Unit tests for OutputFormatter class and extended report functionality
"""

import pytest
from io import StringIO
from unittest.mock import patch
from collections import defaultdict

from src.models import ReviewStats
from src.output import OutputFormatter


class TestOutputFormatterInitialization:
    """Test cases for OutputFormatter initialization."""

    def test_initialization_default_params(self):
        """Test OutputFormatter initialization with default parameters."""
        formatter = OutputFormatter('test_user')

        assert formatter.username == 'test_user'
        assert formatter.sort_by == 'total_prs'
        assert formatter.show_extended_report is False

    def test_initialization_with_extended_report_true(self):
        """Test OutputFormatter initialization with extended report enabled."""
        formatter = OutputFormatter('test_user', show_extended_report=True)

        assert formatter.username == 'test_user'
        assert formatter.show_extended_report is True

    def test_initialization_with_extended_report_false(self):
        """Test OutputFormatter initialization with extended report disabled."""
        formatter = OutputFormatter('test_user', show_extended_report=False)

        assert formatter.username == 'test_user'
        assert formatter.show_extended_report is False

    def test_initialization_with_custom_sort_by(self):
        """Test OutputFormatter initialization with custom sort_by parameter."""
        formatter = OutputFormatter('test_user', sort_by='balance')

        assert formatter.username == 'test_user'
        assert formatter.sort_by == 'balance'

    def test_initialization_with_all_params(self):
        """Test OutputFormatter initialization with all parameters."""
        formatter = OutputFormatter('test_user', sort_by='balance', show_extended_report=True)

        assert formatter.username == 'test_user'
        assert formatter.sort_by == 'balance'
        assert formatter.show_extended_report is True


class TestExtendedReportDisplay:
    """Test cases for extended report display functionality."""

    @pytest.fixture
    def sample_stats(self):
        """Create sample review statistics for testing."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add data for user 'alice'
        reviewed_by_me['alice'].prs_reviewed = 2
        reviewed_by_me['alice'].lines_reviewed = 500
        reviewed_by_me['alice'].additions_reviewed = 400
        reviewed_by_me['alice'].deletions_reviewed = 100
        reviewed_by_me['alice'].review_events = 3
        reviewed_by_me['alice'].comments = 5
        reviewed_by_me['alice'].prs.append({
            'title': 'Fix bug in authentication',
            'url': 'https://github.com/test/repo/pull/1',
            'number': 1,
            'lines': 200,
            'additions': 150,
            'deletions': 50
        })
        reviewed_by_me['alice'].prs.append({
            'title': 'Add new feature',
            'url': 'https://github.com/test/repo/pull/2',
            'number': 2,
            'lines': 300,
            'additions': 250,
            'deletions': 50
        })

        reviewed_by_others['alice'].prs_reviewed = 3
        reviewed_by_others['alice'].lines_reviewed = 800
        reviewed_by_others['alice'].additions_reviewed = 600
        reviewed_by_others['alice'].deletions_reviewed = 200
        reviewed_by_others['alice'].review_events = 4
        reviewed_by_others['alice'].comments = 8
        reviewed_by_others['alice'].prs.append({
            'title': 'Update documentation',
            'url': 'https://github.com/test/repo/pull/3',
            'number': 3,
            'lines': 300,
            'additions': 200,
            'deletions': 100
        })

        open_prs_by_author = {}

        return reviewed_by_me, reviewed_by_others, open_prs_by_author

    def test_extended_report_shown_when_enabled(self, sample_stats):
        """Test that extended report is displayed when show_extended_report=True."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check that the extended report sections are present
            assert 'DETAILED REVIEW HISTORY' in output
            assert 'alice' in output
            assert 'PRs I reviewed' in output
            assert 'PRs they reviewed' in output
            assert 'Line Review Offset:' in output
            assert 'Fix bug in authentication' in output
            assert 'Update documentation' in output

    def test_extended_report_hidden_when_disabled(self, sample_stats):
        """Test that extended report is NOT displayed when show_extended_report=False."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user', show_extended_report=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check that the extended report sections are NOT present
            assert 'DETAILED REVIEW HISTORY' not in output
            # Use emoji markers specific to detailed history section
            assert '📝 PRs I reviewed' not in output
            assert '📝 PRs they reviewed' not in output
            assert '📊 Line Review Offset:' not in output
            # Check that PR titles from detailed history don't appear
            assert 'Fix bug in authentication' not in output
            assert 'Update documentation' not in output

            # But basic sections should still be present
            assert 'REVIEW BALANCE & NEXT ACTIONS' in output
            assert 'OVERALL STATISTICS' in output

    def test_extended_report_default_is_hidden(self, sample_stats):
        """Test that extended report is hidden by default (when parameter is not specified)."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user')  # No show_extended_report parameter

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check that the extended report is NOT shown by default
            assert 'DETAILED REVIEW HISTORY' not in output

    def test_extended_report_with_multiple_users(self):
        """Test extended report with multiple users."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add data for multiple users
        for user in ['alice', 'bob', 'charlie']:
            reviewed_by_me[user].prs_reviewed = 1
            reviewed_by_me[user].lines_reviewed = 100
            reviewed_by_me[user].prs.append({
                'title': f'PR by {user}',
                'url': f'https://github.com/test/repo/pull/{user}',
                'number': ord(user[0]),
                'lines': 100,
                'additions': 80,
                'deletions': 20
            })

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # All users should appear in the detailed history
            assert 'alice' in output
            assert 'bob' in output
            assert 'charlie' in output
            assert 'DETAILED REVIEW HISTORY' in output


class TestExtendedReportContent:
    """Test cases for the content of extended report."""

    @pytest.fixture
    def detailed_stats(self):
        """Create detailed review statistics for content testing."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Alice: I reviewed more of her code
        reviewed_by_me['alice'].prs_reviewed = 5
        reviewed_by_me['alice'].lines_reviewed = 1000
        reviewed_by_me['alice'].additions_reviewed = 800
        reviewed_by_me['alice'].deletions_reviewed = 200
        reviewed_by_me['alice'].review_events = 10
        reviewed_by_me['alice'].comments = 15

        reviewed_by_others['alice'].prs_reviewed = 2
        reviewed_by_others['alice'].lines_reviewed = 400
        reviewed_by_others['alice'].additions_reviewed = 300
        reviewed_by_others['alice'].deletions_reviewed = 100

        open_prs_by_author = {}

        return reviewed_by_me, reviewed_by_others, open_prs_by_author

    def test_extended_report_shows_review_metrics(self, detailed_stats):
        """Test that extended report shows all review metrics."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = detailed_stats
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check for metric labels
            assert 'PRs reviewed' in output
            assert 'Lines reviewed (total)' in output
            assert '+lines (additions)' in output
            assert '-lines (deletions)' in output
            assert 'Review events' in output
            assert 'Comments written' in output

    def test_extended_report_shows_line_offsets(self, detailed_stats):
        """Test that extended report shows line review offsets."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = detailed_stats
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check for offset information
            assert 'Line Review Offset:' in output
            assert 'positive = you reviewed more of their code' in output

    def test_extended_report_with_no_users(self):
        """Test extended report when there are no users."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        open_prs_by_author = {}

        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Should show "No review activity found" and not show detailed history
            assert 'No review activity found' in output
            assert 'DETAILED REVIEW HISTORY' not in output


class TestBasicOutputWithoutExtendedReport:
    """Test that basic output sections still work without extended report."""

    def test_review_balance_section_present_without_extended_report(self):
        """Test that review balance section is always present."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        reviewed_by_me['alice'].prs_reviewed = 2
        reviewed_by_me['alice'].lines_reviewed = 200

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'REVIEW BALANCE & NEXT ACTIONS' in output
            assert 'alice' in output

    def test_overall_statistics_section_present_without_extended_report(self):
        """Test that overall statistics section is always present."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        reviewed_by_me['alice'].prs_reviewed = 2
        reviewed_by_me['alice'].lines_reviewed = 200

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'OVERALL STATISTICS' in output
            assert 'Total PRs I reviewed:' in output
            assert 'Total lines I reviewed:' in output


class TestExtendedReportEdgeCases:
    """Test edge cases for extended report functionality."""

    def test_extended_report_with_empty_pr_list(self):
        """Test extended report when user has stats but empty PR list."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add stats but no PRs
        reviewed_by_me['alice'].prs_reviewed = 0
        reviewed_by_me['alice'].lines_reviewed = 0
        reviewed_by_me['alice'].prs = []  # Empty PR list

        reviewed_by_others['alice'].prs_reviewed = 0
        reviewed_by_others['alice'].lines_reviewed = 0
        reviewed_by_others['alice'].prs = []

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True)

        # Should not crash
        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Extended report should still be attempted
            assert 'DETAILED REVIEW HISTORY' in output

    def test_extended_report_with_large_line_counts(self):
        """Test extended report formatting with large line counts."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add large line counts
        reviewed_by_me['alice'].prs_reviewed = 100
        reviewed_by_me['alice'].lines_reviewed = 1000000
        reviewed_by_me['alice'].additions_reviewed = 800000
        reviewed_by_me['alice'].deletions_reviewed = 200000

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Should handle large numbers
            assert 'DETAILED REVIEW HISTORY' in output
            assert 'alice' in output


class TestPrintDetailedHistory:
    """Test the _print_detailed_history method specifically."""

    def test_print_detailed_history_method_called_when_enabled(self):
        """Test that _print_detailed_history is called when extended report is enabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True)

        with patch.object(formatter, '_print_detailed_history') as mock_method:
            with patch('sys.stdout', new=StringIO()):
                formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)

                # Method should be called once
                mock_method.assert_called_once()

    def test_print_detailed_history_method_not_called_when_disabled(self):
        """Test that _print_detailed_history is NOT called when extended report is disabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=False)

        with patch.object(formatter, '_print_detailed_history') as mock_method:
            with patch('sys.stdout', new=StringIO()):
                formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)

                # Method should NOT be called
                mock_method.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])