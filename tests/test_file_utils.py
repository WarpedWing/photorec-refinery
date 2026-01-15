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

    def test_extensionless_files_go_to_unknown_folder(self):
        """Verify that files without extensions are categorized as 'unknown'."""
        state = AppState()

        # Create an extensionless file
        extensionless_file = self.recup_dir / "mystery_file"
        extensionless_file.write_bytes(b"mystery content")

        # --- Act ---
        fu.clean_folder(str(self.recup_dir), state)

        # --- Assert ---
        # The extensionless file should be in kept_files under "unknown"
        self.assertIn("unknown", state.kept_files)
        unknown_files = [Path(p).name for p in state.kept_files["unknown"]]
        self.assertIn("mystery_file", unknown_files)

    def test_sqlite_associated_files_grouped_with_sqlite(self):
        """Verify that .sqlite-shm, .sqlite-wal, .sqlite-journal files are grouped with sqlite."""
        state = AppState()

        # Create SQLite file and its associated files
        (self.recup_dir / "database.sqlite").write_bytes(b"sqlite data")
        (self.recup_dir / "database.sqlite-shm").write_bytes(b"shm data")
        (self.recup_dir / "database.sqlite-wal").write_bytes(b"wal data")
        (self.recup_dir / "database.sqlite-journal").write_bytes(b"journal data")

        # --- Act ---
        fu.clean_folder(str(self.recup_dir), state)

        # --- Assert ---
        # All SQLite-related files should be under "sqlite" extension
        self.assertIn("sqlite", state.kept_files)
        sqlite_files = [Path(p).name for p in state.kept_files["sqlite"]]
        self.assertIn("database.sqlite", sqlite_files)
        self.assertIn("database.sqlite-shm", sqlite_files)
        self.assertIn("database.sqlite-wal", sqlite_files)
        self.assertIn("database.sqlite-journal", sqlite_files)

        # These extensions should NOT have their own folders
        self.assertNotIn("shm", state.kept_files)
        self.assertNotIn("wal", state.kept_files)
        self.assertNotIn("journal", state.kept_files)

    def test_non_sqlite_shm_wal_files_keep_own_extension(self):
        """Verify that .shm/.wal/.journal files NOT following SQLite naming keep their extension."""
        state = AppState()

        # Create files that end in .shm but don't follow SQLite pattern
        (self.recup_dir / "random.shm").write_bytes(b"random shm")
        (self.recup_dir / "other.wal").write_bytes(b"other wal")

        # --- Act ---
        fu.clean_folder(str(self.recup_dir), state)

        # --- Assert ---
        # These should be under their own extension, not sqlite
        self.assertIn("shm", state.kept_files)
        self.assertIn("wal", state.kept_files)

        shm_files = [Path(p).name for p in state.kept_files["shm"]]
        wal_files = [Path(p).name for p in state.kept_files["wal"]]
        self.assertIn("random.shm", shm_files)
        self.assertIn("other.wal", wal_files)


class TestOrganizeByType(unittest.TestCase):
    """Test suite for the organize_by_type function."""

    def setUp(self):
        """Set up a temporary directory for each test."""
        self.test_dir = Path("temp_test_organize")
        self.recup_dir = self.test_dir / "recup_dir.1"
        self.recup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Remove the temporary directory after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_photorec_report_xml_moved_to_root(self):
        """Verify that PhotoRec's carve report.xml is moved to root directory."""
        state = AppState()

        # Create a PhotoRec-style report.xml
        report_content = """<?xml version='1.0' encoding='UTF-8'?>
<dfxml xmloutputversion='1.0'>
  <metadata
  xmlns='http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML'
  xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'
  xmlns:dc='http://purl.org/dc/elements/1.1/'>
    <dc:type>Carve Report</dc:type>
  </metadata>
  <creator>
    <package>PhotoRec</package>
  </creator>
</dfxml>"""
        report_file = self.recup_dir / "report.xml"
        report_file.write_text(report_content)

        # Also create a regular XML file to ensure it still goes to xml folder
        other_xml = self.recup_dir / "other.xml"
        other_xml.write_text("<data>test</data>")

        # Simulate what clean_folder would do
        state.kept_files["xml"] = [str(report_file), str(other_xml)]

        # --- Act ---
        fu.organize_by_type(str(self.test_dir), state)

        # --- Assert ---
        # report.xml should be in root directory
        self.assertTrue((self.test_dir / "report.xml").exists())

        # other.xml should be in xml folder
        self.assertTrue((self.test_dir / "xml" / "other.xml").exists())

        # report.xml should NOT be in xml folder
        self.assertFalse((self.test_dir / "xml" / "report.xml").exists())

    def test_regular_report_xml_goes_to_xml_folder(self):
        """Verify that non-PhotoRec report.xml files go to xml folder."""
        state = AppState()

        # Create a report.xml that is NOT a PhotoRec carve report
        report_file = self.recup_dir / "report.xml"
        report_file.write_text("<report><data>Some other report</data></report>")

        state.kept_files["xml"] = [str(report_file)]

        # --- Act ---
        fu.organize_by_type(str(self.test_dir), state)

        # --- Assert ---
        # This report.xml should be in xml folder since it's not a PhotoRec carve report
        self.assertTrue((self.test_dir / "xml" / "report.xml").exists())
        self.assertFalse((self.test_dir / "report.xml").exists())
