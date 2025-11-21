# GitHub PR Review Analyzer

A Python script to analyze GitHub pull request review activity between you and other contributors.

## Features

- 📊 Track PRs you reviewed vs. PRs others reviewed for you
- 📈 Calculate lines of code reviewed in both directions
- ➕ Separate tracking of additions (+lines) and deletions (-lines)
- 🔢 Count review events (approvals, change requests)
- 💬 Track number of comments written
- 📝 List all reviewed PRs with clickable links
- ⚖️ Calculate review balance (offset) between users
- 🔀 Sortable review balance table by different columns
- 💾 Smart caching system to speed up subsequent runs
- 🔓 Includes open (unmerged) PRs in analysis

## Prerequisites

- Python 3.7+
- `requests` library
- GitHub Personal Access Token (recommended for higher rate limits)

## Installation

1. Install required dependencies:
    ```bash
     pip install -r requirements-review-analyzer.txt
    ```
   
2. Create env file (optional but recommended)

    ```bash
    cp .env.example .env
    ```

3. Replace the placeholders in the `.env` file


### Continuous Integration

Tests are automatically run on every push to the `main` branch or any feature branch via GitHub Actions. The workflow tests against multiple Python versions (3.9, 3.10, 3.11, 3.12) to ensure compatibility.


## Usage

### Interactive Mode

Simply run the script and follow the prompts (or provide parameters via `.env` file):

```bash
python3 github-review-analyzer.py
```

You'll be asked to provide:
- Your GitHub username
- GitHub token (optional, can press Enter to skip)
- List of repositories to analyze (format: `owner/repo`)
- Time range in months (default: 3)
- Users to exclude (optional, comma-separated)

### Example Session

```
GitHub PR Review Analyzer
================================================================================

Enter your GitHub username: florian-glombik

Enter GitHub token (or press Enter to skip):

Enter repositories (format: owner/repo, one per line)
Press Enter on an empty line when done
Example: ls1intum/Artemis
Repository: ls1intum/Artemis
Repository:

Analyze last N months [default: 3]: 3

Analyzing repository: ls1intum/Artemis
  Fetching pull requests...
  Found 150 PRs in the last 3 months
  Processing PR 10/150...
  ...
```

## Caching

The script automatically caches API responses to `.github_review_cache.json` in the current directory. This significantly speeds up subsequent runs by avoiding redundant API calls.

### Cache Features

- **Automatic**: Caching is enabled by default
- **Smart PR-state aware**: Only caches data for closed PRs (open PRs always fetch fresh data)
- **Permanent**: Cache entries never expire (closed PRs don't change)
- **Selective**: Only fetches new data when not in cache
- **Persistent**: Cache is saved to disk and reused across runs indefinitely

### Cache Control

To disable caching, set the `USE_CACHE` environment variable:

```bash
# Disable caching for a single run
USE_CACHE=false python3 github-review-analyzer.py

# Or in your .env file
USE_CACHE=false
```

To clear the cache, simply delete the cache file:

```bash
rm .github_review_cache.json
```

## Configuration Options

### Environment Variables

You can configure the script using environment variables in your `.env` file:

- `GITHUB_USERNAME`: Your GitHub username
- `GITHUB_TOKEN`: Your GitHub personal access token
- `GITHUB_REPOS`: Comma-separated list of repositories (e.g., `owner/repo1,owner/repo2`)
- `ANALYSIS_MONTHS`: Number of months to analyze (default: 3)
- `EXCLUDED_USERS`: Comma-separated list of users to exclude from analysis
- `USE_CACHE`: Enable/disable caching (default: true)
- `SORT_BY`: Column to sort the review balance table by (default: total_prs)

### Table Sorting

The review balance table can be sorted by different columns using the `SORT_BY` environment variable. Available options:

- `total_prs` (default): Total number of PRs reviewed between you and each user
- `balance`: Review balance (positive = you reviewed more of their code, negative = they reviewed more of yours)
- `user`: Username (alphabetically)
- `they_reviewed`: Total lines they reviewed of your code
- `i_reviewed`: Total lines you reviewed of their code
- `their_prs`: Number of their PRs you reviewed
- `my_prs`: Number of your PRs they reviewed

Example usage:

```bash
# Sort by review balance to see who you owe reviews to
SORT_BY=balance python3 github-review-analyzer.py

# Sort alphabetically by username
SORT_BY=user python3 github-review-analyzer.py

# Or in your .env file
SORT_BY=balance
```

Example `.env` file:
```bash
GITHUB_USERNAME=your-username
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPOS=ls1intum/Artemis
ANALYSIS_MONTHS=6
EXCLUDED_USERS=coderabbitai[bot],dependabot,bot-user
USE_CACHE=true
SORT_BY=balance
```

## Output

The script generates a detailed report showing:

### Per-User Statistics
For each user you've interacted with:
- Number of PRs reviewed (both directions)
- Lines of code reviewed (both directions)
- Number of review events (approvals, change requests)
- Number of comments written
- Line review offset (balance between you and them)
- Complete list of PRs with titles and direct links

### Overall Statistics
- Total PRs you reviewed
- Total PRs others reviewed for you
- Total lines reviewed (both directions)
- Number of collaborators

## Example Output

```
================================================================================
REVIEW SUMMARY FOR florian-glombik
================================================================================

────────────────────────────────────────────────────────────────────────────────
👤 user1
────────────────────────────────────────────────────────────────────────────────

Metric                         I reviewed           They reviewed
──────────────────────────────────────────────────────────────────────────────
PRs reviewed                   15                   10
Lines reviewed (total)         5,420                3,200
  +lines (additions)           4,200                2,500
  -lines (deletions)           1,220                  700
Review events                  18                   12
Comments written               45                   28

📊 Line Review Offset:
   Total: +2,220 lines (positive = you reviewed more of their code)
   +lines: +1,700
   -lines: +520

📝 PRs I reviewed (15):
   • #1234: Add new feature for exercise management
     https://github.com/ls1intum/Artemis/pull/1234 (+380 / -70 lines)
   ...

📝 PRs they reviewed (10):
   • #1235: Fix bug in quiz assessment
     https://github.com/ls1intum/Artemis/pull/1235 (+250 / -70 lines)
   ...

================================================================================
OVERALL STATISTICS
================================================================================

Total PRs I reviewed: 45
Total PRs others reviewed of mine: 38

Total lines I reviewed: 15,840
  +lines: 12,300
  -lines: 3,540

Total lines others reviewed: 12,450
  +lines: 9,800
  -lines: 2,650

Number of collaborators: 12
```

## Rate Limits

- **Without token**: 60 requests/hour
- **With token**: 5,000 requests/hour

Using a token is highly recommended for analyzing repositories with many PRs.

## Notes

- The script tracks additions (+lines) and deletions (-lines) separately and also shows the total
- Fetches full PR details to ensure accurate line counts
- Both open and closed PRs are included in the analysis
- Only closed PRs are cached; open PRs always fetch fresh data to reflect ongoing changes
- Cached data never expires since closed PR data is immutable
- You can exclude specific users (e.g., bots like dependabot) from the analysis
- Review events include approvals, change requests, and dismissals
- Comments include both review comments and general PR comments
- PRs are filtered by creation date within the specified time range
- The script handles pagination automatically for repositories with many PRs

## Troubleshooting

### Rate Limit Exceeded
```
Error: Rate limit exceeded
```
**Solution**: Use a GitHub Personal Access Token

### Missing Reviews
If you notice missing review data, ensure:
- The time range is appropriate
- You have access to the repository
- The PRs were created within the specified time range

## Testing
### Running Tests

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Run all tests:
   ```bash
   pytest test_github_review_analyzer.py -v
   ```

3. Run tests with coverage report:
   ```bash
   pytest test_github_review_analyzer.py --cov=github_review_analyzer --cov-report=term-missing
   ```
