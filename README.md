# PhotoRec Refinery

![PhotoRec Refinery - Main](https://github.com/WarpedWing/WarpedWing/blob/main/refinery-mainwindow.png)

A desktop companion for [PhotoRec](https://www.cgsecurity.org/wiki/PhotoRec) that helps you auto-remove filetypes you don't want — and keep the carved files organized.

- Live‑monitors PhotoRec’s output and automatically deletes unwanted types in completed `recup_dir.X` folders
- One‑click “Process” for existing PhotoRec output that’s already finished
- Optional reorganization into type‑based folders with configurable subfolder batch sizes

| From This    | To This |
| -------- | ------- |
| ![PhotRec Refinery - Ugly Folders](https://github.com/WarpedWing/WarpedWing/blob/main/refinery-uglyfolders.png)  | ![PhotRec Refinery - Reorganized Folders](https://github.com/WarpedWing/WarpedWing/blob/main/refinery-cleanfolders.png)    |

## Why This Helps

PhotoRec works best when it recovers everything it can. (Carving just a few filetypes results in corrupt or huge files.) But recovering all types can quickly fill your drive.

For example, you might only want `.jpg,.png,.pdf`, but end up with gigabytes of `html.gz`, `xml.gz`, and tiny temp files. Or, you might only want system files, but end up with a drive's-worth of images.

![PhotoRec Refinery - Outcome](https://github.com/WarpedWing/WarpedWing/blob/main/refinery-outputprompt.png)

PhotoRec Refinery can get rid of the unwanted files as soon as they're written to disk, keeping total extraction size as small as possible for your specific needs.

## Features

- **Live monitor or one‑shot** – Monitor while PhotoRec runs, or process a finished output folder
- **Flexible filtering** – Comma‑separated Keep and Exclude lists (e.g., `jpg,png,pdf`)
- **Smart reorganization** – Move kept files into type‑named folders
- **Detailed logging** – Per‑file CSV log (kept/deleted) plus a final summary CSV (bytes and GB saved)

![PhotoRec Refinery - Log](https://github.com/WarpedWing/WarpedWing/blob/main/refinery-log.png)

## Installation

### Option 1: Download Pre-built App

Download the latest release for your platform from the [Releases](https://github.com/WarpedWing/photorec-refinery/releases) page:

- **macOS**: Download `PhotoRec-Refinery-X.X.X.dmg`
- **Windows**: Download `PhotoRec-Refinery-X.X.X.msi`
- **Linux**: Download `PhotoRec-Refinery-X.X.X.AppImage`

#### Running on macOS (Unsigned App)

Since the app is not signed with an Apple Developer certificate, macOS Gatekeeper will prevent it from opening. To run the app:

1. **Initial launch**: After downloading, right-click (or Control-click) on `PhotoRec Refinery.app` and select "Open"
2. Click "Open" in the security dialog that appears
3. Alternatively, you can run this command in Terminal:

   ```bash
   xattr -cr "/Applications/PhotoRec Refinery.app"
   ```

4. For subsequent launches, you can open the app normally

If you see "damaged app" warnings, run:

```bash
sudo xattr -rd com.apple.quarantine "/Applications/PhotoRec Refinery.app"
```

### Option 2: Run from Source

If you prefer to run the app from source:

#### Requirements

- Python 3.8+
- [UV](https://docs.astral.sh/uv/) (recommended) or pip

#### Installation with UV

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/WarpedWing/photorec-refinery.git
cd photorec-refinery

# Install the package
uv pip install -e .

# Run the GUI app
uv run photorec-refinery-gui
```

#### Installation with pip

```bash
# Clone the repository
git clone https://github.com/WarpedWing/photorec-refinery.git
cd photorec-refinery

# Install the package
pip install .

# Run the GUI app
photorec-refinery-gui
```

## Using the App

1. **Select the PhotoRec Output Directory** – The folder that contains `recup_dir.1`, `recup_dir.2`, ...
2. **Set Filtering Options**
   - Toggle **Enable File Deletion** to activate filtering
   - Enter comma‑separated extensions without dots: `jpg,png,pdf` (not `.jpg, .png`)
      - _Only **Keep** filled in_
         - Keep types will be saved, all other files will be deleted.
      - _Only **Exclude** filled in_
         - Exclude types will be deleted, all other files will be kept.
      - _Both **Keep and Exclude** field in_
         - Exclude overrides Keep, allowing for subtype filtering.
         - E.g., keep `gz` but exclude `xml.gz` and `html.gz`
3. **Set Reorganization Options**
   - **Enable Logging** – Writes a per‑file CSV of actions to your chosen log folder
      - Each file is tracked and marked **kept** or **deleted**
   - **Reorganize Files** – Moves kept files into folders named by type; set a **Batch Size** to limit files per subfolder
4. **Live Processing**
   - **Live Monitor** – Starts monitoring before or during PhotoRec's carving run
   - **Finalize** – When PhotoRec finishes, click **Finalize**
5. **Post Processing**
   - **Process** – Processes all existing `recup_dir.*` folders immediately

## Building from Source

To build the application yourself (requires Python 3.8+):

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and enter directory
git clone https://github.com/WarpedWing/photorec-refinery.git
cd photorec-refinery

# Build the app
uv run briefcase create
uv run briefcase build

# Create distributable package
uv run briefcase package
```

The packaged app will be in the `dist/` directory.

## Tips & Troubleshooting

### macOS: "App is damaged and can't be opened"

This happens due to Gatekeeper quarantine. Run:

```bash
sudo xattr -rd com.apple.quarantine "/Applications/PhotoRec Refinery.app"
```

### macOS: "App can't be opened because it is from an unidentified developer"

Right-click the app and select "Open", then click "Open" in the dialog.

### Windows: SmartScreen warning

Click "More info" then "Run anyway"

### Windows: "photorec-refinery-gui program not found" when using uv

On Windows, you need to explicitly install the package first before running the script:

```bash
# Install the package first
uv pip install -e .

# Then run the GUI
uv run photorec-refinery-gui
```

Alternatively, you can run it as a Python module:
```bash
uv run python -m photorec_refinery
```

### App doesn't detect PhotoRec folders

- Ensure you've selected the correct output directory (the one containing `recup_dir.1`, etc.)
- Check that you have read/write permissions for the directory

### Files aren't being filtered

- Verify "Clean Files" is enabled
- Check that you've entered at least one extension in either "Keep" or "Exclude"
- Extensions should be entered without dots: `jpg png` not `.jpg .png`

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contact

For issues, questions, or suggestions, please:

- Open an issue on [GitHub](https://github.com/WarpedWing/photorec-refinery/issues)
- Email: <noel@warpedwinglabs.com>
