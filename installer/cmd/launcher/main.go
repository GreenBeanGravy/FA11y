// FA11y Launcher.exe starts FA11y inside its private virtual environment.
//
// Before starting FA11y it runs Updater.exe: a full install when FA11y is
// missing, or a quick update check when the AutoUpdates setting is on.
// Updates happen here, before Python starts, because pip cannot replace
// files that a running FA11y has loaded from the venv.
//
// The launcher is built with -H windowsgui, so starting FA11y opens no
// console window. It opens one only to install or update (a hidden
// "Updater.exe --check" decides whether there is an update) or to report
// an error. FA11y itself runs under pythonw.exe without a console: its
// window is the user interface. Pass --console to run it under python.exe
// in a console instead, which shows FA11y's printed output for
// troubleshooting. Pass --update to update first even when AutoUpdates is
// off (FA11y's "Restart to update" button does this).
package main

import (
	"errors"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"slices"
	"syscall"

	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/fa11yconfig"
	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
	"github.com/GreenBeanGravy/FA11y/installer/internal/pyenv"
)

const (
	detachedProcess = 0x00000008
	createNoWindow  = 0x08000000
	asfwAny         = ^uintptr(0) // ASFW_ANY
)

var allowSetForegroundWindow = syscall.NewLazyDLL("user32.dll").NewProc("AllowSetForegroundWindow")

func main() {
	console.SetTitle("FA11y")
	// Ctrl+C belongs to FA11y, which shares this console.
	signal.Ignore(os.Interrupt)

	l, err := layout.FromExecutable()
	if err != nil {
		console.Fail(2, "could not find the FA11y folder: %v", err)
	}

	if !installed(l) {
		console.Say("FA11y is not installed yet. Starting the updater to install it.")
		code := runUpdater(l, "--install")
		if (code != layout.ExitNoUpdate && code != layout.ExitUpdated) || !installed(l) {
			console.Fail(2, "the install did not finish (updater exit code %d).", code)
		}
	} else if forced := slices.Contains(os.Args[1:], "--update"); (forced || fa11yconfig.Bool(l.ConfigFile(), "AutoUpdates", true)) && checkForUpdate(l) {
		code := runUpdater(l, "--quick")
		if code != layout.ExitNoUpdate && code != layout.ExitUpdated {
			console.Say("The update failed (exit code %d). Starting the installed version.", code)
		}
	}

	if err := repairVenv(l); err != nil {
		console.Fail(2, "FA11y's Python environment is damaged: %v. Run Updater.exe to repair it.", err)
	}
	if slices.Contains(os.Args[1:], "--console") {
		console.Ensure()
		os.Exit(runFA11y(l))
	}
	if err := startFA11yWindowed(l); err != nil {
		console.Fail(2, "could not start FA11y: %v", err)
	}
}

func installed(l layout.Layout) bool {
	for _, path := range []string{l.VenvPython(), l.Entry()} {
		if _, err := os.Stat(path); err != nil {
			return false
		}
	}
	return true
}

// repairVenv re-points the venv at the bundled Python when the install
// folder has been moved since the venv was created.
func repairVenv(l layout.Layout) error {
	cfg, err := pyenv.ReadConfig(l.VenvDir())
	if err != nil {
		return err
	}
	version := cfg.Version()
	if version == "" {
		return errors.New("pyvenv.cfg has no Python version")
	}
	changed, err := cfg.Relocate(l.RuntimeDir(version))
	if changed {
		console.Say("Updated the Python environment for the new install location.")
	}
	return err
}

func runUpdater(l layout.Layout, args ...string) int {
	if _, err := os.Stat(l.Updater()); err != nil {
		console.Say("%s is missing, so FA11y cannot install or update.", layout.UpdaterExe)
		return 2
	}
	console.Ensure() // the updater shares this console
	cmd := exec.Command(l.Updater(), append(args, "--from-launcher")...)
	cmd.Dir = l.Root
	return run(cmd)
}

// checkForUpdate runs "Updater.exe --check" without a window and reports
// whether there is an update to install. A failed check (no network, no
// updater) counts as no update, so FA11y still starts quietly.
func checkForUpdate(l layout.Layout) bool {
	if _, err := os.Stat(l.Updater()); err != nil {
		return false
	}
	cmd := exec.Command(l.Updater(), "--check", "--from-launcher")
	cmd.Dir = l.Root
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	err := cmd.Run()
	var exitErr *exec.ExitError
	return errors.As(err, &exitErr) && exitErr.ExitCode() == layout.ExitUpdateAvailable
}

func fa11yCommand(l layout.Layout, python string) *exec.Cmd {
	// -E ignores any PYTHON* variables that CleanEnv missed.
	cmd := exec.Command(python, "-E", l.Entry())
	cmd.Dir = l.Files
	cmd.Env = append(pyenv.CleanEnv(os.Environ()),
		"FA11Y_LAUNCHER="+l.Launcher(),
	)
	return cmd
}

// runFA11y runs FA11y in this console and returns its exit code.
func runFA11y(l layout.Layout) int {
	return run(fa11yCommand(l, l.VenvPython()))
}

// startFA11yWindowed starts FA11y under pythonw.exe, detached from this
// console, and returns without waiting so the console window closes.
func startFA11yWindowed(l layout.Layout) error {
	pythonw := filepath.Join(filepath.Dir(l.VenvPython()), "pythonw.exe")
	if _, err := os.Stat(pythonw); err != nil {
		os.Exit(runFA11y(l))
	}
	cmd := fa11yCommand(l, pythonw)
	// The user just started FA11y, so its window may take the foreground.
	allowSetForegroundWindow.Call(asfwAny)
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: detachedProcess | syscall.CREATE_NEW_PROCESS_GROUP}
	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}

func run(cmd *exec.Cmd) int {
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	err := cmd.Run()
	var exitErr *exec.ExitError
	switch {
	case err == nil:
		return 0
	case errors.As(err, &exitErr):
		return exitErr.ExitCode()
	default:
		console.Say("Could not start %s: %v", cmd.Path, err)
		return 2
	}
}
