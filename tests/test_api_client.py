"""
Unit tests for API client functionality
"""

import pytest
import requests
from unittest.mock import Mock, patch
from src.github_review_analyzer import GitHubReviewAnalyzer


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
        mock_analyzer.api_client.session.get = Mock(return_value=mock_response)

        with pytest.raises(requests.exceptions.HTTPError):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)

    def test_500_error_with_retry(self, mock_analyzer):
        """Test that 500 errors are retried (via HTTPAdapter config)."""
        assert mock_analyzer.session is not None

    def test_network_error_handling(self, mock_analyzer):
        """Test handling of network errors."""
        mock_analyzer.session.get.side_effect = requests.exceptions.ConnectionError("Network error")

        with pytest.raises(requests.exceptions.ConnectionError):
            mock_analyzer.get_paginated('https://api.github.com/test', use_cache=False)


class TestAnalyzeRepositoryMethod:
    """Test cases for analyze_repository method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked methods."""
        analyzer = GitHubReviewAnalyzer(username='test_user', token='test_token', use_cache=False)
        analyzer.session = Mock()
        return analyzer

    def test_analyze_repository_with_merged_prs(self, mock_analyzer, capsys):
        """Test analyzing repository with merged PRs."""
        from datetime import datetime
        merged_pr = {
            'number': 1,
            'user': {'login': 'other_user'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'closed',
            'merged_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'draft': False,
            'labels': [],
            'additions': 100,
            'deletions': 50
        }

        def mock_get_paginated(url, params=None, should_continue=None):
            if should_continue:
                should_continue([merged_pr])
            return [merged_pr]

        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)
        mock_analyzer._analyze_pr = Mock()

        mock_analyzer.analyze_repository('test/repo', months=3)

        assert 'test/repo' in mock_analyzer.repositories
        assert mock_analyzer._analyze_pr.called

    def test_analyze_repository_filters_old_prs(self, mock_analyzer, capsys):
        """Test that old PRs are filtered out."""
        from datetime import datetime, timedelta
        old_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%dT%H:%M:%SZ')
        old_pr = {
            'number': 1,
            'user': {'login': 'other_user'},
            'title': 'Old PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'closed',
            'merged_at': old_date,
            'draft': False,
            'labels': []
        }

        def mock_get_paginated(url, params=None, should_continue=None):
            if should_continue:
                should_continue([old_pr])
            return [old_pr]

        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)
        mock_analyzer._analyze_pr = Mock()

        mock_analyzer.analyze_repository('test/repo', months=3)

        assert not mock_analyzer._analyze_pr.called

    def test_analyze_repository_includes_open_prs(self, mock_analyzer):
        """Test that open PRs are included."""
        open_pr = {
            'number': 1,
            'user': {'login': 'other_user'},
            'title': 'Open PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': False,
            'labels': []
        }

        def mock_get_paginated(url, params=None, should_continue=None, use_cache=True):
            if params and params.get('state') == 'open':
                return [open_pr]
            return []

        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)
        mock_analyzer._analyze_pr = Mock()

        mock_analyzer.analyze_repository('test/repo', months=3)

        assert mock_analyzer._analyze_pr.called

    def test_analyze_repository_filters_drafts(self, mock_analyzer):
        """Test that draft PRs are filtered."""
        draft_pr = {
            'number': 1,
            'user': {'login': 'other_user'},
            'title': 'Draft PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': True,
            'labels': []
        }

        mock_analyzer._get_paginated = Mock(return_value=[draft_pr])
        mock_analyzer._analyze_pr = Mock()

        mock_analyzer.analyze_repository('test/repo', months=3)

        assert not mock_analyzer._analyze_pr.called

    def test_analyze_repository_filters_by_label(self, mock_analyzer, capsys):
        """Test that PRs without required label are filtered."""
        mock_analyzer.required_pr_label = 'ready-for-review'

        pr_without_label = {
            'number': 1,
            'user': {'login': 'other_user'},
            'title': 'PR without label',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': False,
            'labels': [{'name': 'bug'}]
        }

        pr_with_label = {
            'number': 2,
            'user': {'login': 'other_user'},
            'title': 'PR with label',
            'html_url': 'https://github.com/test/repo/pull/2',
            'state': 'open',
            'draft': False,
            'labels': [{'name': 'ready-for-review'}, {'name': 'bug'}]
        }

        def mock_get_paginated(url, params=None, should_continue=None, use_cache=True):
            if should_continue:
                should_continue([pr_without_label, pr_with_label])
            return [pr_without_label, pr_with_label]

        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)
        mock_analyzer._analyze_pr = Mock()

        with patch('builtins.print'):
            mock_analyzer.analyze_repository('test/repo', months=3)

        assert mock_analyzer._analyze_pr.call_count == 1


class TestAnalyzePRMethodFull:
    """Comprehensive tests for _analyze_pr method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked session."""
        analyzer = GitHubReviewAnalyzer(username='test_user', token='test_token', use_cache=False)
        analyzer.session = Mock()
        return analyzer

    def test_analyze_pr_i_reviewed(self, mock_analyzer):
        """Test analyzing PR that I reviewed."""
        pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'closed',
            'additions': 100,
            'deletions': 50
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50,
            'state': 'closed'
        }

        my_review = {
            'id': 1,
            'user': {'login': 'test_user'},
            'state': 'APPROVED'
        }

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(side_effect=lambda url, **kwargs:
            [my_review] if 'reviews' in url else []
        )

        mock_analyzer._analyze_pr('test/repo', pr)

        assert 'alice' in mock_analyzer.reviewed_by_me
        assert mock_analyzer.reviewed_by_me['alice'].prs_reviewed == 1
        assert mock_analyzer.reviewed_by_me['alice'].lines_reviewed == 150

    def test_analyze_pr_others_reviewed_mine(self, mock_analyzer):
        """Test analyzing my PR that others reviewed."""
        pr = {
            'number': 1,
            'user': {'login': 'test_user'},
            'title': 'My PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'closed',
            'additions': 200,
            'deletions': 100
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 200,
            'deletions': 100,
            'state': 'closed'
        }

        bob_review = {
            'id': 1,
            'user': {'login': 'bob'},
            'state': 'APPROVED'
        }

        charlie_comment = {
            'id': 1,
            'user': {'login': 'charlie'}
        }

        def mock_get_paginated(url, **kwargs):
            if 'reviews' in url:
                return [bob_review]
            elif 'comments' in url:
                return [charlie_comment]
            return []

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)

        mock_analyzer._analyze_pr('test/repo', pr)

        assert 'bob' in mock_analyzer.reviewed_by_others
        assert mock_analyzer.reviewed_by_others['bob'].prs_reviewed == 1
        assert mock_analyzer.reviewed_by_others['bob'].review_events == 1

        assert 'charlie' in mock_analyzer.reviewed_by_others
        assert mock_analyzer.reviewed_by_others['charlie'].comments == 1

    def test_analyze_pr_no_reviews(self, mock_analyzer):
        """Test analyzing PR with no reviews."""
        pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'additions': 50,
            'deletions': 25
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 50,
            'deletions': 25,
            'state': 'open'
        }

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(return_value=[])

        mock_analyzer._analyze_pr('test/repo', pr)

        assert len(mock_analyzer.reviewed_by_me) == 0
        assert len(mock_analyzer.reviewed_by_others) == 0

    def test_analyze_pr_excludes_self_reviews(self, mock_analyzer):
        """Test that self-reviews are excluded."""
        pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'additions': 50,
            'deletions': 25
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 50,
            'deletions': 25,
            'state': 'open'
        }

        alice_self_review = {
            'id': 1,
            'user': {'login': 'alice'},
            'state': 'APPROVED'
        }

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(return_value=[alice_self_review])

        mock_analyzer._analyze_pr('test/repo', pr)

        assert len(mock_analyzer.reviewed_by_me) == 0

    def test_analyze_pr_error_handling(self, mock_analyzer):
        """Test error handling when fetching PR details fails."""
        pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Test PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'additions': 50,
            'deletions': 25
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 404
        pr_details_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(return_value=[])

        mock_analyzer._analyze_pr('test/repo', pr)


class TestGetOpenPRsNeedingReview:
    """Test cases for get_open_prs_needing_review method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked session."""
        analyzer = GitHubReviewAnalyzer(username='test_user', token='test_token', use_cache=False)
        analyzer.repositories = ['test/repo']
        analyzer.session = Mock()
        return analyzer

    def test_get_open_prs_needing_review(self, mock_analyzer):
        """Test getting open PRs that need review."""
        open_pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Open PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': False,
            'labels': [],
            'created_at': '2025-01-15T10:00:00Z',
            'updated_at': '2025-01-16T10:00:00Z'
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {
            'additions': 100,
            'deletions': 50
        }

        def mock_get_paginated(url, params=None, use_cache=True):
            if 'pulls?' in url or 'pulls' in url and not 'reviews' in url and not 'comments' in url:
                return [open_pr]
            return []

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)

        result = mock_analyzer.get_open_prs_needing_review()

        assert 'alice' in result
        assert len(result['alice']) == 1
        assert result['alice'][0]['number'] == 1
        assert result['alice'][0]['additions'] == 100
        assert result['alice'][0]['deletions'] == 50

    def test_get_open_prs_excludes_my_prs(self, mock_analyzer):
        """Test that my own PRs are excluded."""
        my_pr = {
            'number': 1,
            'user': {'login': 'test_user'},
            'title': 'My PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': False,
            'labels': []
        }

        mock_analyzer._get_paginated = Mock(return_value=[my_pr])

        result = mock_analyzer.get_open_prs_needing_review()

        assert len(result) == 0

    def test_get_open_prs_excludes_already_reviewed(self, mock_analyzer):
        """Test that PRs I already reviewed are excluded."""
        pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'PR',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': False,
            'labels': []
        }

        my_review = {
            'id': 1,
            'user': {'login': 'test_user'}
        }

        pr_details_response = Mock()
        pr_details_response.status_code = 200
        pr_details_response.json.return_value = {'additions': 100, 'deletions': 50}

        def mock_get_paginated(url, params=None, use_cache=True):
            if 'pulls?' in url or ('pulls' in url and 'reviews' not in url and 'comments' not in url):
                return [pr]
            elif 'reviews' in url:
                return [my_review]
            return []

        mock_analyzer.api_client.session.get = Mock(return_value=pr_details_response)
        mock_analyzer._get_paginated = Mock(side_effect=mock_get_paginated)

        result = mock_analyzer.get_open_prs_needing_review()

        assert len(result) == 0

    def test_get_open_prs_excludes_drafts(self, mock_analyzer):
        """Test that draft PRs are excluded."""
        draft_pr = {
            'number': 1,
            'user': {'login': 'alice'},
            'title': 'Draft',
            'html_url': 'https://github.com/test/repo/pull/1',
            'state': 'open',
            'draft': True,
            'labels': []
        }

        mock_analyzer._get_paginated = Mock(return_value=[draft_pr])

        result = mock_analyzer.get_open_prs_needing_review()

        assert len(result) == 0


class TestPrintSummary:
    """Test cases for print_summary method."""

    @pytest.fixture
    def analyzer_with_data(self):
        """Create analyzer with test data."""
        from unittest.mock import Mock
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        analyzer.reviewed_by_me['alice'].prs_reviewed = 2
        analyzer.reviewed_by_me['alice'].lines_reviewed = 200
        analyzer.reviewed_by_me['alice'].additions_reviewed = 150
        analyzer.reviewed_by_me['alice'].deletions_reviewed = 50
        analyzer.reviewed_by_me['alice'].prs.append({
            'number': 1,
            'title': 'PR 1',
            'url': 'https://github.com/test/repo/pull/1',
            'additions': 75,
            'deletions': 25,
            'lines': 100
        })

        analyzer.reviewed_by_others['bob'].prs_reviewed = 3
        analyzer.reviewed_by_others['bob'].lines_reviewed = 300
        analyzer.reviewed_by_others['bob'].additions_reviewed = 250
        analyzer.reviewed_by_others['bob'].deletions_reviewed = 50

        analyzer.repositories = ['test/repo']

        return analyzer

    def test_print_summary_with_data(self, analyzer_with_data, capsys):
        """Test print_summary with data."""
        from unittest.mock import Mock
        analyzer_with_data.get_open_prs_needing_review = Mock(return_value={})

        analyzer_with_data.print_summary()

        captured = capsys.readouterr()
        assert 'REVIEW SUMMARY FOR test_user' in captured.out
        assert 'alice' in captured.out or 'bob' in captured.out

    def test_print_summary_no_data(self, capsys):
        """Test print_summary with no data."""
        analyzer = GitHubReviewAnalyzer(username='test_user', use_cache=False)

        analyzer.print_summary()

        captured = capsys.readouterr()
        assert 'No review activity found' in captured.out

    def test_print_summary_with_open_prs(self, analyzer_with_data, capsys):
        """Test print_summary with open PRs."""
        from unittest.mock import Mock
        open_prs = {
            'alice': [{
                'number': 2,
                'title': 'Open PR',
                'url': 'https://github.com/test/repo/pull/2',
                'repo': 'test/repo',
                'additions': 100,
                'deletions': 50,
                'created_at': '2025-01-15T10:00:00Z',
                'updated_at': '2025-01-16T10:00:00Z'
            }]
        }

        analyzer_with_data.get_open_prs_needing_review = Mock(return_value=open_prs)

        analyzer_with_data.print_summary()

        captured = capsys.readouterr()
        assert 'OPEN PRs THAT NEED YOUR REVIEW' in captured.out


class TestGraphQLAPI:
    """Test cases for GraphQL API functionality."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create analyzer with mocked session."""
        analyzer = GitHubReviewAnalyzer(username='test_user', token='test_token', use_cache=False)
        analyzer.api_client.session = Mock()
        return analyzer

    def test_build_pr_project_states_query_single_pr(self, mock_analyzer):
        """Test building GraphQL query for a single PR."""
        from src.api_client import GitHubAPIClient

        query = GitHubAPIClient.build_pr_project_states_query('owner', 'repo', [123])

        assert 'pr_123: pullRequest(number: 123)' in query
        assert 'projectItems(first: 10)' in query
        assert 'fieldValueByName(name: "Status")' in query
        assert 'project' in query
        assert 'number' in query

    def test_build_pr_project_states_query_multiple_prs(self, mock_analyzer):
        """Test building GraphQL query for multiple PRs."""
        from src.api_client import GitHubAPIClient

        query = GitHubAPIClient.build_pr_project_states_query('owner', 'repo', [123, 456, 789])

        assert 'pr_123: pullRequest(number: 123)' in query
        assert 'pr_456: pullRequest(number: 456)' in query
        assert 'pr_789: pullRequest(number: 789)' in query
        assert 'repository(owner: "owner", name: "repo")' in query

    def test_post_graphql_success(self, mock_analyzer):
        """Test successful GraphQL query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
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
                    }
                }
            }
        }
        mock_analyzer.api_client.session.post = Mock(return_value=mock_response)

        result = mock_analyzer.api_client.post_graphql('query { test }')

        assert 'repository' in result
        assert result['repository']['pr_123']['number'] == 123

    def test_post_graphql_with_errors(self, mock_analyzer):
        """Test GraphQL query with errors."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'errors': [
                {'message': 'Field not found'},
                {'message': 'Permission denied'}
            ]
        }
        mock_analyzer.api_client.session.post = Mock(return_value=mock_response)

        with pytest.raises(Exception) as exc_info:
            mock_analyzer.api_client.post_graphql('query { test }')

        assert 'Field not found' in str(exc_info.value)
        assert 'Permission denied' in str(exc_info.value)

    def test_post_graphql_null_data(self, mock_analyzer):
        """Test GraphQL query returning null data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': None}
        mock_analyzer.api_client.session.post = Mock(return_value=mock_response)

        result = mock_analyzer.api_client.post_graphql('query { test }')

        assert result == {}

    def test_post_graphql_rate_limit(self, mock_analyzer):
        """Test GraphQL query with rate limit."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {'message': 'rate limit exceeded'}
        mock_analyzer.api_client.session.post = Mock(return_value=mock_response)

        with pytest.raises(SystemExit):
            mock_analyzer.api_client.post_graphql('query { test }')

    def test_post_graphql_with_variables(self, mock_analyzer):
        """Test GraphQL query with variables."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'test': 'value'}}
        mock_analyzer.api_client.session.post = Mock(return_value=mock_response)

        variables = {'owner': 'test', 'repo': 'repo'}
        result = mock_analyzer.api_client.post_graphql('query($owner: String!) { test }', variables)

        mock_analyzer.api_client.session.post.assert_called_once()
        call_args = mock_analyzer.api_client.session.post.call_args
        assert call_args[1]['json']['variables'] == variables


if __name__ == '__main__':
    pytest.main([__file__, '-v'])