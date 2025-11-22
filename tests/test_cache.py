"""
Unit tests for caching functionality
"""

import pytest
import os
import tempfile
from datetime import datetime, timedelta
from src.github_review_analyzer import GitHubReviewAnalyzer


class TestCacheFunctionality:
    """Test cases for basic cache operations."""

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
        """Create analyzer with caching enabled."""
        return GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=temp_cache_file,
            use_cache=True
        )

    @pytest.fixture
    def analyzer_no_cache(self, temp_cache_file):
        """Create analyzer with caching disabled."""
        return GitHubReviewAnalyzer(
            username='test_user',
            token='test_token',
            cache_file=temp_cache_file,
            use_cache=False
        )

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

        assert analyzer_no_cache.cache == {'test': 'data'}

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

        analyzer._put_in_cache(cache_key, data)
        retrieved = analyzer._get_from_cache(cache_key)
        assert retrieved == data

    def test_get_from_cache_miss(self, analyzer):
        """Test cache miss returns None."""
        result = analyzer._get_from_cache('non_existent_key')
        assert result is None


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

        analyzer_with_cache._put_in_cache(cache_key, data)
        result = analyzer_with_cache._get_from_cache(cache_key)
        assert result == data

    def test_cache_timestamp_format(self, analyzer_with_cache):
        """Test that cache timestamp is in correct format."""
        cache_key = 'test_key'
        data = [{'id': 1}]

        analyzer_with_cache._put_in_cache(cache_key, data)

        timestamp_str = analyzer_with_cache.cache[cache_key]['timestamp']
        timestamp = datetime.fromisoformat(timestamp_str)
        assert isinstance(timestamp, datetime)


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
        key1 = analyzer._get_cache_key('repo', 'endpoint', {'a': '1', 'b': '2'})
        key2 = analyzer._get_cache_key('repo', 'endpoint', {'b': '2', 'a': '1'})

        assert key1 == key2


class TestCacheEdgeCases:
    """Additional tests for cache edge cases."""

    def test_save_cache_exception_handling(self):
        """Test that _save_cache handles exceptions gracefully."""
        analyzer = GitHubReviewAnalyzer(username='test_user', cache_file='/invalid/path/cache.json', use_cache=True)
        analyzer.cache = {'test': 'data'}

        # Should not crash
        analyzer._save_cache()

    def test_put_in_cache_when_disabled(self):
        """Test that _put_in_cache does nothing when cache is disabled."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        analyzer._put_in_cache('key', [{'data': 'test'}])

        # Cache should still be empty
        assert len(analyzer.cache) == 0

    def test_get_paginated_uses_cache(self):
        """Test that get_paginated uses cache when available."""
        from unittest.mock import Mock
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=True)

        # Put data in cache
        test_data = [{'id': 1}, {'id': 2}]
        cache_key = analyzer._get_cache_key('', 'https://api.github.com/test', {})
        analyzer._put_in_cache(cache_key, test_data)

        # Mock session to ensure it's not called
        analyzer.session = Mock()

        # Fetch data - should come from cache
        result = analyzer.get_paginated('https://api.github.com/test', use_cache=True)

        assert result == test_data
        assert not analyzer.session.get.called

    def test_get_paginated_saves_to_cache(self):
        """Test that get_paginated saves data to cache."""
        from unittest.mock import Mock
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=True)

        # Mock session
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1}]
        mock_session.get.return_value = mock_response
        analyzer.session = mock_session

        result = analyzer.get_paginated('https://api.github.com/test', use_cache=True)

        # Check cache was populated
        cache_key = analyzer._get_cache_key('', 'https://api.github.com/test', {})
        assert cache_key in analyzer.cache
        assert analyzer.cache[cache_key]['data'] == [{'id': 1}]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])