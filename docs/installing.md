# Installing

This page is for whoever sets up the scoring laptop. It covers installing on Windows, macOS, and Linux, where the data lives, and a few notes on the second monitor, backups, and the venue logo. If you want to build the program yourself, see [Building](building.md).

MadTracker needs no internet connection and no administrator rights. The data folder is never next to the program, so upgrading never touches it, and uninstalling removes it only if you say so.

## Download

Get the file for the laptop's system from the project's GitHub Releases page.

- Windows 10 or 11: `MadTracker-<version>-setup.exe` is the installer. Use it for the scoring laptop. `MadTracker-<version>-portable.zip` is the same program without an installer; unzip it to a folder on the laptop's own disk and run `MadTracker.exe`.
- macOS 12 or newer, on a Mac with Apple silicon (M1 or later): `MadTracker-<version>.dmg`. There is no build for Intel Macs. A `MadTracker-<version>-macos.zip` with the same app is also there.
- Linux, 64-bit Intel or AMD with a graphical desktop: `MadTracker-<version>-linux-x86_64.tar.gz`.

## Install on Windows

1. Double-click the setup file.
2. If Windows shows a blue "Windows protected your PC" box, see the next section.
3. Accept the license and click Next.
4. Choose whether to add a desktop shortcut.
5. Click Install, then Finish.

The installer puts the program in `%LOCALAPPDATA%\Programs\MadTracker`. It also adds a Start menu entry. If an older version is installed, the installer removes it first, then installs the new one in its place. Your data folder is not touched.

On a laptop with a 1366 by 768 screen, keep Windows' display scale at 100%, which is its default there (Settings -> System -> Display -> Scale). At 125% the screen is too short for the scoring window, and its bottom is cut off.

## SmartScreen warning on Windows

The builds are not code-signed yet. Windows SmartScreen therefore warns about the download.

1. Click "More info".
2. Click "Run anyway".

Do this once per downloaded file. The portable zip may also show the warning when you first run `MadTracker.exe`. Use the same two clicks.

## Install on a Mac

1. Double-click the dmg.
2. Drag MadTracker onto the Applications folder in the window.
3. Eject the disk image.

## Gatekeeper warning on a Mac

The builds are not signed or notarized yet. So the first time MadTracker is opened, macOS refuses with a message that Apple could not verify it.

1. Open MadTracker from the Applications folder, and close the message. Don't choose Move to Trash.
2. Open System Settings -> Privacy & Security.
3. Scroll to the Security section, find the message about MadTracker, and click "Open Anyway".
4. Enter your password, then click "Open Anyway" in the dialog that follows.

Do this once. After that, the app opens normally. If the "Open Anyway" button isn't there, open the app once more, then look again.

## Install on Linux

1. Unpack the tarball into a folder on the laptop's own disk, for example `tar -xzf MadTracker-<version>-linux-x86_64.tar.gz -C ~/apps`.
2. Run `~/apps/MadTracker/MadTracker`.

To add MadTracker to the application menu, run `~/apps/MadTracker/install-launcher.sh`. It writes `madtracker.desktop` for the current user and points it at the unpacked folder. Run it again if you move the folder.

## Where your data lives

All data is in one folder per user.

- Windows: `%LOCALAPPDATA%\MadTracker`. To open it, press Win+R, type `%LOCALAPPDATA%\MadTracker`, and press Enter.
- macOS: `~/Library/Application Support/MadTracker`. In Finder, choose Go -> Go to Folder... and paste that path.
- Linux: `~/.local/share/madtracker`. If the `XDG_DATA_HOME` variable is set, the data is in the `madtracker` folder inside it instead.

In the app, Help -> Open Data Folder opens the folder of the open data file in Explorer, Finder, or the file manager.

The folder holds the same files on every system:

- The default data file, `madtracker.sqlite`.
- The automatic backups, in the `backups` folder.
- The self-test's result, `self-test.log`.
- A `demo` folder, once Help -> Demo Data File... has been used. It holds `demo.sqlite`, the sample data file, with its own `backups` folder and log. The demo is open for the session only; the next start returns to your own data file.
- The program's log, `madtracker.log`. When a scorer reports a problem, ask for this file. It records the start of each session (the version, the system, the data file, and the displays), every message box and refused click, each backup written or failed, slow saves, recovery after an unclean close, and the details of any unexpected error. At about 1 MB it becomes `madtracker.log.1` and a new log starts, so at most two are kept.

You can keep other data files, for example a practice file. Choose File -> New Data File... to create one, or File -> Open Data File... to open one. If a new file copies no settings, Settings opens so you can name the venue. The app remembers the last data file it opened and opens it at the next start. If that file is missing, the app opens the default data file and a message box names the missing file. The `--data-dir` option opens the data file in another folder for one run, and the app does not remember it.

Each data file keeps its `backups` folder and its `madtracker.log` beside it. The app always writes its automatic backups there. If you choose a backup folder in File -> Settings..., the app also writes a copy there when you quit. If that folder is missing, for example because the USB stick was removed, the app warns you, and the automatic backup is still written.

Keep the data folder on the laptop's internal disk. Do not move it into OneDrive, iCloud Drive, Documents, or Desktop, and do not put it on a USB stick. The same applies to any data file you open.

The program never stores data next to its own files. On Windows, uninstalling asks whether to also delete the data folder, and the answer is No unless you choose Yes. Yes deletes the data folder above and the app's remembered settings; data files kept elsewhere and a backup folder chosen in Settings stay. Upgrading never asks and never deletes. On macOS and Linux, removing the app leaves the data folder; delete it by hand if you want it gone.

To move a venue's data to another laptop, use a backup; see [Backups](../madtracker/help/backups.md).

## Second monitor and backup notes

1. Connect the scoreboard TV and confirm the system shows two displays. MadTracker uses the second display for the scoreboard. The Scoreboard menu lists every display, with Automatic first and None for off, so another display can be picked on the night. With one display, or with the scoring window on the display chosen for the scoreboard, the scoreboard opens as an ordinary window. If the system mirrors the laptop screen to the TV instead of extending to it, it counts as one display, so set it to extend.
2. Keep the data folder on the laptop's internal disk, as described above.
3. If you want backups on an external disk (eg: USB flash drive), set that up as per [Backups](../madtracker/help/backups.md).
4. While MadTracker is running, it keeps the displays awake, so neither the laptop's screen nor the scoreboard TV goes to sleep. It may not stop a screen saver (on Windows it does not), so turn the screen saver off on the scoring laptop. On Linux it works on KDE, Xfce, and other desktops that support it; on GNOME, turn off screen blanking in the power settings.
5. Run one practice race in a practice data file and export a PDF. Check that the PDF opens.

## Second display on a Mac

MadTracker shows the scoreboard full screen on the display you choose. Connect the scoreboard TV before you start the app.

If the scoreboard does not fill the TV, or the scorer window moves when the scoreboard opens, check one setting. Open System Settings -> Desktop & Dock, scroll to Mission Control, and turn on "Displays have separate Spaces". Then log out and log in again.

If "Displays have separate Spaces" is turned off, a full-screen window on one display grays out the others, so keep it on (its default) while the scoreboard is full screen.

## The venue logo

The app ships with its own placeholder wordmark on the scoreboard. Set the venue's logo in File -> Settings... The image should be a PNG with a transparent background, white or light artwork, and a wide shape, about three times as wide as tall. For a 1080p TV make it at least 1400 pixels wide, and for a 4K TV 2880; a larger image is scaled down to fit 2880 by 1200 pixels when it is chosen. Keep it under 1 MB. SVG files are not supported.

A venue's wordmark is its trademark and is not part of the app. Keep a copy on the scoring laptop, for example in Documents, and choose it in Settings once. The setting is stored in the database, so it survives upgrades.
