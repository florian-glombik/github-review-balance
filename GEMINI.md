# GEMINI.md

This file provides guidance for using the Gemini CLI with the **GitHub PR Review Analyzer** repository.

## Project Overview

This project is a Python script that analyzes GitHub pull request review activity. It generates a console summary and a detailed, interactive HTML report.

## Key Files

-   **Main Script:** `github-review-analyzer.py`
-   **Main Source:** `src/github_review_analyzer.py`
-   **Core Logic:** Files in `src/`
-   **Dependencies:** `requirements-review-analyzer.txt`
-   **Dev Dependencies:** `requirements-dev.txt`
-   **Tests:** Files in `tests/`

## How to Run the Application

The main script is `github-review-analyzer.py`.

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements-review-analyzer.txt
    ```

2.  **Set up Environment:**
    -   Copy the example `.env` file:
        ```bash
        cp .env.example .env
        ```
    -   Edit the `.env` file to add your `GITHUB_USERNAME`, `GITHUB_TOKEN`, and other settings.

3.  **Execute the Script:**
    ```bash
    python3 github-review-analyzer.py
    ```
    The script will generate an HTML report in the `reports/` directory.

## How to Run Tests

This project uses `pytest` for testing.

1.  **Install Development Dependencies:**
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run the Test Suite:**
    ```bash
    pytest tests/ -v
    ```

## Gemini's Role

As the Gemini assistant, your goal is to help maintain and extend this application. When making changes:

1.  **Adhere to Conventions:** Match the existing coding style and project structure.
2.  **Verify Changes:** Always run the test suite after making modifications to ensure you haven't introduced any regressions.
3.  **Update Tests:** If you add new features, add corresponding tests.
