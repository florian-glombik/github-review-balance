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
        assert formatter.show_overall_statistics is True

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
        formatter = OutputFormatter('test_user', sort_by='balance', show_extended_report=True, show_overall_statistics=False)

        assert formatter.username == 'test_user'
        assert formatter.sort_by == 'balance'
        assert formatter.show_extended_report is True
        assert formatter.show_overall_statistics is False


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


class TestOverallStatisticsDisplay:
    """Test cases for overall statistics display functionality."""

    @pytest.fixture
    def sample_stats(self):
        """Create sample review statistics for testing."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        reviewed_by_me['alice'].prs_reviewed = 2
        reviewed_by_me['alice'].lines_reviewed = 500
        reviewed_by_me['alice'].additions_reviewed = 400
        reviewed_by_me['alice'].deletions_reviewed = 100

        reviewed_by_others['alice'].prs_reviewed = 3
        reviewed_by_others['alice'].lines_reviewed = 800
        reviewed_by_others['alice'].additions_reviewed = 600
        reviewed_by_others['alice'].deletions_reviewed = 200

        open_prs_by_author = {}

        return reviewed_by_me, reviewed_by_others, open_prs_by_author

    def test_overall_statistics_shown_when_enabled(self, sample_stats):
        """Test that overall statistics is displayed when show_overall_statistics=True."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user', show_overall_statistics=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'OVERALL STATISTICS' in output
            assert 'Total PRs I reviewed:' in output
            assert 'Total PRs others reviewed of mine:' in output
            assert 'Total lines I reviewed:' in output
            assert 'Total lines others reviewed:' in output
            assert 'Number of collaborators:' in output

    def test_overall_statistics_hidden_when_disabled(self, sample_stats):
        """Test that overall statistics is NOT displayed when show_overall_statistics=False."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user', show_overall_statistics=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'OVERALL STATISTICS' not in output
            assert 'REVIEW BALANCE & NEXT ACTIONS' in output

    def test_overall_statistics_default_is_shown(self, sample_stats):
        """Test that overall statistics is shown by default (when parameter is not specified)."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = sample_stats
        formatter = OutputFormatter('test_user')

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'OVERALL STATISTICS' in output


class TestPrintOverallStats:
    """Test the _print_overall_stats method specifically."""

    def test_print_overall_stats_method_called_when_enabled(self):
        """Test that _print_overall_stats is called when overall statistics is enabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_overall_statistics=True)

        with patch.object(formatter, '_print_overall_stats') as mock_method:
            with patch('sys.stdout', new=StringIO()):
                formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)

                mock_method.assert_called_once()

    def test_print_overall_stats_method_not_called_when_disabled(self):
        """Test that _print_overall_stats is NOT called when overall statistics is disabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_overall_statistics=False)

        with patch.object(formatter, '_print_overall_stats') as mock_method:
            with patch('sys.stdout', new=StringIO()):
                formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)

                mock_method.assert_not_called()


class TestCombinedOptions:
    """Test cases for combined show_extended_report and show_overall_statistics options."""

    def test_both_extended_and_stats_enabled(self):
        """Test with both extended report and overall statistics enabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True, show_overall_statistics=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'DETAILED REVIEW HISTORY' in output
            assert 'OVERALL STATISTICS' in output

    def test_both_extended_and_stats_disabled(self):
        """Test with both extended report and overall statistics disabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=False, show_overall_statistics=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'DETAILED REVIEW HISTORY' not in output
            assert 'OVERALL STATISTICS' not in output
            assert 'REVIEW BALANCE & NEXT ACTIONS' in output

    def test_extended_enabled_stats_disabled(self):
        """Test with extended report enabled but overall statistics disabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=True, show_overall_statistics=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'DETAILED REVIEW HISTORY' in output
            assert 'OVERALL STATISTICS' not in output

    def test_extended_disabled_stats_enabled(self):
        """Test with extended report disabled but overall statistics enabled."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        open_prs_by_author = {}
        formatter = OutputFormatter('test_user', show_extended_report=False, show_overall_statistics=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            assert 'DETAILED REVIEW HISTORY' not in output
            assert 'OVERALL STATISTICS' in output


class TestReviewRequestedIndicator:
    """Test cases for the review requested indicator functionality."""

    def test_review_requested_indicator_shown(self):
        """Test that review requested indicator appears when requested_my_review is True."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add minimal review history to trigger display
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        # Create open PR with review requested
        open_prs_by_author = {
            'alice': [{
                'number': 123,
                'title': 'Fix authentication bug',
                'url': 'https://github.com/test/repo/pull/123',
                'repo': 'test/repo',
                'additions': 50,
                'deletions': 20,
                'review_count': 0,
                'requested_my_review': True
            }]
        }

        formatter = OutputFormatter('test_user')

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check that the review requested indicator appears
            assert '[REVIEW REQUESTED]' in output
            assert 'Fix authentication bug' in output

    def test_review_requested_indicator_not_shown(self):
        """Test that review requested indicator does NOT appear when requested_my_review is False."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add minimal review history to trigger display
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        # Create open PR without review requested
        open_prs_by_author = {
            'alice': [{
                'number': 123,
                'title': 'Fix authentication bug',
                'url': 'https://github.com/test/repo/pull/123',
                'repo': 'test/repo',
                'additions': 50,
                'deletions': 20,
                'review_count': 0,
                'requested_my_review': False
            }]
        }

        formatter = OutputFormatter('test_user')

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Check that the review requested indicator does NOT appear
            assert '[REVIEW REQUESTED]' not in output
            assert 'Fix authentication bug' in output

    def test_review_requested_with_multiple_prs(self):
        """Test review requested indicator with multiple PRs, some requested and some not."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add some review history for balance calculation
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100
        reviewed_by_others['alice'].prs_reviewed = 2
        reviewed_by_others['alice'].lines_reviewed = 300

        # Create multiple PRs with different requested_my_review states
        open_prs_by_author = {
            'alice': [
                {
                    'number': 123,
                    'title': 'Requested PR 1',
                    'url': 'https://github.com/test/repo/pull/123',
                    'repo': 'test/repo',
                    'additions': 50,
                    'deletions': 20,
                    'review_count': 0,
                    'requested_my_review': True
                },
                {
                    'number': 124,
                    'title': 'Not requested PR',
                    'url': 'https://github.com/test/repo/pull/124',
                    'repo': 'test/repo',
                    'additions': 30,
                    'deletions': 10,
                    'review_count': 1,
                    'requested_my_review': False
                },
                {
                    'number': 125,
                    'title': 'Requested PR 2',
                    'url': 'https://github.com/test/repo/pull/125',
                    'repo': 'test/repo',
                    'additions': 100,
                    'deletions': 50,
                    'review_count': 0,
                    'requested_my_review': True
                }
            ]
        }

        formatter = OutputFormatter('test_user')

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Count occurrences of the review requested indicator
            requested_count = output.count('[REVIEW REQUESTED]')
            assert requested_count == 2, f"Expected 2 [REVIEW REQUESTED] indicators, found {requested_count}"

            # Check that all PR titles appear
            assert 'Requested PR 1' in output
            assert 'Not requested PR' in output
            assert 'Requested PR 2' in output

    def test_review_requested_bypasses_review_count_threshold(self):
        """Test that requested PRs are shown even when they exceed the review count threshold."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add minimal review history to trigger display
        reviewed_by_me['alice'].prs_reviewed = 1
        reviewed_by_me['alice'].lines_reviewed = 100

        # Create PRs with high review counts
        open_prs_by_author = {
            'alice': [
                {
                    'number': 123,
                    'title': 'Requested PR with many reviews',
                    'url': 'https://github.com/test/repo/pull/123',
                    'repo': 'test/repo',
                    'additions': 50,
                    'deletions': 20,
                    'review_count': 5,  # High review count
                    'requested_my_review': True
                },
                {
                    'number': 124,
                    'title': 'Not requested PR with many reviews',
                    'url': 'https://github.com/test/repo/pull/124',
                    'repo': 'test/repo',
                    'additions': 30,
                    'deletions': 10,
                    'review_count': 5,  # High review count
                    'requested_my_review': False
                }
            ]
        }

        # Set threshold to filter PRs with 3 or more reviews
        formatter = OutputFormatter('test_user', max_review_count_threshold=3)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # The requested PR should appear despite high review count
            assert 'Requested PR with many reviews' in output
            assert '[REVIEW REQUESTED]' in output

            # The non-requested PR should be filtered out
            assert 'Not requested PR with many reviews' not in output

            # Check that filtering message appears
            assert 'filtered out by threshold' in output or 'filtered out due to review count threshold' in output

    def test_review_requested_with_no_review_history(self):
        """Test review requested indicator when there's no review history with the author."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Add minimal review history with bob to trigger display
        reviewed_by_me['bob'].prs_reviewed = 1
        reviewed_by_me['bob'].lines_reviewed = 50

        # Open PR from bob with review requested
        open_prs_by_author = {
            'bob': [{
                'number': 456,
                'title': 'New contributor PR',
                'url': 'https://github.com/test/repo/pull/456',
                'repo': 'test/repo',
                'additions': 200,
                'deletions': 100,
                'review_count': 0,
                'requested_my_review': True
            }]
        }

        formatter = OutputFormatter('test_user')

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # Should still show the requested indicator
            assert '[REVIEW REQUESTED]' in output
            assert 'New contributor PR' in output
            assert 'bob' in output


class TestFilterNonPRAuthors:
    """Test cases for filtering out users who haven't opened any PRs."""

    @pytest.fixture
    def mixed_user_stats(self):
        """Create statistics with users who opened PRs and users who only reviewed."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # alice: I reviewed their PRs, they reviewed mine
        reviewed_by_me['alice'].prs_reviewed = 2
        reviewed_by_me['alice'].lines_reviewed = 200
        reviewed_by_me['alice'].additions_reviewed = 150
        reviewed_by_me['alice'].deletions_reviewed = 50

        reviewed_by_others['alice'].prs_reviewed = 3
        reviewed_by_others['alice'].lines_reviewed = 300
        reviewed_by_others['alice'].additions_reviewed = 250
        reviewed_by_others['alice'].deletions_reviewed = 50

        # bob: I reviewed their PRs, they reviewed mine
        reviewed_by_me['bob'].prs_reviewed = 1
        reviewed_by_me['bob'].lines_reviewed = 100
        reviewed_by_me['bob'].additions_reviewed = 80
        reviewed_by_me['bob'].deletions_reviewed = 20

        reviewed_by_others['bob'].prs_reviewed = 2
        reviewed_by_others['bob'].lines_reviewed = 150
        reviewed_by_others['bob'].additions_reviewed = 120
        reviewed_by_others['bob'].deletions_reviewed = 30

        # charlie: Only reviewed my PRs, never opened any PRs
        reviewed_by_others['charlie'].prs_reviewed = 2
        reviewed_by_others['charlie'].lines_reviewed = 100
        reviewed_by_others['charlie'].additions_reviewed = 80
        reviewed_by_others['charlie'].deletions_reviewed = 20
        # charlie has 0 PRs I reviewed (not in reviewed_by_me dict)

        # david: Only reviewed my PRs, never opened any PRs
        reviewed_by_others['david'].prs_reviewed = 1
        reviewed_by_others['david'].lines_reviewed = 50
        reviewed_by_others['david'].additions_reviewed = 40
        reviewed_by_others['david'].deletions_reviewed = 10

        open_prs_by_author = {}

        return reviewed_by_me, reviewed_by_others, open_prs_by_author

    def test_filter_non_pr_authors_enabled(self, mixed_user_stats):
        """Test that users who haven't opened PRs are filtered out when flag is True."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = mixed_user_stats
        formatter = OutputFormatter('test_user', filter_non_pr_authors=True)

        # alice and bob are PR authors, charlie and david are not
        pr_authors = {'alice', 'bob'}

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author, pr_authors)
            output = fake_output.getvalue()

            # alice and bob should appear (they opened PRs)
            assert 'alice' in output
            assert 'bob' in output

            # charlie and david should NOT appear (they only reviewed, never opened PRs)
            assert 'charlie' not in output
            assert 'david' not in output

    def test_filter_non_pr_authors_disabled(self, mixed_user_stats):
        """Test that all users appear when filter_non_pr_authors is False."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = mixed_user_stats
        formatter = OutputFormatter('test_user', filter_non_pr_authors=False)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # All users should appear
            assert 'alice' in output
            assert 'bob' in output
            assert 'charlie' in output
            assert 'david' in output

    def test_filter_non_pr_authors_default(self, mixed_user_stats):
        """Test that filtering is disabled by default."""
        reviewed_by_me, reviewed_by_others, open_prs_by_author = mixed_user_stats
        formatter = OutputFormatter('test_user')  # No filter_non_pr_authors parameter

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author)
            output = fake_output.getvalue()

            # All users should appear (default is False)
            assert 'alice' in output
            assert 'bob' in output
            assert 'charlie' in output
            assert 'david' in output

    def test_filter_non_pr_authors_with_only_reviewers(self):
        """Test filtering when only reviewers exist (no PR authors)."""
        reviewed_by_me = defaultdict(ReviewStats)
        reviewed_by_others = defaultdict(ReviewStats)

        # Only users who reviewed, no users who opened PRs
        reviewed_by_others['reviewer1'].prs_reviewed = 2
        reviewed_by_others['reviewer1'].lines_reviewed = 100
        reviewed_by_others['reviewer2'].prs_reviewed = 1
        reviewed_by_others['reviewer2'].lines_reviewed = 50

        open_prs_by_author = {}
        pr_authors = set()  # No PR authors
        formatter = OutputFormatter('test_user', filter_non_pr_authors=True)

        with patch('sys.stdout', new=StringIO()) as fake_output:
            formatter.print_summary(reviewed_by_me, reviewed_by_others, open_prs_by_author, pr_authors)
            output = fake_output.getvalue()

            # No users should appear in the table
            assert 'reviewer1' not in output
            assert 'reviewer2' not in output

    def test_filter_non_pr_authors_initialization(self):
        """Test that filter_non_pr_authors is properly initialized."""
        formatter1 = OutputFormatter('test_user', filter_non_pr_authors=True)
        assert formatter1.filter_non_pr_authors is True

        formatter2 = OutputFormatter('test_user', filter_non_pr_authors=False)
        assert formatter2.filter_non_pr_authors is False

        formatter3 = OutputFormatter('test_user')
        assert formatter3.filter_non_pr_authors is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])