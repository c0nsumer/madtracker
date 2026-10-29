# Backups

A backup is a complete copy of the data file, with everything in it: riders, events, races, every entry, rulesets, and settings. Each backup opens on its own.

## When and where

The program backs up the data file on its own: each time a race's result is complete, each time a race is marked final, and when you quit or open another data file. **File** → **Backup Now...** writes one more copy where you choose, eg: on a USB stick to take home, and the usual automatic backup with it.

Backups go to the `backups` folder beside the data file. The newest 20 are kept, plus the last backup of each of the last 10 dates, so last week's file is still there after a long night. The default data file and its `backups` folder are here:

- Windows: `%LOCALAPPDATA%\MadTracker`. To open it, press Win+R, type `%LOCALAPPDATA%\MadTracker`, and press Enter.
- macOS: `~/Library/Application Support/MadTracker`. In Finder, choose **Go** → **Go to Folder...** and paste that path.
- Linux: `~/.local/share/madtracker`.

The same folder holds `madtracker.log`, the program's log. If something goes wrong, send it with your report. **Help** → **Open Data Folder** opens the folder of the open data file, with its log and its `backups` folder.

If a **Backup folder** is set in [Settings](getting-started.md#settings), a copy also goes there when you quit, and **Backup Now...** starts its save box there. Nothing in that folder is ever deleted. If the folder is gone, eg: the USB stick was pulled, the program says so, and the automatic backup is still written.

A backup that succeeds shows nothing. A backup that fails shows a message box with the reason, and scoring continues.

## Restoring

Choose **File** → **Open Data File...** (see [The data file](getting-started.md#the-data-file)) and pick the backup, wherever it is and whatever it's called. The program recognizes it and asks, eg: "This is a backup of Race Night 12, taken 2026-Oct-10 9:45 PM. Restore it as a new data file?" Click **Restore**, choose a name, and the copy opens in place of the current file. The backup itself is never changed.

If the name chosen is a data file that already exists, such as `madtracker.sqlite`, the program asks before replacing it. What that file held is backed up into its own `backups` folder first, so a wrong pick can be undone the same way. That copy is named `madtracker-before-restore-` and the time, and it's never deleted by the program.

This is also how to move a data file to another laptop or share a copy: make a backup, copy it, and open it.

**Caution**: Copy a backup, not the data file itself. While the program is running, data is spread across the data file and the other files in its folder. Attempting to copy them directly will have unreliable results. The backup function makes a clean copy, ready to restore elsewhere or later.
