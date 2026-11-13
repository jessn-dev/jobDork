# The desktop app in Docker

For trying the **Linux desktop app** — its own window, with the Qt web engine
the AppImage and the .deb carry — on a Mac or a Windows PC, without a Linux
computer. The window runs in a container and shows in your browser.

This is for testing a change to jobdork in the real window. To use jobdork,
take the [desktop app](desktop.md) or the [server image](docker.md).

## Start it

From the repository, with Docker running:

```
docker compose -f docker/desktop/compose.yaml up --build
```

Then open **http://localhost:6080/vnc.html** and press **Connect**. jobdork's
window is on that screen, built from this checkout: change the code, run the
command again, and the window shows the change. Close the window, or press
Ctrl+C in the terminal, to stop it.

- **Your settings and job posts** stay in a Docker volume
  (`jobdork-desktop-data`) between runs, apart from any jobdork on your own
  computer. `docker volume rm desktop_jobdork-desktop-data` starts from setup
  again.
- **The address works on this computer only** (`127.0.0.1`): the screen has no
  password, so it is not published to your network.
- **A Mac with Apple Silicon** runs the ARM64 build, the same one as a
  Raspberry Pi or an ARM Linux PC; an Intel Mac or a Windows PC runs the x86-64
  one.

## Check the build without a window

```
docker compose -f docker/desktop/compose.yaml run --rm desktop self-test
```

It runs the installed app's own check (`--self-test`), prints `ok`, or what
the window would be missing (a library, a data file), and exits 1 if anything
is.

## The Windows and Mac apps

Neither can run this way on a Mac:

- **The Mac app** runs on macOS only. Docker on a Mac runs Linux, and Apple's
  licence allows macOS only on Apple's own computers. Run the Mac app on the
  Mac itself: `./run.sh` for the browser, `jobdork app` for the window, or
  the installer from a pull request's checks (Actions → the run → Artifacts).
- **The Windows app** needs Windows. Containers that start a Windows virtual
  machine need hardware virtualisation (KVM), which Docker on a Mac does not
  offer. Use a Windows PC or a virtual machine (UTM, Parallels, VMware), and
  the installer from a pull request's checks. Each pull request's CI already
  installs the Windows, Linux and Microsoft Store builds for real and opens
  them (.github/workflows/desktop.yml).
