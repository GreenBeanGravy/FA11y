// FA11y Launcher.exe starts FA11y inside its private virtual environment.
//
// Before starting FA11y it runs Updater.exe: a full install when FA11y is
// missing, or a quick update check when the AutoUpdates setting is on.
// Updates happen here, before Python starts, because pip cannot replace
// files that a running FA11y has loaded from the venv.
package main

import (
	"errors"
	"os"
	"os/exec"
	"os/signal"

	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/fa11yconfig"
	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
	"github.com/GreenBeanGravy/FA11y/installer/internal/pyenv"
)

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
	} else if fa11yconfig.Bool(l.ConfigFile(), "AutoUpdates", true) {
		code := runUpdater(l, "--quick")
		if code != layout.ExitNoUpdate && code != layout.ExitUpdated {
			console.Say("The update check failed (exit code %d). Starting the installed version.", code)
		}
	}

	if err := repairVenv(l); err != nil {
		console.Fail(2, "FA11y's Python environment is damaged: %v. Run Updater.exe to repair it.", err)
	}
	os.Exit(runFA11y(l))
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
	cmd := exec.Command(l.Updater(), append(args, "--from-launcher")...)
	cmd.Dir = l.Root
	return run(cmd)
}

func runFA11y(l layout.Layout) int {
	// -E ignores any PYTHON* variables that CleanEnv missed.
	cmd := exec.Command(l.VenvPython(), "-E", l.Entry())
	cmd.Dir = l.Files
	cmd.Env = append(pyenv.CleanEnv(os.Environ()),
		"FA11Y_LAUNCHER="+l.Launcher(),
	)
	return run(cmd)
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
