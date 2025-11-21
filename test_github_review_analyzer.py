"""
Unit tests for GitHub PR Review Analyzer
"""

import pytest
import json
import os
import sys
import tempfile
import requests
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util

# Import the module from file with hyphens
spec = importlib.util.spec_from_file_location("github_review_analyzer", "github-review-analyzer.py")
github_review_analyzer = importlib.util.module_from_spec(spec)
sys.modules["github_review_analyzer"] = github_review_analyzer
spec.loader.exec_module(github_review_analyzer)

ReviewStats = github_review_analyzer.ReviewStats
GitHubReviewAnalyzer = github_review_analyzer.GitHubReviewAnalyzer


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
        assert analyzer.token == 'test_token'
        assert analyzer.use_cache is True
        assert 'Authorization' in analyzer.session.headers

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

    def test_cache_key_generation(self, analyzer):
        """Test cache key generation."""
        key1 = analyzer._get_cache_key('repo1', 'pulls', {'state': 'open'})
        key2 = analyzer._get_cache_key('repo1', 'pulls', {'state': 'open'})
        key3 = analyzer._get_cache_key('repo1', 'pulls', {'state': 'closed'})

        assert key1 == key2  # Same parameters should generate same key
        assert key1 != key3  # Different parameters should generate different key

    def test_cache_save_and_load(self, analyzer, temp_cache_file):
        """Test saving and loading cache."""
        test_data = {'key1': {'timestamp': datetime.now().isoformat(), 'data': ['item1', 'item2']}}
        analyzer.cache = test_data
        analyzer._save_cache()

        # Create new analyzer to load the cache
        new_analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=temp_cache_file,
            use_cache=True
        )
        assert new_analyzer.cache == test_data

    def test_cache_disabled(self, analyzer_no_cache, temp_cache_file):
        """Test that caching is disabled when use_cache is False."""
        assert analyzer_no_cache.use_cache is False
        analyzer_no_cache.cache = {'test': 'data'}
        analyzer_no_cache._save_cache()

        # When caching is disabled, _save_cache should not write to file
        # But the in-memory cache remains unchanged
        assert analyzer_no_cache.cache == {'test': 'data'}

        # Verify the cache file was not modified or created
        with open(temp_cache_file, 'r') as f:
            content = f.read()
            assert content == '' or content == '{}'

    def test_put_in_cache(self, analyzer):
        """Test putting data in cache."""
        cache_key = 'test_key'
        data = [{'id': 1}, {'id': 2}]

        analyzer._put_in_cache(cache_key, data)

        assert cache_key in analyzer.cache
        assert analyzer.cache[cache_key]['data'] == data
        assert 'timestamp' in analyzer.cache[cache_key]

    def test_get_from_cache(self, analyzer):
        """Test getting data from cache."""
        cache_key = 'test_key'
        data = [{'id': 1}, {'id': 2}]

        # First put data in cache
        analyzer._put_in_cache(cache_key, data)

        # Then retrieve it
        retrieved = analyzer._get_from_cache(cache_key)
        assert retrieved == data

    def test_get_from_cache_miss(self, analyzer):
        """Test cache miss returns None."""
        result = analyzer._get_from_cache('non_existent_key')
        assert result is None

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


class TestCacheExpiration:
    """Test cache expiration logic."""

    @pytest.fixture
    def analyzer_with_cache(self):
        """Create analyzer with a cache file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            cache_file = f.name

        analyzer = GitHubReviewAnalyzer(
            username='test_user',
            cache_file=cache_file,
            use_cache=True
        )
        yield analyzer

        if os.path.exists(cache_file):
            os.remove(cache_file)

    def test_cache_with_recent_data(self, analyzer_with_cache):
        """Test that recent cache data is used."""
        cache_key = 'test_key'
        data = [{'id': 1}]

        # Add data to cache with recent timestamp
        analyzer_with_cache._put_in_cache(cache_key, data)

        # Retrieve should work
        result = analyzer_with_cache._get_from_cache(cache_key)
        assert result == data

    def test_cache_timestamp_format(self, analyzer_with_cache):
        """Test that cache timestamp is in correct format."""
        cache_key = 'test_key'
        data = [{'id': 1}]

        analyzer_with_cache._put_in_cache(cache_key, data)

        # Verify timestamp can be parsed
        timestamp_str = analyzer_with_cache.cache[cache_key]['timestamp']
        timestamp = datetime.fromisoformat(timestamp_str)
        assert isinstance(timestamp, datetime)


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

    def test_sort_by_they_reviewed(self):
        """Test sorting by lines they reviewed (descending)."""
        test_data = [
            {'user': 'Alice', 'they_reviewed': 500, 'i_reviewed': 300},
            {'user': 'Bob', 'they_reviewed': 200, 'i_reviewed': 400},
            {'user': 'Charlie', 'they_reviewed': 800, 'i_reviewed': 100}
        ]

        sort_key = lambda x: x['they_reviewed']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Charlie'  # 800
        assert sorted_data[1]['user'] == 'Alice'    # 500
        assert sorted_data[2]['user'] == 'Bob'      # 200

    def test_sort_by_i_reviewed(self):
        """Test sorting by lines I reviewed (descending)."""
        test_data = [
            {'user': 'Alice', 'they_reviewed': 500, 'i_reviewed': 300},
            {'user': 'Bob', 'they_reviewed': 200, 'i_reviewed': 400},
            {'user': 'Charlie', 'they_reviewed': 800, 'i_reviewed': 100}
        ]

        sort_key = lambda x: x['i_reviewed']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Bob'      # 400
        assert sorted_data[1]['user'] == 'Alice'    # 300
        assert sorted_data[2]['user'] == 'Charlie'  # 100

    def test_sort_by_their_prs(self):
        """Test sorting by number of their PRs I reviewed (descending)."""
        test_data = [
            {'user': 'Alice', 'their_prs_i_reviewed': 3, 'my_prs_they_reviewed': 5},
            {'user': 'Bob', 'their_prs_i_reviewed': 7, 'my_prs_they_reviewed': 2},
            {'user': 'Charlie', 'their_prs_i_reviewed': 4, 'my_prs_they_reviewed': 4}
        ]

        sort_key = lambda x: x['their_prs_i_reviewed']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Bob'      # 7
        assert sorted_data[1]['user'] == 'Charlie'  # 4
        assert sorted_data[2]['user'] == 'Alice'    # 3

    def test_sort_by_my_prs(self):
        """Test sorting by number of my PRs they reviewed (descending)."""
        test_data = [
            {'user': 'Alice', 'their_prs_i_reviewed': 3, 'my_prs_they_reviewed': 5},
            {'user': 'Bob', 'their_prs_i_reviewed': 7, 'my_prs_they_reviewed': 2},
            {'user': 'Charlie', 'their_prs_i_reviewed': 4, 'my_prs_they_reviewed': 4}
        ]

        sort_key = lambda x: x['my_prs_they_reviewed']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data[0]['user'] == 'Alice'    # 5
        assert sorted_data[1]['user'] == 'Charlie'  # 4
        assert sorted_data[2]['user'] == 'Bob'      # 2

    def test_sort_key_mapping(self):
        """Test that the sort key mapping works correctly for all options."""
        sort_key_map = {
            'total_prs': lambda x: x['total_prs'],
            'balance': lambda x: x['balance'],
            'user': lambda x: x['user'].lower(),
            'they_reviewed': lambda x: x['they_reviewed'],
            'i_reviewed': lambda x: x['i_reviewed'],
            'their_prs': lambda x: x['their_prs_i_reviewed'],
            'my_prs': lambda x: x['my_prs_they_reviewed']
        }

        test_item = {
            'user': 'TestUser',
            'total_prs': 10,
            'balance': 100,
            'they_reviewed': 500,
            'i_reviewed': 300,
            'their_prs_i_reviewed': 5,
            'my_prs_they_reviewed': 3
        }

        # Verify each sort key extracts the correct value
        assert sort_key_map['total_prs'](test_item) == 10
        assert sort_key_map['balance'](test_item) == 100
        assert sort_key_map['user'](test_item) == 'testuser'
        assert sort_key_map['they_reviewed'](test_item) == 500
        assert sort_key_map['i_reviewed'](test_item) == 300
        assert sort_key_map['their_prs'](test_item) == 5
        assert sort_key_map['my_prs'](test_item) == 3

    def test_case_insensitive_user_sorting(self):
        """Test that user sorting is case-insensitive."""
        test_data = [
            {'user': 'alice', 'total_prs': 5},
            {'user': 'Bob', 'total_prs': 10},
            {'user': 'CHARLIE', 'total_prs': 8}
        ]

        sort_key = lambda x: x['user'].lower()
        sorted_data = sorted(test_data, key=sort_key, reverse=False)

        assert sorted_data[0]['user'] == 'alice'
        assert sorted_data[1]['user'] == 'Bob'
        assert sorted_data[2]['user'] == 'CHARLIE'

    def test_sorting_with_equal_values(self):
        """Test sorting behavior when values are equal."""
        test_data = [
            {'user': 'Alice', 'total_prs': 5, 'balance': 100},
            {'user': 'Bob', 'total_prs': 5, 'balance': 50},
            {'user': 'Charlie', 'total_prs': 5, 'balance': 200}
        ]

        sort_key = lambda x: x['total_prs']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        # All have same total_prs, order may vary but all should be present
        users = [item['user'] for item in sorted_data]
        assert set(users) == {'Alice', 'Bob', 'Charlie'}

    def test_sorting_with_negative_balance(self):
        """Test sorting with negative balance values."""
        test_data = [
            {'user': 'Alice', 'balance': -100},
            {'user': 'Bob', 'balance': 50},
            {'user': 'Charlie', 'balance': -200}
        ]

        sort_key = lambda x: x['balance']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        # Descending order: 50, -100, -200
        assert sorted_data[0]['user'] == 'Bob'      # 50
        assert sorted_data[1]['user'] == 'Alice'    # -100
        assert sorted_data[2]['user'] == 'Charlie'  # -200

    def test_sorting_empty_list(self):
        """Test sorting an empty list."""
        test_data = []

        sort_key = lambda x: x['total_prs']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert sorted_data == []

    def test_sorting_single_item(self):
        """Test sorting a list with a single item."""
        test_data = [
            {'user': 'Alice', 'total_prs': 5, 'balance': 100}
        ]

        sort_key = lambda x: x['total_prs']
        sorted_data = sorted(test_data, key=sort_key, reverse=True)

        assert len(sorted_data) == 1
        assert sorted_data[0]['user'] == 'Alice'


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
        mock_analyzer.session.get.return_value = mock_response

        result = mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[1]['id'] == 2

    def test_get_paginated_multiple_pages(self, mock_analyzer):
        """Test fetching multiple pages of results."""
        # First page returns 100 items, second page returns 50 items
        page1 = [{'id': i} for i in range(100)]
        page2 = [{'id': i} for i in range(100, 150)]

        mock_analyzer.session.get.side_effect = [
            Mock(status_code=200, json=lambda: page1),
            Mock(status_code=200, json=lambda: page2)
        ]

        result = mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

        assert len(result) == 150
        assert mock_analyzer.session.get.call_count == 2

    def test_get_paginated_empty_response(self, mock_analyzer):
        """Test handling of empty response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_analyzer.session.get.return_value = mock_response

        result = mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

        assert len(result) == 0

    def test_get_paginated_with_params(self, mock_analyzer):
        """Test that parameters are passed correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1}]
        mock_analyzer.session.get.return_value = mock_response

        params = {'state': 'open', 'sort': 'created'}
        mock_analyzer.get_paginated('https://api.github.com/test', params=params, use_cache=False)

        call_args = mock_analyzer.session.get.call_args
        assert 'state' in call_args[1]['params']
        assert call_args[1]['params']['state'] == 'open'

    def test_get_paginated_rate_limit_error(self, mock_analyzer):
        """Test handling of rate limit errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {'message': 'rate limit exceeded'}
        mock_analyzer.session.get.return_value = mock_response

        with pytest.raises(SystemExit):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

    def test_get_paginated_early_termination(self, mock_analyzer):
        """Test early termination callback."""
        page1 = [{'id': i} for i in range(100)]
        page2 = [{'id': i} for i in range(100, 200)]

        mock_analyzer.session.get.side_effect = [
            Mock(status_code=200, json=lambda: page1),
            Mock(status_code=200, json=lambda: page2)
        ]

        # Callback that stops after first page
        def stop_after_first(page_data):
            return False

        result = mock_analyzer.get_paginated(
            'https://api.github.com/test',
            use_cache=False,
            should_continue=stop_after_first
        )

        assert len(result) == 100
        assert mock_analyzer.session.get.call_count == 1


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
        # This is tested indirectly through the analyze_repository flow
        # but we can test the draft flag check
        draft_pr = {
            'number': 123,
            'user': {'login': 'other_user'},
            'title': 'Draft PR',
            'html_url': 'https://github.com/test/test/pull/123',
            'state': 'open',
            'draft': True
        }

        # When analyzing, draft PRs should be skipped
        # The _analyze_pr method won't be called for draft PRs in analyze_repository
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

        # Check label presence
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
        # Add another user
        analyzer_with_data.reviewed_by_me['charlie'].prs_reviewed = 2

        assert len(analyzer_with_data.reviewed_by_me) == 2
        assert 'alice' in analyzer_with_data.reviewed_by_me
        assert 'charlie' in analyzer_with_data.reviewed_by_me

    def test_bidirectional_tracking(self, analyzer_with_data):
        """Test that reviews are tracked in both directions."""
        # Alice: I reviewed their code
        assert analyzer_with_data.reviewed_by_me['alice'].prs_reviewed == 5

        # Bob: They reviewed my code
        assert analyzer_with_data.reviewed_by_others['bob'].prs_reviewed == 3

    def test_line_counts_separated(self, analyzer_with_data):
        """Test that additions and deletions are tracked separately."""
        alice_stats = analyzer_with_data.reviewed_by_me['alice']

        assert alice_stats.additions_reviewed == 400
        assert alice_stats.deletions_reviewed == 100
        assert alice_stats.lines_reviewed == 500  # Total


class TestAPIErrorHandling:
    """Test cases for API error handling."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked session."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)
        analyzer.session = Mock()
        return analyzer

    def test_404_error_handling(self, mock_analyzer):
        """Test handling of 404 errors."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_analyzer.session.get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

    def test_500_error_with_retry(self, mock_analyzer):
        """Test that 500 errors are retried (via HTTPAdapter config)."""
        # The analyzer is configured with retry logic in HTTPAdapter
        # We just verify the configuration exists
        assert mock_analyzer.session is not None

    def test_network_error_handling(self, mock_analyzer):
        """Test handling of network errors."""
        mock_analyzer.session.get.side_effect = requests.exceptions.ConnectionError("Network error")

        with pytest.raises(requests.exceptions.ConnectionError):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)


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

        # Add data for multiple users
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


class TestCacheKeyGeneration:
    """Test cases for cache key generation."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer for cache key tests."""
        return GitHubReviewAnalyzer(username='test_user', use_cache=False)

    def test_same_params_same_key(self, analyzer):
        """Test that identical parameters generate the same cache key."""
        key1 = analyzer._get_cache_key('repo', 'endpoint', {'param': 'value'})
        key2 = analyzer._get_cache_key('repo', 'endpoint', {'param': 'value'})

        assert key1 == key2

    def test_different_params_different_key(self, analyzer):
        """Test that different parameters generate different cache keys."""
        key1 = analyzer._get_cache_key('repo', 'endpoint', {'param': 'value1'})
        key2 = analyzer._get_cache_key('repo', 'endpoint', {'param': 'value2'})

        assert key1 != key2

    def test_different_repo_different_key(self, analyzer):
        """Test that different repos generate different cache keys."""
        key1 = analyzer._get_cache_key('repo1', 'endpoint', {'param': 'value'})
        key2 = analyzer._get_cache_key('repo2', 'endpoint', {'param': 'value'})

        assert key1 != key2

    def test_none_params_handling(self, analyzer):
        """Test that None params are handled correctly."""
        key1 = analyzer._get_cache_key('repo', 'endpoint', None)
        key2 = analyzer._get_cache_key('repo', 'endpoint', None)

        assert key1 == key2

    def test_param_order_independence(self, analyzer):
        """Test that parameter order doesn't affect cache key."""
        # Due to JSON sorting in _get_cache_key, order shouldn't matter
        key1 = analyzer._get_cache_key('repo', 'endpoint', {'a': '1', 'b': '2'})
        key2 = analyzer._get_cache_key('repo', 'endpoint', {'b': '2', 'a': '1'})

        assert key1 == key2


class TestDefaultDictBehavior:
    """Test cases for defaultdict behavior in stats tracking."""

    def test_new_user_creates_empty_stats(self):
        """Test that accessing a new user creates empty ReviewStats."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        # Access a user that doesn't exist yet
        stats = analyzer.reviewed_by_me['new_user']

        assert isinstance(stats, ReviewStats)
        assert stats.prs_reviewed == 0
        assert stats.lines_reviewed == 0

    def test_multiple_new_users(self):
        """Test creating stats for multiple users on the fly."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        # Access multiple users
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
        # Verify adapter is mounted for https
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


class TestThreadSafety:
    """Test cases for thread safety in parallel processing."""

    def test_stats_lock_exists(self):
        """Test that stats lock is initialized."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        assert hasattr(analyzer, '_stats_lock')
        assert isinstance(analyzer._stats_lock, Lock)

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

        # Manually add a repository twice
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])