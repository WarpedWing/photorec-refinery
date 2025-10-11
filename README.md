# PhotoRec Refinery

A command-line utility to intelligently organize files recovered by [PhotoRec](https://www.cgsecurity.org/wiki/PhotoRec). It actively monitors the PhotoRec output directory, deletes unwanted file types from completed `recup_dir.X` folders in real-time.

![While running](https://i.imgur.com/NaiEfDp.png)
![After running](https://i.imgur.com/4c2jbBD.png)

## Why Does This Exist?

Sometimes you only need to recover a handful of file types, but your drive can quickly get filled by thousands of unwanted image and text files. The catch is that the more file types PhotoRec parses, the better the output. Only searching for one or two types can result in erroneously huge files.

PhotoRec Refinery allows PhotoRec to parse all file types, but actively deletes unwanted types as they are created to keep the output tidy. It also can reorganize the kept files into a type-based folder structure, as well as create a log of all deleted and kept files.

> [!NOTE]
> This early version of the script shouldn't be used for critical forensic applications. Use at your own risk.

Please [email me](mailto:noel.benford@gmail.com) with any issues, questions, comments, or suggestions. Thanks!

## Requirements

- Python 3.8+
- [UV](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

### Using UV (Recommended)

UV is a fast Python package installer and resolver. If you don't have it installed:

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install PhotoRec Refinery:

```bash
# Clone or download this repository
cd photorec-refinery

# Install the package
uv pip install .
```

### Using pip

```bash
# Clone or download this repository
cd photorec-refinery

# Install the package
pip install .
```

### Running Without Installation

You can also run the script directly without installing:

```bash
uv run src/photorec_refinery/photorec_refinery.py [OPTIONS]
```

## Command-Line Arguments

> [!IMPORTANT]
> **You must provide an input directory (`-i`) and at least one filtering rule (`-k` or `-x`).**

| Argument              | Short | Description                                                                                                          |
| --------------------- | ----- | -------------------------------------------------------------------------------------------------------------------- |
| `--input <path>`      | `-i`  | **(Required)** Path to the PhotoRec output directory.                                                                |
| `--keep <ext ...>`    | `-k`  | Defines an **allow list**. Only files with these extensions will be kept; all others are deleted.                    |
| `--exclude <ext ...>` | `-x`  | Defines a **deny list**. Files with these extensions will be deleted. This rule overrides `--keep` if both are used. |
| `--reorganize`        | `-r`  | After cleaning, move kept files into folders named by file type and remove the old `recup_dir.X` folders.            |
| `--log`               | `-l`  | Log all file actions (kept/deleted) to a timestamped CSV file in the output directory.                               |
| `--interval <sec>`    | `-t`  | Seconds between scanning for new folders. Defaults to `5`.                                                           |
| `--batch-size <num>`  | `-b`  | Max number of files per subfolder when reorganizing. Defaults to `500`.                                              |

## Usage

```bash
photorec-refinery -i /path/to/photorec_output [OPTIONS]
```

### Examples

**Example 1: Keep only common image and document files.**

```bash
photorec-refinery -i /path/to/output -k jpg jpeg png gif pdf doc docx
```

**Example 2: Keep everything _except_ temporary and system files, and reorganize the results.**

```bash
photorec-refinery -i /path/to/output -x tmp chk dat -r
```

**Example 3: Keep gz files except xml.gz and html.gz, polls every 1 second, logs actions, and uses 1000 files per subfolder in the reorg.**

```bash
photorec-refinery -i /path/to/output -k gz -x xml.gz html.gz -t 1 -l -r -b 1000
```

## How It Works

1. Start PhotoRec Refinery before starting recovery with PhotoRec. The status spinner will be **gray** until PhotoRec creates the first `recup_dir.1` folder.
1. Once PhotoRec Refinery detects folders, the spinner turns **blue**.
1. As soon as PhotoRec creates a second folder (e.g., `recup_dir.2`), the script assumes the first one is complete. It begins cleaning `recup_dir.1` based on your rules. The spinner turns **green**.
1. This process continues, with the script always cleaning all but the highest-numbered `recup_dir.X` folder.
1. When PhotoRec finishes, press `y` and then `Enter`. The script will perform a final pass to clean all remaining folders.
1. If `-r` (`--reorganize`) is used, it will then move all kept files into their new folders/subfolders, and the `recup_dir.X` folders will be removed.

## Running Tests

Unit tests are located in the `tests/` directory. You can run them from the project's root directory using Python's built-in test discovery:

```bash
python -m unittest discover
```

Or with UV:

```bash
uv run python -m unittest discover
```
