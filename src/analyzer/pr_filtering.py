"""PR filtering methods for GitHubReviewAnalyzer."""

import logging
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed


def _filter_prs(self, all_prs: List[Dict], since_date: datetime, project_states: Dict[int, List[str]] = None) -> List[Dict]:
    """Filter PRs by date, draft status, labels, and project states.

    Args:
        all_prs: List of all PRs
        since_date: Only include PRs merged after this date
        project_states: Dictionary mapping PR number to list of project state names

    Returns:
        Filtered list of PRs
    """
    if project_states is None:
        project_states = {}

    # Deduplicate PRs by number
    seen_pr_numbers = set()
    deduplicated_prs = []
    for pr in all_prs:
        if pr['number'] not in seen_pr_numbers:
            seen_pr_numbers.add(pr['number'])
            deduplicated_prs.append(pr)

    recent_prs = []
    for pr in deduplicated_prs:
        # Check date range
        if pr['state'] == 'open':
            pass  # Include all open PRs
        elif pr.get('merged_at'):
            merged_date = datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
            if merged_date < since_date:
                continue
        else:
            continue  # Skip closed but not merged

        # Skip draft PRs
        if pr.get('draft', False):
            logging.debug(f"Skipping draft PR #{pr['number']}")
            continue

        # Check for required label or project state (OR logic)
        # Note: Project state filter only applies to open PRs (closed PRs are already done)
        if self.required_pr_label or self.required_project_state:
            pr_labels = [label['name'] for label in pr.get('labels', [])]
            is_open = pr['state'] == 'open'

            # Check label match
            has_required_label = self.required_pr_label and self.required_pr_label in pr_labels

            # Check project state match (only for open PRs)
            has_required_state = False
            if is_open and self.required_project_state and pr['number'] in project_states:
                has_required_state = self.required_project_state in project_states[pr['number']]

            # For open PRs: skip if has NEITHER required label NOR required state
            # For closed PRs: skip only if label filter is configured and missing
            if is_open:
                if not (has_required_label or has_required_state):
                    reason = []
                    if self.required_pr_label:
                        reason.append(f"missing label '{self.required_pr_label}'")
                    if self.required_project_state:
                        reason.append(f"missing state '{self.required_project_state}'")
                    logging.debug(f"Skipping PR #{pr['number']} - {' and '.join(reason)}")
                    continue
            else:
                # Closed PRs: only filter by label if configured
                if self.required_pr_label and not has_required_label:
                    logging.debug(f"Skipping PR #{pr['number']} - missing label '{self.required_pr_label}'")
                    continue

        recent_prs.append(pr)

    return recent_prs


def _batch_prefetch_filtered_line_counts(self, repo: str, prs: List[Dict]):
    """Batch-prefetch filtered line counts for all closed PRs in parallel.

    Args:
        repo: Repository name
        prs: List of PRs to prefetch file data for
    """
    if not self.exclude_generated_files:
        return

    # Only prefetch for closed PRs (which will be cached)
    closed_prs = [pr for pr in prs if pr.get('state') == 'closed']

    if not closed_prs:
        return

    print(f"Pre-fetching file data for {len(closed_prs)} closed PRs...")
    prefetched = 0
    max_workers = min(10, len(closed_prs))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pr = {
            executor.submit(self._get_filtered_line_counts, repo, pr['number'], should_cache=True): pr
            for pr in closed_prs
        }

        for future in as_completed(future_to_pr):
            pr = future_to_pr[future]
            try:
                future.result()
                prefetched += 1

                if prefetched % 20 == 0 or prefetched == len(closed_prs):
                    print(f"  Prefetch progress: {prefetched}/{len(closed_prs)} PRs", flush=True)

            except Exception as e:
                logging.warning(f"Error prefetching PR #{pr['number']}: {e}")
                prefetched += 1

    print(f"Pre-fetching complete. Proceeding with PR analysis...")


def _get_filtered_line_counts(self, repo: str, pr_number: int, should_cache: bool) -> Dict[str, int]:
    """Fetch PR files and calculate filtered line counts excluding generated files.

    Args:
        repo: Repository name
        pr_number: PR number
        should_cache: Whether to cache the results

    Returns:
        Dictionary with 'additions' and 'deletions' counts, or None if filtering is disabled
    """
    if not self.exclude_generated_files:
        return None

    # Create cache key for this PR's filtered line counts
    cache_key = f"filtered_lines:{repo}:{pr_number}"

    # Try to get from cache
    if should_cache and cache_key in self.cache_manager:
        cached_data = self.cache_manager.cache[cache_key]
        logging.debug(f"Using cached filtered line counts for PR #{pr_number}")
        return cached_data['data']

    # Fetch files from API
    files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"

    try:
        files = self._get_paginated(files_url, use_cache=False)
        result = self.file_filter.calculate_filtered_line_counts(files)

        # Log the PR number with the result
        logging.info(f"PR #{pr_number}: Filtered line counts: +{result['additions']:,}/-{result['deletions']:,}")

        # Cache only the filtered counts
        if should_cache:
            self.cache_manager.cache[cache_key] = {
                'timestamp': datetime.now().isoformat(),
                'data': result
            }

        return result

    except Exception as e:
        logging.warning(f"Error fetching files for PR #{pr_number}: {e}")
        return None
