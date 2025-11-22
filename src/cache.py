"""Caching functionality for GitHub API responses."""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional


class CacheManager:
    """Manages caching of API responses to reduce API calls."""

    def __init__(self, cache_file: str = '.github_review_cache.json', use_cache: bool = True):
        """Initialize the cache manager.

        Args:
            cache_file: Path to the cache file
            use_cache: Whether caching is enabled
        """
        self.cache_file = cache_file
        self.use_cache = use_cache
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if not self.use_cache or not os.path.exists(self.cache_file):
            return {}

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
                logging.info(f"Loaded cache from {self.cache_file} with {len(cache)} entries")
                return cache
        except Exception as e:
            logging.warning(f"Failed to load cache: {e}")
            return {}

    def save_cache(self):
        """Save cache to file."""
        if not self.use_cache:
            return

        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
                logging.info(f"Saved cache to {self.cache_file} with {len(self.cache)} entries")
        except Exception as e:
            logging.warning(f"Failed to save cache: {e}")

    def get_cache_key(self, repo: str, endpoint: str, params: Dict = None) -> str:
        """Generate a cache key for an API call.

        Args:
            repo: Repository name
            endpoint: API endpoint
            params: Query parameters

        Returns:
            MD5 hash of the cache key
        """
        key_data = f"{repo}:{endpoint}:{json.dumps(params, sort_keys=True) if params else ''}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, cache_key: str) -> Optional[List[Dict]]:
        """Get data from cache if it exists.

        Args:
            cache_key: The cache key to lookup

        Returns:
            Cached data if available, None otherwise
        """
        if not self.use_cache or cache_key not in self.cache:
            return None

        cached_entry = self.cache[cache_key]
        cached_time = datetime.fromisoformat(cached_entry['timestamp'])
        age_hours = (datetime.now() - cached_time).total_seconds() / 3600

        logging.debug(f"Using cached data (age: {age_hours:.1f} hours)")
        return cached_entry['data']

    def put(self, cache_key: str, data: List[Dict]):
        """Store data in cache.

        Args:
            cache_key: The cache key
            data: The data to cache
        """
        if not self.use_cache:
            return

        self.cache[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: The cache key to check

        Returns:
            True if the key exists in cache, False otherwise
        """
        return key in self.cache