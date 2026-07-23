# Install OpenConstructionERP

OpenConstructionERP by DataDrivenConstruction is an open-source platform for construction cost estimation, bills of quantities, and data validation, with CAD and BIM quantity takeoff and multi-currency support. The desktop app puts the whole thing on your computer. You download one installer and run it. There is no Python, no pip, no Docker, and no database to set up. Everything it needs is already inside.

This guide walks you through installing it and signing in for the first time.

## Where to download

The installers live on the project's GitHub Releases page. Open the latest release and pick the file that matches your computer. Windows gets a `.exe`, macOS gets a `.dmg`, and Linux gets either a `.deb` or an `.AppImage`. Each release is built automatically and the files are attached right there.

## Download and install

### Windows

Download the `.exe` installer and run it. It installs for all users on the machine, so you may see a prompt asking for permission to continue. The app needs Microsoft's WebView2 runtime, and if your machine does not already have it the installer fetches it for you, so there is nothing extra to install by hand.

When it finishes you will find OpenConstructionERP in the Start Menu and as a shortcut, both named "OpenConstructionERP". Click either one to launch it.

### macOS

Download the `.dmg`, open it, and drag OpenConstructionERP into your Applications folder. You need macOS 10.15 or later.

This build is ad-hoc signed but not yet notarized by Apple, so the first time you open it macOS may say it "is damaged and can't be opened" or otherwise block it. The app is not damaged. macOS quarantines anything downloaded from the web, and an app that Apple has not notarized trips that check. To clear it, open Terminal and run this once, then open the app normally:

```
xattr -dr com.apple.quarantine /Applications/OpenConstructionERP.app
```

On older macOS you can instead right-click the app and choose Open. On macOS Sequoia you may also need to approve it once under System Settings, in Privacy and Security, where macOS shows a button to open the app anyway. You only need to do this once.

### Linux

On Debian or Ubuntu, download the `.deb` and install it with your package manager. It depends on `libwebkit2gtk-4.1-0`, which your system will pull in if it is not already present. After that, launch OpenConstructionERP from your applications menu.

If you prefer something portable, download the `.AppImage` instead, make it executable, and run it. From a terminal that is:

```
chmod +x OpenConstructionERP*.AppImage
./OpenConstructionERP*.AppImage
```

## First launch

The very first time you open the app it sets up its local database, and that takes a little while, usually somewhere between 40 and 90 seconds. While it works you will see a branded loading screen telling you the setup is in progress. This is normal and it only happens once. Please let it finish without closing the window. Every launch after this one starts quickly.

## Sign in

Once the app is ready you will reach the sign-in screen. A demo account is ready to go so you can look around right away.

Email: demo@openconstructionerp.com
Password: DemoPass1234!

Sign in with those and you are in. You can create your own account and projects from there.

## Your data is local

Everything you do stays on your own machine. The app runs its own database locally and does not send your projects anywhere. It works offline, and your data is yours.

## Need help

If something does not work or you have a question, email us at info@datadrivenconstruction.io, or open an issue on the project's GitHub issues page. We are happy to help.
