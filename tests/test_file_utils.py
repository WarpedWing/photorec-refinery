"""
Tests app against auto-created imaginary files.
"""

import csv
import shutil
import unittest
from io import StringIO
from pathlib import Path

from src.photorec_refinery import file_utils as fu
from src.photorec_refinery.app_state import AppState


class TestFileUtils(unittest.TestCase):
    """Test suite for the file utility functions."""

    def setUp(self):
        """Set up a temporary directory with dummy files for each test."""
        self.test_dir = Path("temp_test_dir")
        self.recup_dir = self.test_dir / "recup_dir.1"
        self.recup_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy files with specific sizes
        self.files_to_create = {
            "photo.jpg": 100,
            "image.jpeg": 150,
            "document.pdf": 200,
            "archive.zip": 300,
            "movie.mov": 1000,
            "temp.tmp": 50,
        }

        for filename, size in self.files_to_create.items():
            path = self.recup_dir / filename
            path.write_bytes(b"a" * size)  # Write content to match the size

    def tearDown(self):
        """Remove the temporary directory after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_clean_folder_with_keep_rules_and_logging(self):
        """Verify that only specified files are kept and logging works."""
        state = AppState()
        keep_extensions = {"jpg", "jpeg", "pdf"}

        # --- Setup logging ---
        log_stream = StringIO()
        state.log_writer = csv.writer(log_stream)

        # --- Act ---
        fu.clean_folder(str(self.recup_dir), state, keep_ext=keep_extensions)

        # --- Assert ---
        # --- Assert File System State ---
        # Check file system state
        remaining_files = [f.name for f in self.recup_dir.iterdir()]
        self.assertIn("photo.jpg", remaining_files)
        self.assertIn("image.jpeg", remaining_files)
        self.assertIn("document.pdf", remaining_files)
        self.assertNotIn("archive.zip", remaining_files)
        self.assertNotIn("movie.mov", remaining_files)
        self.assertNotIn("temp.tmp", remaining_files)

        # --- Assert AppState Correctness ---
        self.assertEqual(state.total_kept_count, 3)
        self.assertEqual(state.total_deleted_count, 3)
        expected_deleted_size = (
            self.files_to_create["archive.zip"] + self.files_to_create["movie.mov"] + self.files_to_create["temp.tmp"]
        )  # 300 + 1000 + 50 = 1350
        self.assertEqual(state.total_deleted_size, expected_deleted_size)

        # --- Assert Logging Correctness ---
        log_stream.seek(0)
        log_content = list(csv.reader(log_stream))
        self.assertEqual(len(log_content), 6)

        # Create a set of tuples from the log for easy checking
        log_set = {(row[1], row[3]) for row in log_content}  # (filename, status)
        expected_log_set = {
            ("photo.jpg", "kept"),
            ("image.jpeg", "kept"),
            ("document.pdf", "kept"),
            ("archive.zip", "deleted"),
            ("movie.mov", "deleted"),
            ("temp.tmp", "deleted"),
        }
        self.assertEqual(log_set, expected_log_set)

    def test_clean_folder_with_exclude_rules(self):
        """Verify that excluded files are deleted, overriding any keep rules."""
        state = AppState()
        keep_extensions = {"jpg", "jpeg"}
        exclude_extensions = {"jpeg"}

        # --- Act ---
        fu.clean_folder(
            str(self.recup_dir),
            state,
            keep_ext=keep_extensions,
            exclude_ext=exclude_extensions,
        )

        # --- Assert ---
        remaining_files = [f.name for f in self.recup_dir.iterdir()]
        self.assertIn("photo.jpg", remaining_files)
        self.assertNotIn("image.jpeg", remaining_files)

        # Check AppState correctness
        self.assertEqual(state.total_kept_count, 1)
        self.assertEqual(state.total_deleted_count, 5)

    def test_clean_folder_with_exclude_rules_and_logging(self):
        """Verify that excluded files are deleted and logging works."""
        state = AppState()
        keep_extensions = {"jpg", "jpeg"}
        exclude_extensions = {"jpeg"}

        # --- Setup logging ---
        log_stream = StringIO()
        state.log_writer = csv.writer(log_stream)

        # --- Act ---
        fu.clean_folder(
            str(self.recup_dir),
            state,
            keep_ext=keep_extensions,
            exclude_ext=exclude_extensions,
        )

        # --- Assert Logging ---
        log_stream.seek(0)
        self.assertEqual(len(list(csv.reader(log_stream))), 6)  # 1 kept, 5 deleted

    def test_clean_folder_with_deletion_disabled(self):
        """Verify that no files are deleted when keep_ext is an empty set."""
        state = AppState()
        keep_extensions = set()  # Empty set simulates deletion being disabled

        # --- Act ---
        fu.clean_folder(str(self.recup_dir), state, keep_ext=keep_extensions)

        # --- Assert ---
        # Verify that no files were deleted
        remaining_files = [f.name for f in self.recup_dir.iterdir()]
        self.assertEqual(len(remaining_files), len(self.files_to_create))

        # Verify the application state
        self.assertEqual(state.total_kept_count, len(self.files_to_create))
        self.assertEqual(state.total_deleted_count, 0)
        self.assertEqual(state.total_deleted_size, 0)
