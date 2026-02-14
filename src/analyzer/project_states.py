"""Project state fetching methods for GitHubReviewAnalyzer."""

import logging
from typing import Dict, List
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed


def _batch_fetch_project_states(self, repo: str, prs: List[Dict]) -> Dict[int, List[str]]:
    """Batch-fetch project states for multiple PRs using GraphQL.

    Args:
        repo: Repository name (format: owner/repo)
        prs: List of PRs to fetch project states for

    Returns:
        Dictionary mapping PR number to list of project state names
        Returns empty dict if GraphQL query fails
    """
    if not self.required_project_state:
        return {}

    repo_owner, repo_name = repo.split('/')
    pr_numbers = [pr['number'] for pr in prs]

    # Split into batches of 50 to avoid query complexity limits
    batch_size = 50
    batches = [pr_numbers[i:i+batch_size] for i in range(0, len(pr_numbers), batch_size)]

    if not batches:
        return {}

    all_results = {}
    results_lock = Lock()
    first_error_logged = [False]  # Use list for mutable reference in closure

    def fetch_batch(batch: List[int], batch_index: int) -> Dict[int, List[str]]:
        """Fetch project states for a single batch of PRs."""
        batch_results = {}
        try:
            # Build and execute GraphQL query
            query = self.api_client.build_pr_project_states_query(repo_owner, repo_name, batch)
            logging.debug(f"Executing GraphQL query for batch {batch_index + 1}")
            result = self.api_client.post_graphql(query)

            # Check if we got valid data
            if not result:
                logging.warning(f"GraphQL query returned empty result for batch starting at PR {batch[0]}")
                for pr_num in batch:
                    batch_results[pr_num] = []
                return batch_results

            # Parse results
            repo_data = result.get('repository', {})
            for pr_num in batch:
                pr_key = f'pr_{pr_num}'
                pr_data = repo_data.get(pr_key)

                if not pr_data:
                    batch_results[pr_num] = []
                    continue

                # Extract all status values from all projects this PR is in
                states = []
                project_items = pr_data.get('projectItems', {}).get('nodes', [])
                for item in project_items:
                    # Filter by project number if specified
                    if self.required_project_number:
                        project_info = item.get('project', {})
                        project_num = project_info.get('number')
                        if project_num != self.required_project_number:
                            logging.debug(f"PR #{pr_num} skipping project #{project_num} (looking for #{self.required_project_number})")
                            continue

                    status_field = item.get('fieldValueByName')
                    if status_field and status_field.get('name'):
                        states.append(status_field['name'])

                batch_results[pr_num] = states
                if states:
                    logging.debug(f"PR #{pr_num} project states: {states}")
                else:
                    logging.debug(f"PR #{pr_num} has no matching project states")

        except Exception as e:
            error_msg = str(e)
            logging.warning(f"Failed to fetch project states for batch: {error_msg}")

            # Provide helpful guidance on first error (thread-safe)
            with results_lock:
                if not first_error_logged[0]:
                    first_error_logged[0] = True
                    logging.warning("Project state fetching requires:")
                    logging.warning("  1. GitHub token with 'project' read permission (repo scope + project scope)")
                    logging.warning("  2. Repository using GitHub Projects v2 (not v1 or classic projects)")
                    logging.warning("  3. PRs must be added to a project board with a 'Status' field")
                    logging.warning("Continuing with label-only filtering...")

            # Return empty results for PRs in this failed batch
            for pr_num in batch:
                batch_results[pr_num] = []

        return batch_results

    # Fetch all batches in parallel
    with ThreadPoolExecutor(max_workers=min(len(batches), 10)) as executor:
        futures = {
            executor.submit(fetch_batch, batch, idx): batch
            for idx, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            batch_results = future.result()
            with results_lock:
                all_results.update(batch_results)

    return all_results
