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

## Output

The script generates a comprehensive report with **color-coded sections** for easy readability.

### Report Structure

The output consists of three main sections:

1. **Review Balance & Next Actions** - Overview table showing:
    - Your review balance with each collaborator (positive = you owe reviews, negative = they owe you)
    - Total PRs reviewed in both directions
    - Action indicators: `→` (you should review their PRs) or `←` (they should review yours)
    - Sortable by various metrics (balance, total PRs, user, etc.)

2. **Open PRs That Need Your Review** - Actionable list showing:
    - Currently open PRs waiting for your review
    - Automatically prioritized by who you owe the most reviews to
    - Direct GitHub links and line counts for each PR

3. **Detailed Review History** - Deep dive per collaborator:
    - Complete metrics: PRs reviewed, lines reviewed, review events, comments
    - Full list of PRs you reviewed with titles and links
    - Full list of PRs they reviewed with titles and links

## Example Output

Below is a sample output (with anonymized usernames):

```
GitHub PR Review Analyzer
================================================================================
11/22/2025 08:54:33 PM INFO: Starting analysis for user: john-doe
11/22/2025 08:54:33 PM INFO: Using repositories from environment: acme-corp/awesome-app
11/22/2025 08:54:33 PM INFO: Using time range from environment: 6 months
11/22/2025 08:54:33 PM INFO: Sorting review balance table by: balance
11/22/2025 08:54:33 PM INFO: Excluding generated files from line count calculations

Fetching pull requests from acme-corp/awesome-app...
  Fetching open PRs... fetched 45 PRs
  Fetching closed PRs... fetched 198 PRs
Found 198 PRs in the last 6 months
Analyzing 198 PRs...
  Progress: 50/198 PRs analyzed
  Progress: 150/198 PRs analyzed
  Progress: 198/198 PRs analyzed
Completed analysis of acme-corp/awesome-app

================================================================================
REVIEW SUMMARY FOR john-doe
================================================================================

================================================================================
REVIEW BALANCE & NEXT ACTIONS
================================================================================

Review Balance (lines reviewed):
User              Total PRs  Their PRs    My PRs    They reviewed      I reviewed         Balance    Action
--------------------------------------------------------------------------------------------------------------
alice-smith       45         5            40        +9,172/-3,347      +2,752/-2,305      +7,462     → I should review their PRs
bob-jones         20         7            13        +6,582/-1,420      +1,601/-546        +5,855     → I should review their PRs
charlie-brown     15         2            13        +3,749/-433        +421/-89           +3,750     → I should review their PRs
diana-prince      12         0            12        +2,728/-916        +0/-0              +3,644     → I should review their PRs
eve-wilson        8          3            5         +2,320/-84         +863/-571          +970       → I should review their PRs
frank-castle      5          0            5         +549/-251          +0/-0              +800       → I should review their PRs
grace-hopper      2          1            1         +78/-63            +146/-7            -12        ← They should review my PRs
henry-ford        5          2            3         +399/-347          +838/-308          -400       ← They should review my PRs
iris-west         5          2            3         +104/-202          +1,794/-491        -1,979     ← They should review my PRs
jack-ryan         3          2            1         +327/-204          +1,920/-2,568      -3,957     ← They should review my PRs
kate-bishop       5          3            2         +656/-508          +5,458/-1,006      -5,300     ← They should review my PRs

================================================================================
OPEN PRs THAT NEED YOUR REVIEW
================================================================================

You have 12 open PR(s) to review:

From diana-prince (Priority: You owe them 3,644 lines):
  • [awesome-app] #1234: Feature: Add user authentication system
    https://github.com/acme-corp/awesome-app/pull/1234 (+346 / -245 lines)
  • [awesome-app] #1256: Fix: Resolve memory leak in data processor
    https://github.com/acme-corp/awesome-app/pull/1256 (+189 / -52 lines)

From bob-jones (Priority: You owe them 5,855 lines):
  • [awesome-app] #1289: Refactor: Modernize API endpoints
    https://github.com/acme-corp/awesome-app/pull/1289 (+951 / -412 lines)
  • [awesome-app] #1301: Docs: Update deployment guide
    https://github.com/acme-corp/awesome-app/pull/1301 (+112 / -8 lines)

From eve-wilson (Priority: You owe them 970 lines):
  • [awesome-app] #1198: Feature: Add dark mode support
    https://github.com/acme-corp/awesome-app/pull/1198 (+652 / -221 lines)

From iris-west (Priority: They owe you 1,979 lines):
  • [awesome-app] #1145: Test: Improve integration test coverage
    https://github.com/acme-corp/awesome-app/pull/1145 (+487 / -156 lines)
```

### Understanding the Output

**Review Balance Table:**
- **Positive Balance** (→): You owe them reviews - prioritize reviewing their PRs
- **Negative Balance** (←): They owe you reviews - they should review your PRs
- **Balance calculation**: (lines they reviewed of yours) - (lines you reviewed of theirs)

**Open PRs Section:**
- Automatically prioritized by review balance
- Shows PRs from people you owe the most reviews to first
- Includes clickable GitHub links and line counts

**Detailed History:**
- Complete breakdown per collaborator
- All PRs listed with titles and links
- Full metrics including comments and review events

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
- `SHOW_EXTENDED_REPORT`: Show detailed review history per user (default: false)

### Extended Report

By default, the script outputs a concise report showing only the review balance table, open PRs, and overall statistics. To see the detailed review history section with per-user breakdowns of all reviewed PRs, you can enable the extended report:

```bash
# Enable extended report for a single run
SHOW_EXTENDED_REPORT=true python3 github-review-analyzer.py

# Or in your .env file
SHOW_EXTENDED_REPORT=true
```

The extended report includes:
- Detailed metrics table for each collaborator
- Complete list of PRs you reviewed for them with links
- Complete list of PRs they reviewed for you with links
- Line review offset calculations per user

This is useful for in-depth analysis but can make the output quite long if you have many collaborators.

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
SHOW_EXTENDED_REPORT=false
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

For comprehensive testing instructions, see the [Testing Guide](TESTING.md).

### Quick Start

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Run all tests:
   ```bash
   pytest tests/ -v
   ```

3. Run tests with coverage report:
   ```bash
   pytest tests/ --cov=src --cov-report=term-missing
   ```
