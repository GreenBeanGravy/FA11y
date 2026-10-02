// Updater.exe installs and updates FA11y: the private Python runtime, the
// virtual environment and its packages, FA11y's files, and the external
// components listed in installer/manifest.json.
//
// Exit codes: 0 nothing changed, 1 something was updated, 2 error.
package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows"

	"github.com/GreenBeanGravy/FA11y/installer/internal/components"
	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
	"github.com/GreenBeanGravy/FA11y/installer/internal/filesync"
	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
	"github.com/GreenBeanGravy/FA11y/installer/internal/selfupdate"
	"github.com/GreenBeanGravy/FA11y/installer/internal/state"
)

// version is set at build time: -ldflags "-X main.version=1.2.3".
// Development builds ("dev") never replace themselves.
var version = "dev"

const (
	defaultRepo   = "GreenBeanGravy/FA11y"
	defaultBranch = "main"
	restartedEnv  = "FA11Y_UPDATER_RESTARTED"
	manifestCopy  = ".fa11y-manifest.json"
	exitError     = 2
)

type options struct {
	install, quick, fromLauncher, noComponents bool
	branch, source                             string
}

func main() {
	var opts options
	flag.BoolVar(&opts.install, "install", false, "install FA11y (also repairs an existing install)")
	flag.BoolVar(&opts.quick, "quick", false, "only update when a new FA11y version is out or the install needs repair")
	flag.BoolVar(&opts.fromLauncher, "from-launcher", false, "started by FA11y Launcher.exe")
	flag.StringVar(&opts.branch, "branch", defaultBranch, "GitHub branch to install from")
	flag.StringVar(&opts.source, "source", "", "install from this folder (an exported checkout) instead of GitHub, for testing")
	flag.BoolVar(&opts.noComponents, "no-components", false, "skip drivers and other external components, for testing")
	monarch := flag.Bool("monarch", false, "retry failed downloads until they succeed")
	elevatedPlan := flag.String("elevated-plan", "", "internal: install the components in this plan file")
	flag.Bool("run-by-fa11y", false, "ignored; accepted for compatibility")
	flag.Parse()

	console.SetTitle("FA11y Updater")
	if *elevatedPlan != "" {
		if err := components.RunPlan(*elevatedPlan, console.Say); err != nil {
			console.Say("Error: %v", err)
			os.Exit(exitError)
		}
		return
	}
	fetch.Persistent = *monarch

	l, err := layout.FromExecutable()
	if err != nil {
		console.Fail(exitError, "could not find the FA11y folder: %v", err)
	}
	code, err := run(l, opts)
	if err != nil {
		console.Say("Error: %v", err)
		code = exitError
	}
	if !opts.fromLauncher {
		if code == exitError {
			console.Fail(code, "the update did not finish.")
		}
		console.Say("Closing in 5 seconds.")
		time.Sleep(5 * time.Second)
	}
	os.Exit(code)
}

func run(l layout.Layout, opts options) (int, error) {
	if err := os.MkdirAll(l.Files, 0o755); err != nil {
		return exitError, err
	}
	selfupdate.CleanupOld(l.Updater(), l.Launcher())
	var src filesync.Source
	if opts.source != "" {
		console.Say("Installing from %s instead of GitHub.", opts.source)
		src = filesync.Local{Dir: opts.source}
	} else {
		if os.Getenv(restartedEnv) == "" {
			if restarted, code := updateExecutables(l); restarted {
				return code, nil
			}
		}
		commit, err := filesync.Commit(defaultRepo, opts.branch)
		if err != nil {
			if installed(l) && opts.quick {
				console.Say("Could not reach GitHub (%v). Skipping the update check.", err)
				return layout.ExitNoUpdate, nil
			}
			return exitError, fmt.Errorf("could not reach GitHub: %w", err)
		}
		src = filesync.GitHub{Repo: defaultRepo, Commit: commit}
	}
	m, err := loadManifest(l, src)
	if err != nil {
		return exitError, err
	}
	st, err := state.Load(l.Files)
	if err != nil {
		return exitError, err
	}

	localVersion := readVersion(l)
	if opts.quick && installed(l) {
		remote, err := src.Read("VERSION")
		if err == nil && !versionNewer(strings.TrimSpace(string(remote)), localVersion) && healthy(l, m, st, opts.noComponents) {
			console.Say("FA11y is up to date.")
			return layout.ExitNoUpdate, nil
		}
	}

	if !installed(l) {
		console.Say("Installing FA11y into %s", l.Files)
	} else {
		console.Say("Updating FA11y...")
	}
	changed, err := update(l, m, src, st, opts)
	if saveErr := st.Save(l.Files); err == nil {
		err = saveErr
	}
	if err != nil {
		return exitError, err
	}
	if !changed {
		console.Say("FA11y is up to date.")
		return layout.ExitNoUpdate, nil
	}
	newVersion := readVersion(l)
	console.Say("FA11y %s is installed and up to date.", newVersion)
	if localVersion != "" && newVersion != localVersion && opts.fromLauncher {
		offerChangelog(l, newVersion)
	}
	return layout.ExitUpdated, nil
}

func update(l layout.Layout, m *manifest.Manifest, src filesync.Source, st *state.State, opts options) (bool, error) {
	changed, err := ensureRuntime(l, m.Python)
	if err != nil {
		return changed, fmt.Errorf("installing Python failed: %w", err)
	}
	newVenv, err := ensureVenv(l, m.Python)
	if err != nil {
		return changed, fmt.Errorf("creating the Python environment failed: %w", err)
	}
	if newVenv {
		st.LockSHA256 = ""
		changed = true
	}

	console.Say("Checking FA11y files...")
	tree, err := src.Tree()
	if err != nil {
		return changed, err
	}
	res, err := filesync.Sync(l.Files, src, m.Sync, tree, st, console.Say)
	if res.Changed() {
		changed = true
		console.Say("Updated %d files, removed %d.", len(res.Updated), len(res.Removed))
	}
	if err != nil {
		return changed, err
	}
	if err := st.Save(l.Files); err != nil {
		return changed, err
	}

	hash, installedPackages, err := ensureRequirements(l, m.Requirements, st.LockSHA256, opts.install && !newVenv)
	if err != nil {
		return changed, err
	}
	st.LockSHA256 = hash
	changed = changed || installedPackages

	if opts.noComponents {
		return changed, nil
	}
	compChanged, err := installComponents(l, m, st, opts.quick)
	return changed || compChanged, err
}

// installComponents installs every missing component. Elevated components
// share one UAC prompt. In quick mode, components the user declined before
// are not asked for again.
func installComponents(l layout.Layout, m *manifest.Manifest, st *state.State, quick bool) (bool, error) {
	var missing []manifest.Component
	for _, c := range m.Components {
		if components.Installed(c, l.Files) {
			st.SetDeclined(c.ID, false)
			continue
		}
		if quick && st.IsDeclined(c.ID) {
			continue
		}
		missing = append(missing, c)
	}
	if len(missing) == 0 {
		return false, nil
	}

	staging := filepath.Join(l.Files, ".downloads")
	if err := os.MkdirAll(staging, 0o755); err != nil {
		return false, err
	}
	changed := false
	var plan components.Plan
	plan.FilesDir = l.Files
	for _, c := range missing {
		console.Say("Downloading %s. %s", c.Name, c.Reason)
		file, err := components.Download(c, staging)
		if err != nil {
			console.Say("Could not download %s: %v", c.Name, err)
			continue
		}
		if c.Elevate && !isElevated() {
			plan.Items = append(plan.Items, components.PlanItem{Component: c, File: file})
			continue
		}
		changed = report(c, components.Install(c, file, l.Files), st) || changed
	}

	if len(plan.Items) > 0 {
		var names []string
		for _, item := range plan.Items {
			names = append(names, item.Component.Name)
		}
		console.Say("Installing %s needs administrator permission. Windows will ask you to allow it.", strings.Join(names, " and "))
		done, err := components.RunElevated(l.Updater(), staging, plan)
		switch {
		case errors.Is(err, components.ErrCancelled):
			for _, item := range plan.Items {
				st.SetDeclined(item.Component.ID, true)
			}
			console.Say("Skipped installing %s. Some features will not work until you run Updater.exe and allow it.", strings.Join(names, " and "))
		case err != nil:
			console.Say("Could not install %s: %v", strings.Join(names, " and "), err)
		default:
			for _, item := range plan.Items {
				changed = report(item.Component, done.Results[item.Component.ID], st) || changed
			}
		}
	}
	os.RemoveAll(staging)
	return changed, nil
}

func report(c manifest.Component, out components.Outcome, st *state.State) bool {
	if !out.OK {
		console.Say("%s was not installed: %s", c.Name, out.Error)
		return false
	}
	st.SetDeclined(c.ID, false)
	if out.Reboot {
		console.Say("%s is installed. Restart Windows to finish setting it up.", c.Name)
	} else {
		console.Say("%s is installed.", c.Name)
	}
	return true
}

// updateExecutables replaces Updater.exe and FA11y Launcher.exe with the
// newest installer release. When Updater.exe itself was replaced, it
// starts the new copy and returns its exit code.
func updateExecutables(l layout.Layout) (restarted bool, code int) {
	if version == "dev" {
		return false, 0
	}
	rel, err := selfupdate.Latest(defaultRepo)
	if err != nil || rel == nil || !selfupdate.Newer(rel.Version, version) {
		return false, 0
	}
	console.Say("Updating the FA11y updater to version %s...", rel.Version)
	if a, ok := rel.Assets[layout.LauncherExe]; ok {
		if err := selfupdate.Replace(l.Launcher(), a); err != nil {
			console.Say("Could not update %s: %v", layout.LauncherExe, err)
		}
	}
	a, ok := rel.Assets[layout.UpdaterExe]
	if !ok {
		return false, 0
	}
	if err := selfupdate.Replace(l.Updater(), a); err != nil {
		console.Say("Could not update %s: %v", layout.UpdaterExe, err)
		return false, 0
	}
	return true, restartSelf(l)
}

func restartSelf(l layout.Layout) int {
	os.Setenv(restartedEnv, "1")
	attr := &os.ProcAttr{Dir: l.Root, Env: os.Environ(), Files: []*os.File{os.Stdin, os.Stdout, os.Stderr}}
	p, err := os.StartProcess(l.Updater(), os.Args, attr)
	if err != nil {
		console.Say("Could not start the new updater: %v", err)
		return exitError
	}
	s, err := p.Wait()
	if err != nil {
		return exitError
	}
	return s.ExitCode()
}

// loadManifest reads the manifest from src and keeps a copy for when
// GitHub is unreachable.
func loadManifest(l layout.Layout, src filesync.Source) (*manifest.Manifest, error) {
	copyPath := filepath.Join(l.Files, manifestCopy)
	data, err := src.Read(manifest.Path)
	if err != nil {
		console.Say("Could not download the install manifest (%v). Using the saved copy.", err)
		return manifest.Load(copyPath)
	}
	m, err := manifest.Parse(data)
	if err != nil {
		return nil, err
	}
	os.WriteFile(copyPath, data, 0o644)
	return m, nil
}

func installed(l layout.Layout) bool {
	for _, p := range []string{l.VenvPython(), l.Entry()} {
		if _, err := os.Stat(p); err != nil {
			return false
		}
	}
	return true
}

// healthy reports whether the install is complete: runtime, venv, current
// packages, and every component (or the user declined it).
func healthy(l layout.Layout, m *manifest.Manifest, st *state.State, noComponents bool) bool {
	if !runtimeReady(l, m.Python) || !venvReady(l, m.Python) {
		return false
	}
	if _, changed, err := lockHash(l, m.Requirements, st.LockSHA256); err != nil || changed {
		return false
	}
	for _, c := range m.Components {
		if !noComponents && !st.IsDeclined(c.ID) && !components.Installed(c, l.Files) {
			return false
		}
	}
	return true
}

func lockHash(l layout.Layout, name, installed string) (string, bool, error) {
	data, err := os.ReadFile(filepath.Join(l.Files, name))
	if err != nil {
		return "", true, err
	}
	h := sha256Hex(data)
	return h, h != installed, nil
}

func readVersion(l layout.Layout) string {
	data, err := os.ReadFile(filepath.Join(l.Files, "VERSION"))
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// versionNewer compares FA11y's dotted versions ("18.11.16").
func versionNewer(remote, local string) bool {
	if local == "" {
		return true
	}
	r, l := strings.Split(remote, "."), strings.Split(local, ".")
	for i := 0; i < len(r) || i < len(l); i++ {
		var a, b int
		if i < len(r) {
			fmt.Sscan(r[i], &a)
		}
		if i < len(l) {
			fmt.Sscan(l[i], &b)
		}
		if a != b {
			return a > b
		}
	}
	return false
}

func isElevated() bool {
	return windows.GetCurrentProcessToken().IsElevated()
}

func offerChangelog(l layout.Layout, newVersion string) {
	path := filepath.Join(l.Files, "CHANGELOG.txt")
	if _, err := os.Stat(path); err != nil {
		return
	}
	console.Say("FA11y was updated to %s. Type Y and press Enter to open the changelog, or press Enter to continue.", newVersion)
	answer, _ := bufio.NewReader(os.Stdin).ReadString('\n')
	if strings.EqualFold(strings.TrimSpace(answer), "y") {
		verb, _ := windows.UTF16PtrFromString("open")
		file, _ := windows.UTF16PtrFromString(path)
		windows.ShellExecute(0, verb, file, nil, nil, windows.SW_SHOWNORMAL)
	}
}
