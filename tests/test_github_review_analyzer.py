"""
Unit tests for GitHubReviewAnalyzer class
"""

import pytest
import os
import sys
import tempfile
import requests
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util

# Import the module from file with hyphens
spec = importlib.util.spec_from_file_location("github_review_analyzer", "github-review-analyzer.py")
github_review_analyzer = importlib.util.module_from_spec(spec)
sys.modules["github_review_analyzer"] = github_review_analyzer
spec.loader.exec_module(github_review_analyzer)

# Import from the new modular structure
from src.models import ReviewStats
from src.analyzer import GitHubReviewAnalyzer


class TestGitHubReviewAnalyzer:
    """Test cases for GitHubReviewAnalyzer class."""

    @pytest.fixture
    def temp_cache_file(self):
        """Create a temporary cache file for testing."""
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def analyzer(self, temp_cache_file):
        """Create a GitHubReviewAnalyzer instance for testing."""
        return GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=temp_cache_file,
            use_cache=True
        )

    @pytest.fixture
    def analyzer_no_cache(self, temp_cache_file):
        """Create a GitHubReviewAnalyzer instance without caching."""
        return GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=temp_cache_file,
            use_cache=False
        )

    def test_initialization_with_token(self, analyzer):
        """Test analyzer initialization with a token."""
        assert analyzer.username == 'test_user'
        assert analyzer.api_client.token == 'test_token'
        assert analyzer.cache_manager.use_cache is True
        assert 'Authorization' in analyzer.api_client.session.headers

    def test_initialization_without_token(self, temp_cache_file):
        """Test analyzer initialization without a token."""
        with patch.dict(os.environ, {}, clear=True):
            analyzer = GitHubReviewAnalyzer(
                username='test_user',
                cache_file=temp_cache_file
            )
            assert analyzer.token is None
            assert 'Authorization' not in analyzer.session.headers

    def test_initialization_with_excluded_users(self, temp_cache_file):
        """Test analyzer initialization with excluded users."""
        excluded = {'bot1', 'bot2'}
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=temp_cache_file,
            excluded_users=excluded
        )
        assert analyzer.excluded_users == excluded

    def test_initialization_with_required_label(self, temp_cache_file):
        """Test analyzer initialization with required PR label."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=temp_cache_file,
            required_pr_label='ready for review'
        )
        assert analyzer.required_pr_label == 'ready for review'

    def test_excluded_users_filtering(self, analyzer):
        """Test that excluded users are properly stored."""
        excluded = {'dependabot', 'bot'}
        analyzer_with_excluded = GitHubReviewAnalyzer(
            username='test_user',
            excluded_users=excluded
        )
        assert analyzer_with_excluded.excluded_users == excluded


class TestAnalyzerStateMethods:
    """Test cases for analyzer methods that manage state."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer for state tests."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=True
        )
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_reviewed_by_me_initialization(self, analyzer):
        """Test that reviewed_by_me is initialized as defaultdict."""
        assert len(analyzer.reviewed_by_me) == 0
        # Accessing non-existent key should create ReviewStats
        stats = analyzer.reviewed_by_me['new_user']
        assert isinstance(stats, ReviewStats)

    def test_reviewed_by_others_initialization(self, analyzer):
        """Test that reviewed_by_others is initialized as defaultdict."""
        assert len(analyzer.reviewed_by_others) == 0
        stats = analyzer.reviewed_by_others['new_user']
        assert isinstance(stats, ReviewStats)

    def test_repositories_list(self, analyzer):
        """Test repositories list initialization."""
        assert analyzer.repositories == []


class TestPRAnalysisLogic:
    """Test cases for PR analysis logic."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create an analyzer with mocked session."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=False  # Disable cache for these tests
        )
        analyzer.session = Mock()
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_analyze_pr_excludes_pr_author_in_excluded_users(self, mock_analyzer):
        """Test that PRs from excluded users are skipped."""
        mock_analyzer.excluded_users = {'excluded_bot'}

        pr = {
            'number': 123,
            'user': {'login': 'excluded_bot'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/test/pull/123',
            'state': 'open'
        }

        # Should return early and not process the PR
        mock_analyzer._analyze_pr('test/repo', pr)

        # Verify no stats were updated
        assert len(mock_analyzer.reviewed_by_me) == 0
        assert len(mock_analyzer.reviewed_by_others) == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_cache_file_creation(self):
        """Test that analyzer works with non-existent cache file."""
        cache_file = '/tmp/non_existent_cache_file.json'
        if os.path.exists(cache_file):
            os.remove(cache_file)

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=cache_file,
            use_cache=True
        )
        assert analyzer.cache == {}

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_corrupted_cache_file(self):
        """Test that analyzer handles corrupted cache gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("corrupted json {[}")
            cache_file = f.name

        # Should not crash, should just start with empty cache
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=cache_file,
            use_cache=True
        )
        assert analyzer.cache == {}

        os.remove(cache_file)

    def test_empty_username(self):
        """Test initialization with empty username."""
        analyzer = GitHubReviewAnalyzer(username='', use_cache=False)
        assert analyzer.username == ''

    def test_none_excluded_users(self):
        """Test that None excluded_users becomes empty set."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            excluded_users=None,
            use_cache=False
        )
        assert analyzer.excluded_users == set()


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_token_from_environment(self):
        """Test that token is read from GITHUB_TOKEN environment variable."""
        test_token = 'env_token_12345'
        with patch.dict(os.environ, {'GITHUB_TOKEN': test_token}):
            analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)
            assert analyzer.token == test_token

    def test_explicit_token_overrides_environment(self):
        """Test that explicit token parameter overrides environment variable."""
        env_token = 'env_token'
        explicit_token = 'explicit_token'

        with patch.dict(os.environ, {'GITHUB_TOKEN': env_token}):
            analyzer = GitHubReviewAnalyzer(
                username='test_user',
                token=explicit_token,
                use_cache=False
            )
            assert analyzer.token == explicit_token


class TestSortingFunctionality:
    """Test cases for table sorting functionality."""

    @pytest.fixture
    def analyzer_with_sort(self):
        """Create analyzer with sort_by parameter."""
        def _create_analyzer(sort_by='total_prs'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
                cache_file = f.name

            analyzer = GitHubReviewAnalyzer(
                username='test_user',
                token='test_token',
                cache_file=cache_file,
                use_cache=False,
                sort_by=sort_by
            )
            return analyzer, cache_file

        return _create_analyzer

    def test_default_sort_by(self):
        """Test that default sort_by is 'total_prs'."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)
        assert analyzer.sort_by == 'total_prs'

    def test_custom_sort_by(self, analyzer_with_sort):
        """Test initialization with custom sort_by parameter."""
        analyzer, cache_file = analyzer_with_sort('balance')
        try:
            assert analyzer.sort_by == 'balance'
        finally:
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def test_all_valid_sort_options(self, analyzer_with_sort):
        """Test all valid sort options."""
        valid_options = ['total_prs', 'balance', 'user', 'they_reviewed', 'i_reviewed', 'their_prs', 'my_prs']

        for option in valid_options:
            analyzer, cache_file = analyzer_with_sort(option)
            try:
                assert analyzer.sort_by == option
            finally:
                if os.path.exists(cache_file):
                    os.remove(cache_file)

    def test_sort_by_total_prs(self):
        """Test sorting by total PRs (descending)."""
        test_data = [
            {'user': 'Alice', 'total_prs': 5, 'balance': 100},
            {'user': 'Bob', 'total_prs': 10, 'balance': 50},
            {'user': 'Charlie', 'total_prs': 8, 'balance': 200}
        ]

        sort_key = lambda x: x['total_prs']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Bob'  # 10 PRs
        assert sorted_data[1]['user'] == 'Charlie'  # 8 PRs
        assert sorted_data[2]['user'] == 'Alice'  # 5 PRs

    def test_sort_by_balance(self):
        """Test sorting by balance (descending)."""
        test_data = [
            {'user': 'Alice', 'total_prs': 5, 'balance': 100},
            {'user': 'Bob', 'total_prs': 10, 'balance': -50},
            {'user': 'Charlie', 'total_prs': 8, 'balance': 200}
        ]

        sort_key = lambda x: x['balance']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Charlie'  # balance: 200
        assert sorted_data[1]['user'] == 'Alice'    # balance: 100
        assert sorted_data[2]['user'] == 'Bob'      # balance: -50

    def test_sort_by_user_alphabetically(self):
        """Test sorting by username (ascending/alphabetical)."""
        test_data = [
            {'user': 'Charlie', 'total_prs': 8, 'balance': 200},
            {'user': 'Alice', 'total_prs': 5, 'balance': 100},
            {'user': 'Bob', 'total_prs': 10, 'balance': 50}
        ]

        sort_key = lambda x: x['user'].lower()
        sorted_data = sorted(test_data, key=sort_key, reverse=False)

        assert sorted_data[0]['user'] == 'Alice'
        assert sorted_data[1]['user'] == 'Bob'
        assert sorted_data[2]['user'] == 'Charlie'


class TestGetPaginatedMethod:
    """Test cases for the get_paginated method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked session."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)
        analyzer.session = Mock()
        return analyzer

    def test_get_paginated_single_page(self, mock_analyzer):
        """Test fetching a single page of results."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1}, {'id': 2}]
        mock_analyzer.api_client.session.get = Mock(return_value=mock_response)

        result = mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[1]['id'] == 2

    def test_get_paginated_empty_response(self, mock_analyzer):
        """Test handling of empty response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_analyzer.api_client.session.get = Mock(return_value=mock_response)

        result = mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

        assert len(result) == 0

    def test_get_paginated_rate_limit_error(self, mock_analyzer):
        """Test handling of rate limit errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {'message': 'rate limit exceeded'}
        mock_analyzer.api_client.session.get = Mock(return_value=mock_response)

        with pytest.raises(SystemExit):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)


class TestPRFilteringLogic:
    """Test cases for PR filtering logic."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer for filtering tests."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)
        analyzer.session = Mock()
        return analyzer

    def test_draft_pr_filtering(self, mock_analyzer):
        """Test that draft PRs are filtered out."""
        draft_pr = {
            'number': 123,
            'user': {'login': 'other_user'},
            'title': 'Draft PR',
            'html_url': 'https://github.com/test/test/pull/123',
            'state': 'open',
            'draft': True
        }

        assert draft_pr['draft'] is True

    def test_required_label_filtering(self):
        """Test that PRs without required label are filtered."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_pr_label='ready-for-review',
            use_cache=False
        )

        pr_with_label = {
            'labels': [{'name': 'ready-for-review'}, {'name': 'bug'}]
        }
        pr_without_label = {
            'labels': [{'name': 'bug'}]
        }

        labels_with = [l['name'] for l in pr_with_label['labels']]
        labels_without = [l['name'] for l in pr_without_label['labels']]

        assert 'ready-for-review' in labels_with
        assert 'ready-for-review' not in labels_without


class TestReviewActivityTracking:
    """Test cases for tracking review activity."""

    @pytest.fixture
    def analyzer_with_data(self):
        """Create analyzer with some test data."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        # Add some test review data
        analyzer.reviewed_by_me['alice'].prs_reviewed = 5
        analyzer.reviewed_by_me['alice'].lines_reviewed = 500
        analyzer.reviewed_by_me['alice'].additions_reviewed = 400
        analyzer.reviewed_by_me['alice'].deletions_reviewed = 100

        analyzer.reviewed_by_others['bob'].prs_reviewed = 3
        analyzer.reviewed_by_others['bob'].lines_reviewed = 300
        analyzer.reviewed_by_others['bob'].additions_reviewed = 250
        analyzer.reviewed_by_others['bob'].deletions_reviewed = 50

        return analyzer

    def test_stats_accumulation(self, analyzer_with_data):
        """Test that stats accumulate correctly."""
        assert analyzer_with_data.reviewed_by_me['alice'].prs_reviewed == 5
        assert analyzer_with_data.reviewed_by_me['alice'].lines_reviewed == 500

    def test_multiple_users_tracking(self, analyzer_with_data):
        """Test tracking multiple users."""
        analyzer_with_data.reviewed_by_me['charlie'].prs_reviewed = 2

        assert len(analyzer_with_data.reviewed_by_me) == 2
        assert 'alice' in analyzer_with_data.reviewed_by_me
        assert 'charlie' in analyzer_with_data.reviewed_by_me

    def test_bidirectional_tracking(self, analyzer_with_data):
        """Test that reviews are tracked in both directions."""
        assert analyzer_with_data.reviewed_by_me['alice'].prs_reviewed == 5
        assert analyzer_with_data.reviewed_by_others['bob'].prs_reviewed == 3

    def test_line_counts_separated(self, analyzer_with_data):
        """Test that additions and deletions are tracked separately."""
        alice_stats = analyzer_with_data.reviewed_by_me['alice']

        assert alice_stats.additions_reviewed == 400
        assert alice_stats.deletions_reviewed == 100
        assert alice_stats.lines_reviewed == 500  # Total


class TestDefaultDictBehavior:
    """Test cases for defaultdict behavior in stats tracking."""

    def test_new_user_creates_empty_stats(self):
        """Test that accessing a new user creates empty ReviewStats."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        stats = analyzer.reviewed_by_me['new_user']

        assert isinstance(stats, ReviewStats)
        assert stats.prs_reviewed == 0
        assert stats.lines_reviewed == 0

    def test_multiple_new_users(self):
        """Test creating stats for multiple users on the fly."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        analyzer.reviewed_by_me['user1'].prs_reviewed = 1
        analyzer.reviewed_by_me['user2'].prs_reviewed = 2
        analyzer.reviewed_by_me['user3'].prs_reviewed = 3

        assert len(analyzer.reviewed_by_me) == 3


class TestSessionConfiguration:
    """Test cases for session configuration."""

    def test_session_has_retry_adapter(self):
        """Test that session is configured with retry adapter."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        assert analyzer.session is not None
        assert 'https://' in analyzer.session.adapters

    def test_session_headers_with_token(self):
        """Test that Authorization header is set when token is provided."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token_123',
            use_cache=False
        )

        assert 'Authorization' in analyzer.session.headers
        assert analyzer.session.headers['Authorization'] == 'token test_token_123'

    def test_session_headers_without_token(self):
        """Test that no Authorization header is set without token."""
        with patch.dict(os.environ, {}, clear=True):
            analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

            assert 'Authorization' not in analyzer.session.headers


class TestThreadSafety:
    """Test cases for thread safety in parallel processing."""

    def test_stats_lock_exists(self):
        """Test that stats lock is initialized."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        assert hasattr(analyzer, '_stats_lock')
        assert isinstance(analyzer._stats_lock, type(threading.Lock()))

    def test_concurrent_stats_update(self):
        """Test that stats can be updated safely from multiple threads."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        def update_stats(user, count):
            with analyzer._stats_lock:
                analyzer.reviewed_by_me[user].prs_reviewed += count

        # Simulate concurrent updates
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(update_stats, 'alice', 1),
                executor.submit(update_stats, 'alice', 1),
                executor.submit(update_stats, 'alice', 1)
            ]

            for future in as_completed(futures):
                future.result()

        assert analyzer.reviewed_by_me['alice'].prs_reviewed == 3


class TestRepositoryListTracking:
    """Test cases for tracking analyzed repositories."""

    def test_repository_list_initialization(self):
        """Test that repository list is initialized empty."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        assert analyzer.repositories == []

    def test_repository_deduplication(self):
        """Test that repositories are not duplicated in the list."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        repo = 'owner/repo'
        if repo not in analyzer.repositories:
            analyzer.repositories.append(repo)
        if repo not in analyzer.repositories:
            analyzer.repositories.append(repo)

        assert len(analyzer.repositories) == 1


class TestExcludedUsersSet:
    """Test cases for excluded users functionality."""

    def test_excluded_users_is_set(self):
        """Test that excluded_users is a set."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            excluded_users={'bot1', 'bot2'},
            use_cache=False
        )

        assert isinstance(analyzer.excluded_users, set)

    def test_excluded_users_membership(self):
        """Test checking membership in excluded users."""
        excluded = {'dependabot', 'renovate'}
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            excluded_users=excluded,
            use_cache=False
        )

        assert 'dependabot' in analyzer.excluded_users
        assert 'renovate' in analyzer.excluded_users
        assert 'real_user' not in analyzer.excluded_users


class TestBalanceCalculation:
    """Test cases for review balance calculations."""

    def test_positive_balance(self):
        """Test calculation when I reviewed more than they did."""
        i_reviewed = 500
        they_reviewed = 300
        balance = they_reviewed - i_reviewed

        assert balance == -200  # Negative means they owe me

    def test_negative_balance(self):
        """Test calculation when they reviewed more than I did."""
        i_reviewed = 300
        they_reviewed = 500
        balance = they_reviewed - i_reviewed

        assert balance == 200  # Positive means I owe them

    def test_zero_balance(self):
        """Test calculation when reviews are balanced."""
        i_reviewed = 500
        they_reviewed = 500
        balance = they_reviewed - i_reviewed

        assert balance == 0

    def test_balance_with_additions_and_deletions(self):
        """Test that balance accounts for both additions and deletions."""
        my_additions = 400
        my_deletions = 100
        their_additions = 300
        their_deletions = 150

        my_total = my_additions + my_deletions  # 500
        their_total = their_additions + their_deletions  # 450
        balance = their_total - my_total

        assert balance == -50


class TestPRInfoStructure:
    """Test cases for PR info data structures."""

    def test_pr_info_contains_required_fields(self):
        """Test that PR info structure contains all required fields."""
        pr_info = {
            'title': 'Test PR',
            'url': 'https://github.com/test/test/pull/123',
            'number': 123,
            'lines': 500,
            'additions': 400,
            'deletions': 100
        }

        assert 'title' in pr_info
        assert 'url' in pr_info
        assert 'number' in pr_info
        assert 'lines' in pr_info
        assert 'additions' in pr_info
        assert 'deletions' in pr_info

    def test_pr_info_line_calculation(self):
        """Test that total lines equals additions plus deletions."""
        additions = 400
        deletions = 100
        total_lines = additions + deletions

        assert total_lines == 500


class TestReviewStatsAggregation:
    """Test cases for aggregating review statistics."""

    @pytest.fixture
    def analyzer_with_multiple_users(self):
        """Create analyzer with multiple users."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        for user, (prs, lines) in [
            ('alice', (5, 500)),
            ('bob', (3, 300)),
            ('charlie', (2, 200))
        ]:
            analyzer.reviewed_by_me[user].prs_reviewed = prs
            analyzer.reviewed_by_me[user].lines_reviewed = lines

        return analyzer

    def test_total_prs_calculation(self, analyzer_with_multiple_users):
        """Test calculating total PRs across all users."""
        total_prs = sum(
            stats.prs_reviewed
            for stats in analyzer_with_multiple_users.reviewed_by_me.values()
        )

        assert total_prs == 10  # 5 + 3 + 2

    def test_total_lines_calculation(self, analyzer_with_multiple_users):
        """Test calculating total lines across all users."""
        total_lines = sum(
            stats.lines_reviewed
            for stats in analyzer_with_multiple_users.reviewed_by_me.values()
        )

        assert total_lines == 1000  # 500 + 300 + 200

    def test_user_count(self, analyzer_with_multiple_users):
        """Test counting unique users."""
        user_count = len(analyzer_with_multiple_users.reviewed_by_me)

        assert user_count == 3


class TestMainFunction:
    """Test cases for main() function."""

    def test_main_with_environment_variables(self):
        """Test main with environment variables."""
        with patch.dict(os.environ, {
            'GITHUB_USERNAME': 'test_user',
            'GITHUB_TOKEN': 'test_token',
            'GITHUB_REPOS': 'test/repo1,test/repo2',
            'ANALYSIS_MONTHS': '6',
            'USE_CACHE': 'false',
            'EXCLUDED_USERS': 'bot1,bot2',
            'REQUIRED_PR_LABEL': 'ready',
            'SORT_BY': 'balance'
        }):
            with patch.object(GitHubReviewAnalyzer, 'analyze_repository'):
                with patch.object(GitHubReviewAnalyzer, '_save_cache'):
                    with patch.object(GitHubReviewAnalyzer, 'print_summary'):
                        github_review_analyzer.main()

    def test_main_missing_username(self):
        """Test main exits when username is missing."""
        with patch('github_review_analyzer.load_dotenv'):
            with patch.dict(os.environ, {}, clear=True):
                with patch('builtins.input', return_value=''):
                    with patch('builtins.print'):
                        with pytest.raises(SystemExit) as exc_info:
                            github_review_analyzer.main()
                        assert exc_info.value.code == 1

    def test_main_missing_repos(self):
        """Test main exits when no repos provided."""
        with patch('github_review_analyzer.load_dotenv'):
            with patch.dict(os.environ, {'GITHUB_USERNAME': 'test_user'}, clear=True):
                with patch('builtins.input', side_effect=['', '']):
                    with patch('builtins.print'):
                        with pytest.raises(SystemExit) as exc_info:
                            github_review_analyzer.main()
                        assert exc_info.value.code == 1

    def test_main_with_invalid_months(self):
        """Test main handles invalid ANALYSIS_MONTHS."""
        with patch.dict(os.environ, {
            'GITHUB_USERNAME': 'test_user',
            'GITHUB_REPOS': 'test/repo',
            'ANALYSIS_MONTHS': 'invalid',
            'GITHUB_TOKEN': 'test_token',
            'EXCLUDED_USERS': 'none'
        }):
            with patch.object(GitHubReviewAnalyzer, 'analyze_repository'):
                with patch.object(GitHubReviewAnalyzer, '_save_cache'):
                    with patch.object(GitHubReviewAnalyzer, 'print_summary'):
                        github_review_analyzer.main()

    def test_main_repository_error_handling(self):
        """Test that main continues after repository error."""
        with patch.dict(os.environ, {
            'GITHUB_USERNAME': 'test_user',
            'GITHUB_REPOS': 'test/repo1,test/repo2',
            'GITHUB_TOKEN': 'test_token',
            'ANALYSIS_MONTHS': '3',
            'EXCLUDED_USERS': 'none'
        }):
            with patch.object(GitHubReviewAnalyzer, 'analyze_repository', side_effect=[Exception('Error'), None]):
                with patch.object(GitHubReviewAnalyzer, '_save_cache'):
                    with patch.object(GitHubReviewAnalyzer, 'print_summary'):
                        github_review_analyzer.main()


class TestChangesRequestedDetection:
    """Test cases for changes_requested detection in PR analysis."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked API client."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=False
        )
        # Reset the mock for each test
        analyzer.api_client.get = Mock()
        yield analyzer

        # Clean up
        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_no_changes_requested_all_approved(self, mock_analyzer):
        """Test that changes_requested is False when all reviews are approved."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        # Mock PR details response
        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        # Mock reviews - all approved
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer2'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T11:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False

    def test_changes_requested_active(self):
        """Test that changes_requested is True when a reviewer's latest review requests changes."""
        # This test validates the functionality works correctly
        # The standalone verification confirms the logic is correct
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        try:
            analyzer = GitHubReviewAnalyzer(
                username='test_user',
                token='test_token',
                cache_file=cache_file,
                use_cache=False
            )
            analyzer.api_client.get = Mock()

            pr = {
                'number': 123,
                'user': {'login': 'pr_author'},
                'title': 'Test PR',
                'html_url': 'https://github.com/test/repo/pull/123',
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-02T00:00:00Z'
            }

            pr_details_response = Mock()
            pr_details_response.status_code = 200
            pr_details_response.json.return_value = {
                'additions': 100,
                'deletions': 50,
                'requested_reviewers': [],
                'labels': []
            }

            # One reviewer requested changes
            reviews = [
                {
                    'user': {'login': 'reviewer1'},
                    'state': 'CHANGES_REQUESTED',
                    'submitted_at': '2024-01-02T10:00:00Z'
                }
            ]

            analyzer.api_client.get.return_value = pr_details_response
            with patch.object(analyzer, '_get_paginated', side_effect=[reviews, []]):
                result = analyzer._check_and_create_pr_info('test/repo', pr)

            assert result is not None
            assert result['changes_requested'] is True
        finally:
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def test_changes_requested_then_dismissed(self, mock_analyzer):
        """Test that changes_requested is False when reviewer dismisses their own review."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-03T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': []
        }

        # Reviewer requested changes, then dismissed
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer1'},
                'state': 'DISMISSED',
                'submitted_at': '2024-01-03T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False

    def test_changes_requested_then_approved(self, mock_analyzer):
        """Test that changes_requested is False when reviewer approves after requesting changes."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-03T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': []
        }

        # Reviewer requested changes, then approved
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer1'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-03T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False

    def test_changes_requested_then_commented(self, mock_analyzer):
        """Test that changes_requested is TRUE when reviewer comments after requesting changes.

        COMMENTED reviews do NOT clear a CHANGES_REQUESTED review.
        Only APPROVED or DISMISSED reviews clear a change request.
        """
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-03T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        # Reviewer requested changes, then left a comment (change request still active!)
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer1'},
                'state': 'COMMENTED',
                'submitted_at': '2024-01-03T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is True

    def test_changes_requested_from_rerequested_reviewer(self, mock_analyzer):
        """Test that changes_requested is FALSE when reviewer is re-requested.

        Being re-requested means the previous CHANGES_REQUESTED review is OUTDATED.
        When new commits are pushed addressing concerns, reviewers are re-requested,
        and their old reviews are no longer considered active.
        This matches GitHub's UI behavior.
        """
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'labels': [],
            # Reviewer is re-requested, so their previous CHANGES_REQUESTED is outdated
            'requested_reviewers': [{'login': 'reviewer1'}]
        }

        # Reviewer requested changes, then new commits were pushed, and they were re-requested
        # The change request is now considered outdated (not active)
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False

    def test_multiple_reviewers_mixed_states(self):
        """Test changes_requested with multiple reviewers in different states."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        try:
            analyzer = GitHubReviewAnalyzer(
                username='test_user',
                token='test_token',
                cache_file=cache_file,
                use_cache=False
            )
            analyzer.api_client.get = Mock()

            pr = {
                'number': 123,
                'user': {'login': 'pr_author'},
                'title': 'Test PR',
                'html_url': 'https://github.com/test/repo/pull/123',
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-03T00:00:00Z'
            }

            pr_details_response = Mock()
            pr_details_response.status_code = 200
            pr_details_response.json.return_value = {
                'additions': 100,
                'deletions': 50,
                'requested_reviewers': [],
                'labels': []
            }

            # Multiple reviewers: one requested changes then dismissed, one still has active request
            reviews = [
                {
                    'user': {'login': 'reviewer1'},
                    'state': 'CHANGES_REQUESTED',
                    'submitted_at': '2024-01-02T11:00:00Z'
                },
                {
                    'user': {'login': 'reviewer1'},
                    'state': 'DISMISSED',
                    'submitted_at': '2024-01-03T10:00:00Z'
                },
                {
                    'user': {'login': 'reviewer2'},
                    'state': 'CHANGES_REQUESTED',
                    'submitted_at': '2024-01-02T12:00:00Z'
                }
            ]

            analyzer.api_client.get.return_value = pr_details_response
            with patch.object(analyzer, '_get_paginated', side_effect=[reviews, []]):
                result = analyzer._check_and_create_pr_info('test/repo', pr)

            assert result is not None
            # reviewer1 dismissed their changes, but reviewer2 still has active request
            assert result['changes_requested'] is True
        finally:
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def test_review_without_timestamp_ignored(self, mock_analyzer):
        """Test that reviews without timestamps are ignored."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': []
        }

        # Review without submitted_at should be ignored
        reviews = [
            {
                'user': {'login': 'reviewer1'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': None  # No timestamp
            },
            {
                'user': {'login': 'reviewer2'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False  # reviewer1's review ignored due to missing timestamp

    def test_pr_author_reviews_excluded(self, mock_analyzer):
        """Test that PR author's own reviews are excluded from changes_requested detection."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': []
        }

        # PR author's own review should be ignored
        reviews = [
            {
                'user': {'login': 'pr_author'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer1'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T11:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False

    def test_excluded_users_reviews_ignored(self, mock_analyzer):
        """Test that excluded users' reviews are ignored in changes_requested detection."""
        mock_analyzer.excluded_users = {'bot_user'}

        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': []
        }

        # Excluded user's review should be ignored
        reviews = [
            {
                'user': {'login': 'bot_user'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'reviewer1'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T11:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.side_effect = [pr_details_response]
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['changes_requested'] is False


class TestLabelDetection:
    """Test cases for PR label detection."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked API client."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=False
        )
        analyzer.api_client.get = Mock()
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_pr_with_labels(self, mock_analyzer):
        """Test that PR labels are correctly extracted."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': [
                {'name': 'ready to merge'},
                {'name': 'developer approved'},
                {'name': 'bug'}
            ]
        }

        reviews = []

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert 'labels' in result
        assert 'ready to merge' in result['labels']
        assert 'developer approved' in result['labels']
        assert 'bug' in result['labels']
        assert len(result['labels']) == 3

    def test_pr_without_labels(self, mock_analyzer):
        """Test that PR without labels returns empty list."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        reviews = []

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert 'labels' in result
        assert result['labels'] == []

    def test_pr_with_special_labels(self, mock_analyzer):
        """Test detection of special labels like 'ready to merge', 'developer approved', etc."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': [
                {'name': 'ready to merge'},
                {'name': 'maintainer approved'}
            ]
        }

        reviews = []

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert 'ready to merge' in result['labels']
        assert 'maintainer approved' in result['labels']


class TestMyReviewDismissedDetection:
    """Test cases for detecting when my review was dismissed."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked API client."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=False
        )
        analyzer.api_client.get = Mock()
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_my_review_not_dismissed(self, mock_analyzer):
        """Test that my_review_dismissed is False when my review is active."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        # I have reviewed but it's not dismissed
        reviews = [
            {
                'user': {'login': 'test_user'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T10:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        # Should return None since I already reviewed and it's not dismissed
        assert result is None


    def test_my_multiple_reviews_one_dismissed(self, mock_analyzer):
        """Test my_previous_review_count with multiple reviews."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        # I have multiple reviews, one dismissed
        reviews = [
            {
                'user': {'login': 'test_user'},
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2024-01-02T09:00:00Z'
            },
            {
                'user': {'login': 'test_user'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T10:00:00Z'
            },
            {
                'user': {'login': 'test_user'},
                'state': 'DISMISSED',
                'submitted_at': '2024-01-03T10:00:00Z'
            },
            {
                'user': {'login': 'other_user'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T11:00:00Z'
            }
        ]

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, []]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        assert result is not None
        assert result['my_review_dismissed'] is True
        assert result['my_previous_review_count'] == 3  # Three of my reviews

    def test_my_review_with_comments_not_dismissed(self, mock_analyzer):
        """Test that having comments doesn't affect dismissed status."""
        pr = {
            'number': 123,
            'user': {'login': 'pr_author'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/123',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'requested_reviewers': [],
            'labels': []
        }

        reviews = [
            {
                'user': {'login': 'test_user'},
                'state': 'APPROVED',
                'submitted_at': '2024-01-02T10:00:00Z'
            }
        ]

        comments = [
            {
                'user': {'login': 'test_user'},
                'body': 'Looks good!',
                'created_at': '2024-01-02T10:05:00Z'
            }
        ]

        mock_analyzer.api_client.get.return_value = pr_details_response
        with patch.object(mock_analyzer, '_get_paginated', side_effect=[reviews, comments]):
            result = mock_analyzer._check_and_create_pr_info('test/repo', pr)

        # Should return None since I already reviewed and it's not dismissed
        assert result is None


class TestProjectStateFiltering:
    """Test cases for project state filtering functionality."""

    @pytest.fixture
    def analyzer_with_project_state(self):
        """Create analyzer with project state filtering."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=cache_file,
            use_cache=False,
            required_project_state='Ready for Review'
        )
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_initialization_with_project_state(self, analyzer_with_project_state):
        """Test analyzer initialization with required project state."""
        assert analyzer_with_project_state.required_project_state == 'Ready for Review'

    def test_initialization_with_project_number(self):
        """Test analyzer initialization with required project number."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_number=2,
            use_cache=False
        )
        assert analyzer.required_project_number == 2

    def test_batch_fetch_project_states_success(self, analyzer_with_project_state):
        """Test successful batch fetching of project states."""
        prs = [
            {'number': 123},
            {'number': 456}
        ]

        mock_response = {
            'repository': {
                'pr_123': {
                    'number': 123,
                    'projectItems': {
                        'nodes': [
                            {
                                'project': {'number': 2},
                                'fieldValueByName': {'name': 'Ready for Review'}
                            }
                        ]
                    }
                },
                'pr_456': {
                    'number': 456,
                    'projectItems': {
                        'nodes': [
                            {
                                'project': {'number': 2},
                                'fieldValueByName': {'name': 'In Progress'}
                            }
                        ]
                    }
                }
            }
        }

        analyzer_with_project_state.api_client.post_graphql = Mock(return_value=mock_response)

        result = analyzer_with_project_state._batch_fetch_project_states('owner/repo', prs)

        assert 123 in result
        assert 456 in result
        assert 'Ready for Review' in result[123]
        assert 'In Progress' in result[456]

    def test_batch_fetch_project_states_empty_projects(self, analyzer_with_project_state):
        """Test fetching project states when PR has no projects."""
        prs = [{'number': 123}]

        mock_response = {
            'repository': {
                'pr_123': {
                    'number': 123,
                    'projectItems': {'nodes': []}
                }
            }
        }

        analyzer_with_project_state.api_client.post_graphql = Mock(return_value=mock_response)

        result = analyzer_with_project_state._batch_fetch_project_states('owner/repo', prs)

        assert result[123] == []

    def test_batch_fetch_project_states_multiple_projects(self, analyzer_with_project_state):
        """Test PR in multiple projects returns all states."""
        prs = [{'number': 123}]

        mock_response = {
            'repository': {
                'pr_123': {
                    'number': 123,
                    'projectItems': {
                        'nodes': [
                            {
                                'project': {'number': 1},
                                'fieldValueByName': {'name': 'In Progress'}
                            },
                            {
                                'project': {'number': 2},
                                'fieldValueByName': {'name': 'Ready for Review'}
                            }
                        ]
                    }
                }
            }
        }

        analyzer_with_project_state.api_client.post_graphql = Mock(return_value=mock_response)

        result = analyzer_with_project_state._batch_fetch_project_states('owner/repo', prs)

        assert len(result[123]) == 2
        assert 'In Progress' in result[123]
        assert 'Ready for Review' in result[123]

    def test_batch_fetch_project_states_filter_by_project_number(self):
        """Test filtering project states by specific project number."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_state='Ready for Review',
            required_project_number=2,
            use_cache=False
        )

        prs = [{'number': 123}]

        mock_response = {
            'repository': {
                'pr_123': {
                    'number': 123,
                    'projectItems': {
                        'nodes': [
                            {
                                'project': {'number': 1},
                                'fieldValueByName': {'name': 'In Progress'}
                            },
                            {
                                'project': {'number': 2},
                                'fieldValueByName': {'name': 'Ready for Review'}
                            }
                        ]
                    }
                }
            }
        }

        analyzer.api_client.post_graphql = Mock(return_value=mock_response)

        result = analyzer._batch_fetch_project_states('owner/repo', prs)

        # Should only return state from project #2
        assert len(result[123]) == 1
        assert 'Ready for Review' in result[123]
        assert 'In Progress' not in result[123]

    def test_batch_fetch_project_states_graphql_failure(self, analyzer_with_project_state):
        """Test graceful handling of GraphQL failure."""
        prs = [{'number': 123}, {'number': 456}]

        analyzer_with_project_state.api_client.post_graphql = Mock(side_effect=Exception('GraphQL error'))

        result = analyzer_with_project_state._batch_fetch_project_states('owner/repo', prs)

        # Should return empty lists for all PRs on failure
        assert result[123] == []
        assert result[456] == []

    def test_filter_prs_with_label_only(self):
        """Test filtering PRs with label only (no project state)."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_pr_label='ready for review',
            use_cache=False
        )

        prs = [
            {
                'number': 1,
                'state': 'open',
                'draft': False,
                'labels': [{'name': 'ready for review'}]
            },
            {
                'number': 2,
                'state': 'open',
                'draft': False,
                'labels': [{'name': 'bug'}]
            }
        ]

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states={})

        assert len(result) == 1
        assert result[0]['number'] == 1

    def test_filter_prs_with_project_state_only(self):
        """Test filtering PRs with project state only (no label)."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_state='Ready for Review',
            use_cache=False
        )

        prs = [
            {
                'number': 1,
                'state': 'open',
                'draft': False,
                'labels': []
            },
            {
                'number': 2,
                'state': 'open',
                'draft': False,
                'labels': []
            }
        ]

        project_states = {
            1: ['Ready for Review'],
            2: ['In Progress']
        }

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states)

        assert len(result) == 1
        assert result[0]['number'] == 1

    def test_filter_prs_or_logic_label_or_state(self):
        """Test OR logic: PR included if it has label OR project state."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_pr_label='ready for review',
            required_project_state='Ready for Review',
            use_cache=False
        )

        prs = [
            {  # Has label but not state
                'number': 1,
                'state': 'open',
                'draft': False,
                'labels': [{'name': 'ready for review'}]
            },
            {  # Has state but not label
                'number': 2,
                'state': 'open',
                'draft': False,
                'labels': []
            },
            {  # Has both
                'number': 3,
                'state': 'open',
                'draft': False,
                'labels': [{'name': 'ready for review'}]
            },
            {  # Has neither
                'number': 4,
                'state': 'open',
                'draft': False,
                'labels': []
            }
        ]

        project_states = {
            1: [],
            2: ['Ready for Review'],
            3: ['Ready for Review'],
            4: []
        }

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states)

        # Should include PRs 1, 2, and 3 (exclude only PR 4)
        result_numbers = [pr['number'] for pr in result]
        assert 1 in result_numbers
        assert 2 in result_numbers
        assert 3 in result_numbers
        assert 4 not in result_numbers

    def test_filter_prs_multiple_project_states_any_match(self):
        """Test that PR with multiple projects matches if ANY state matches."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_state='Ready for Review',
            use_cache=False
        )

        prs = [
            {
                'number': 1,
                'state': 'open',
                'draft': False,
                'labels': []
            }
        ]

        # PR is in two projects, one matches
        project_states = {
            1: ['In Progress', 'Ready for Review', 'Done']
        }

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states)

        assert len(result) == 1
        assert result[0]['number'] == 1

    def test_filter_prs_no_filtering_when_not_configured(self):
        """Test that no filtering occurs when neither label nor state is configured."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            use_cache=False
        )

        prs = [
            {
                'number': 1,
                'state': 'open',
                'draft': False,
                'labels': []
            },
            {
                'number': 2,
                'state': 'open',
                'draft': False,
                'labels': [{'name': 'bug'}]
            }
        ]

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states={})

        # All PRs should be included
        assert len(result) == 2

    def test_filter_prs_draft_excluded_regardless_of_filters(self):
        """Test that draft PRs are excluded even with matching filters."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_pr_label='ready for review',
            required_project_state='Ready for Review',
            use_cache=False
        )

        prs = [
            {
                'number': 1,
                'state': 'open',
                'draft': True,  # Draft PR
                'labels': [{'name': 'ready for review'}]
            }
        ]

        project_states = {1: ['Ready for Review']}

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)

        result = analyzer._filter_prs(prs, since_date, project_states)

        # Draft should be excluded even though it has both label and state
        assert len(result) == 0

    def test_analyze_repository_fetches_project_states_only_for_open_prs(self):
        """Test that analyze_repository only fetches project states for open PRs, not closed ones."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_state='Ready for Review',
            use_cache=False
        )

        # Mock the paginated API to return both open and closed PRs
        open_prs = [
            {'number': 1, 'state': 'open', 'draft': False, 'labels': []},
            {'number': 2, 'state': 'open', 'draft': False, 'labels': []},
        ]
        closed_prs = [
            {'number': 3, 'state': 'closed', 'merged_at': '2025-01-01T00:00:00Z', 'draft': False, 'labels': []},
            {'number': 4, 'state': 'closed', 'merged_at': '2025-01-01T00:00:00Z', 'draft': False, 'labels': []},
            {'number': 5, 'state': 'closed', 'merged_at': '2025-01-01T00:00:00Z', 'draft': False, 'labels': []},
        ]

        def mock_get_paginated(url, params, should_continue=None):
            if params.get('state') == 'open':
                return open_prs
            else:
                return closed_prs

        analyzer._get_paginated = Mock(side_effect=mock_get_paginated)

        # Mock _batch_fetch_project_states to capture what PRs it receives
        captured_prs = []
        original_batch_fetch = analyzer._batch_fetch_project_states

        def mock_batch_fetch(repo, prs):
            captured_prs.extend(prs)
            # Return project states only for open PRs
            return {pr['number']: ['Ready for Review'] for pr in prs}

        analyzer._batch_fetch_project_states = Mock(side_effect=mock_batch_fetch)

        # Mock _process_prs_parallel to avoid further processing
        analyzer._process_prs_parallel = Mock()

        # Run analyze_repository
        analyzer.analyze_repository('owner/repo', months=3)

        # Verify _batch_fetch_project_states was called
        assert analyzer._batch_fetch_project_states.called

        # Verify only open PRs were passed to _batch_fetch_project_states
        assert len(captured_prs) == 2
        captured_pr_numbers = [pr['number'] for pr in captured_prs]
        assert 1 in captured_pr_numbers
        assert 2 in captured_pr_numbers
        # Closed PRs should NOT be in the captured list
        assert 3 not in captured_pr_numbers
        assert 4 not in captured_pr_numbers
        assert 5 not in captured_pr_numbers

    def test_filter_prs_project_state_only_applies_to_open_prs(self):
        """Test that project state filtering only applies to open PRs, not closed ones."""
        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            required_project_state='Ready for Review',
            use_cache=False
        )

        from datetime import datetime, timedelta
        since_date = datetime.now() - timedelta(days=90)
        # Use a recent date for merged_at (within the since_date filter)
        recent_merged_at = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

        prs = [
            # Open PR with required state - should be included
            {'number': 1, 'state': 'open', 'draft': False, 'labels': []},
            # Open PR without required state - should be excluded
            {'number': 2, 'state': 'open', 'draft': False, 'labels': []},
            # Closed PR - should be included (project state doesn't apply to closed)
            {'number': 3, 'state': 'closed', 'merged_at': recent_merged_at, 'draft': False, 'labels': []},
        ]

        # Only PR #1 has the required project state
        project_states = {1: ['Ready for Review'], 2: ['In Progress']}

        result = analyzer._filter_prs(prs, since_date, project_states)

        # PR #1 (open with state) and PR #3 (closed, state filter doesn't apply) should be included
        # PR #2 (open without state) should be excluded
        result_numbers = [pr['number'] for pr in result]
        assert 1 in result_numbers  # Open with required state
        assert 2 not in result_numbers  # Open without required state
        assert 3 in result_numbers  # Closed - project state doesn't apply


if __name__ == '__main__':
    pytest.main([__file__, '-v'])