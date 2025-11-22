# Testing Guide

## Running Tests

### Run all tests
```bash
pytest tests/ -v
```

### Run tests with coverage
```bash
pytest tests/ --cov=src --cov-report=term-missing
```

### Run tests with XML coverage report (for CI)
```bash
pytest tests/ --cov=src --cov-report=xml
```

### Run specific test file
```bash
pytest tests/test_models.py -v
pytest tests/test_cache.py -v
pytest tests/test_github_review_analyzer.py -v
pytest tests/test_api_client.py -v
```

### Run specific test class
```bash
pytest tests/test_models.py::TestReviewStats -v
```

### Run specific test method
```bash
pytest tests/test_models.py::TestReviewStats::test_review_stats_initialization -v
```

## Test Coverage

To view detailed coverage report:
```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html  # macOS
```

```bash
xdg-open htmlcov/index.html  # Linux
```