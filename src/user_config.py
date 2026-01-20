"""
User configuration management for GitHub Review Analyzer.

Handles loading, updating, and saving user-specific settings like
nicknames and language preferences.
"""

import json
import logging
import os
from typing import Dict, Optional, Set

# Default config file path (relative to project root)
DEFAULT_CONFIG_FILE = "user_config.json"


class UserConfig:
    """Manages user configuration including nicknames and language preferences."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_FILE):
        """
        Initialize the UserConfig manager.

        Args:
            config_path: Path to the user configuration JSON file
        """
        self.config_path = config_path
        self.users: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        """Load existing configuration from file if it exists."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    logging.info(f"Loaded user config with {len(self.users)} user(s)")
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"Could not load user config from {self.config_path}: {e}")
                self.users = {}
        else:
            logging.info(f"No existing user config found at {self.config_path}")
            self.users = {}

    def save(self) -> None:
        """Save the current configuration to file."""
        try:
            data = {'users': self.users}
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logging.info(f"Saved user config with {len(self.users)} user(s)")
        except IOError as e:
            logging.error(f"Could not save user config to {self.config_path}: {e}")

    def update_users(self, github_usernames: Set[str]) -> int:
        """
        Add new users to the configuration without overwriting existing ones.

        Args:
            github_usernames: Set of GitHub usernames discovered during analysis

        Returns:
            Number of new users added
        """
        new_users_count = 0
        for username in sorted(github_usernames):
            if username not in self.users:
                self.users[username] = {
                    'nickname': '',  # Empty string means use GitHub username
                    'language': 'english'  # Default to English
                }
                new_users_count += 1
                logging.debug(f"Added new user to config: {username}")

        if new_users_count > 0:
            logging.info(f"Added {new_users_count} new user(s) to config")
            self.save()

        return new_users_count

    def get_nickname(self, github_username: str) -> str:
        """
        Get the display name for a user (nickname if set, otherwise GitHub username).

        Args:
            github_username: The GitHub username

        Returns:
            The nickname if set and non-empty, otherwise the GitHub username
        """
        if github_username in self.users:
            nickname = self.users[github_username].get('nickname', '')
            if nickname:  # Return nickname only if it's non-empty
                return nickname
        return github_username

    def get_language(self, github_username: str) -> str:
        """
        Get the language preference for a user.

        Args:
            github_username: The GitHub username

        Returns:
            The language preference ('english' or 'german'), defaults to 'english'
        """
        if github_username in self.users:
            return self.users[github_username].get('language', 'german')
        return 'german'

    def set_nickname(self, github_username: str, nickname: str) -> None:
        """
        Set the nickname for a user.

        Args:
            github_username: The GitHub username
            nickname: The nickname to use (empty string to use GitHub username)
        """
        if github_username not in self.users:
            self.users[github_username] = {'nickname': '', 'language': 'english'}
        self.users[github_username]['nickname'] = nickname
        self.save()

    def set_language(self, github_username: str, language: str) -> None:
        """
        Set the language preference for a user.

        Args:
            github_username: The GitHub username
            language: The language preference ('english' or 'german')
        """
        if language not in ('english', 'german'):
            logging.warning(f"Invalid language '{language}', using 'english'")
            language = 'english'

        if github_username not in self.users:
            self.users[github_username] = {'nickname': '', 'language': 'english'}
        self.users[github_username]['language'] = language
        self.save()

    def get_all_users(self) -> Dict[str, Dict[str, str]]:
        """
        Get all user configurations.

        Returns:
            Dictionary mapping GitHub usernames to their configurations
        """
        return self.users.copy()
