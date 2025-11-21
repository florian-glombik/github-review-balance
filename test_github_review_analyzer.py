"""
Unit tests for GitHub PR Review Analyzer
"""

import pytest
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])