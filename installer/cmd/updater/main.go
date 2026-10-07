// Updater.exe installs and updates FA11y: the private Python runtime, the
// virtual environment and its packages, FA11y's files, and the external
// components listed in installer/manifest.json.
//
// Exit codes: 0 nothing changed, 1 something was updated, 2 error,
// 3 an update is available (--check only).
package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
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
	// exitComponentsMissing is --components finishing with a component still
	// missing (declined, or its install failed).
	exitComponentsMissing = 5
)

type options struct {
	install, quick, check, fromLauncher, noComponents, componentsOnly bool
	branch, source                                    string
	waitPIDs                                          pidList
}

func main() {
	var opts options
	flag.BoolVar(&opts.install, "install", false, "install FA11y (also repairs an existing install)")
	flag.BoolVar(&opts.quick, "quick", false, "only update when a new FA11y version is out or the install needs repair")
	flag.BoolVar(&opts.check, "check", false, "only report whether --quick would update: exit 3 if so, 0 if not")
	flag.BoolVar(&opts.fromLauncher, "from-launcher", false, "started by FA11y_Launcher.exe")
	flag.StringVar(&opts.branch, "branch", "", "GitHub branch to install from (default: the branch last installed, or main)")
	flag.StringVar(&opts.source, "source", "", "install from this folder (an exported checkout) instead of GitHub, for testing")
	flag.BoolVar(&opts.noComponents, "no-components", false, "skip drivers and other external components, for testing")
	flag.BoolVar(&opts.componentsOnly, "components", false, "only install missing drivers and runtimes, asking again for ones declined before")
	monarch := flag.Bool("monarch", false, "retry failed downloads until they succeed")
	elevatedPlan := flag.String("elevated-plan", "", "internal: install the components in this plan file")
	plain := flag.Bool("console", false, "print progress as text in the console instead of showing a progress window")
	forceWindow := flag.Bool("window", false, "show the progress window even when started from a console or a pipe")
	flag.Bool("run-by-fa11y", false, "ignored; accepted for compatibility")
	flag.Bool("migrate", false, "convert an old single-folder install (also detected automatically)")
	flag.Var(&opts.waitPIDs, "wait-pid", "wait for this process to exit first (repeatable)")
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
	filesync.Progress = func(done, total int) { console.Progress(float64(done) * 100 / float64(total)) }

	// The progress window replaces the console when someone ran Updater.exe
	// (a console made for it) or the launcher is installing something. A
	// terminal, a pipe and --console keep the text output, and so does the
	// launcher's silent --check, which must never show anything.
	quietCheck := opts.check && opts.fromLauncher
	if !*plain && !quietCheck && (*forceWindow || opts.fromLauncher || console.OwnsConsole()) {
		console.UseWindow()
	}
	if opts.check && !opts.fromLauncher {
		console.Say("Checking for updates...")
	}

	l, err := layout.FromExecutable()
	if err != nil {
		console.Fail(exitError, "could not find the FA11y folder: %v", err)
	}
	code, err := run(l, opts)
	if restartedChild && console.InWindow() {
		os.Exit(code) // the new updater showed its own window
	}
	if err != nil {
		if console.InWindow() {
			console.Fail(exitError, "%v", err)
		}
		console.Say("Error: %v", err)
		code = exitError
	}
	if code == exitError && !opts.componentsOnly && (!opts.fromLauncher || console.InWindow()) {
		console.Fail(code, "the update did not finish.")
	}
	if !opts.fromLauncher {
		console.Finish(5 * time.Second)
	}
	os.Exit(code)
}

// restartedChild is set when restartSelf ran a newer updater in this one's place.
var restartedChild bool

func run(l layout.Layout, opts options) (int, error) {
	if err := os.MkdirAll(l.Files, 0o755); err != nil {
		return exitError, err
	}
	selfupdate.CleanupOld(l.Updater(), l.Launcher())
	renamedLauncher := renameOldLauncher(l)
	waitForExit(opts.waitPIDs)
	legacy := isLegacy(l)
	st, err := state.Load(l.Files)
	if err != nil {
		return exitError, err
	}
	if opts.componentsOnly {
		return installMissingComponents(l, st)
	}
	branch := resolveBranch(opts.branch, st.Branch)
	var src filesync.Source
	if opts.source != "" {
		console.Say("Installing from %s instead of GitHub.", opts.source)
		src = filesync.Local{Dir: opts.source}
	} else {
		if os.Getenv(restartedEnv) == "" && !opts.check {
			if restarted, code := updateExecutables(l, branch); restarted {
				return code, nil
			}
		}
		commit, err := filesync.Commit(defaultRepo, branch)
		if err != nil && opts.branch == "" && branch != defaultBranch && branchMissing(err) {
			if installed(l) && (opts.quick || opts.check) {
				// Routine launches never move an install to another branch on their own;
				// the branch may only be missing for a while.
				console.Say("The %s branch isn't on GitHub, so FA11y wasn't updated. Switch branches from About and updates, or run Updater.exe --branch main.", branch)
				return layout.ExitNoUpdate, nil
			}
			console.Say("The %s branch no longer exists on GitHub. Switching back to main.", branch)
			branch = defaultBranch
			commit, err = filesync.Commit(defaultRepo, branch)
		}
		if err != nil {
			if installed(l) && (opts.quick || opts.check) {
				console.Say("Could not reach GitHub (%v). Skipping the update check.", err)
				return layout.ExitNoUpdate, nil
			}
			return exitError, fmt.Errorf("could not reach GitHub: %w", err)
		}
		src = filesync.GitHub{Repo: defaultRepo, Commit: commit}
		// A first install with no branch chosen uses main once main can be
		// installed this way; until then it uses the Beta branch.
		if opts.branch == "" && st.Branch == "" && branch == defaultBranch {
			if _, err := src.Read(manifest.Path); branchMissing(err) {
				console.Say("Stable FA11y can't be installed with this updater yet, so FA11y installs from the Beta branch (%s).", betaBranch)
				branch = betaBranch
				commit, err = filesync.Commit(defaultRepo, branch)
				if err != nil {
					return exitError, fmt.Errorf("could not reach GitHub: %w", err)
				}
				src = filesync.GitHub{Repo: defaultRepo, Commit: commit}
			}
		}
		if !opts.check {
			ensureLauncher(l, branch, renamedLauncher && version != "dev")
		}
	}
	m, err := loadManifest(l, src)
	if err != nil {
		return exitError, err
	}
	switching := branchSwitch(installed(l), st.Branch, branch)

	if opts.check {
		// Read-only: the launcher runs this without a window and opens a
		// console for the real update only when there is one.
		available := true
		if !switching && !legacy && installed(l) {
			remote, err := src.Read("VERSION")
			available = err == nil && (versionNewer(strings.TrimSpace(string(remote)), readVersion(l)) || !healthy(l, m, st, opts.noComponents))
		}
		if !opts.fromLauncher {
			if available {
				console.Say("An update is available.")
			} else {
				console.Say("FA11y is up to date.")
			}
		}
		if available {
			return layout.ExitUpdateAvailable, nil
		}
		return layout.ExitNoUpdate, nil
	}

	if legacy {
		if _, err := prepareMigration(l); err != nil {
			return exitError, err
		}
		opts.quick, opts.install = false, true
	}

	localVersion := readVersion(l)
	if switching {
		console.Say("Switching FA11y to the %s branch.", branch)
		opts.quick = false
	}
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
	if err == nil {
		st.Branch = branch
	}
	if saveErr := st.Save(l.Files); err == nil {
		err = saveErr
	}
	if err != nil {
		return exitError, err
	}
	removeOldBackups(l)
	if legacy {
		if tree, err := src.Tree(); err == nil {
			cleanupLegacy(l, tree)
		}
		console.Say("FA11y now lives in %s. Start it with %s.", layout.FilesDirName, layout.LauncherExe)
		if !opts.fromLauncher {
			startLauncher(l)
		}
		return layout.ExitUpdated, nil
	}
	if !changed && !switching {
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
	console.Progress(-1)
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

// installMissingComponents is --components. FA11y runs it when a runtime or
// driver it needs is missing. It asks again for components declined before and
// changes nothing else, so it is safe while FA11y is running.
func installMissingComponents(l layout.Layout, st *state.State) (int, error) {
	m, err := manifest.Load(filepath.Join(l.Files, manifestCopy))
	if err != nil {
		if m, err = manifest.Load(filepath.Join(l.Files, filepath.FromSlash(manifest.Path))); err != nil {
			return exitError, fmt.Errorf("could not read the install manifest: %w", err)
		}
	}
	if _, err := installComponents(l, m, st, false); err != nil {
		return exitError, err
	}
	if err := st.Save(l.Files); err != nil {
		return exitError, err
	}
	for _, c := range m.Components {
		if !components.Installed(c, l.Files) {
			return exitComponentsMissing, nil
		}
	}
	console.Say("Everything FA11y needs is installed.")
	return layout.ExitNoUpdate, nil
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

// updateExecutables replaces Updater.exe and FA11y_Launcher.exe with the
// newest installer release. When Updater.exe itself was replaced, it
// starts the new copy and returns its exit code.
func updateExecutables(l layout.Layout, branch string) (restarted bool, code int) {
	if version == "dev" {
		return false, 0
	}
	rel, err := selfupdate.Latest(defaultRepo, branch != defaultBranch)
	if err != nil || rel == nil || !selfupdate.Newer(rel.Version, version) {
		return false, 0
	}
	console.Say("Updating the FA11y updater to version %s...", rel.Version)
	if a, ok := launcherAsset(rel); ok {
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

// ensureLauncher downloads FA11y_Launcher.exe from the newest installer
// release when it isn't next to the updater, so Updater.exe alone is enough
// to install FA11y. replace downloads it even when it is there: a launcher
// renamed from an old name is an old build.
func ensureLauncher(l layout.Layout, branch string, replace bool) {
	if _, err := os.Stat(l.Launcher()); err == nil && !replace {
		return
	}
	rel, err := selfupdate.Latest(defaultRepo, branch != defaultBranch)
	if err != nil || rel == nil {
		console.Say("Could not find %s on GitHub. Download it from the FA11y releases page.", layout.LauncherExe)
		return
	}
	a, ok := launcherAsset(rel)
	if !ok {
		return
	}
	console.Say("Downloading %s...", layout.LauncherExe)
	if err := selfupdate.Replace(l.Launcher(), a); err != nil {
		console.Say("Could not download %s: %v", layout.LauncherExe, err)
	}
}

// launcherAsset finds the launcher in a release. Older releases
// named it "FA11y Launcher.exe", which GitHub published as
// "FA11y.Launcher.exe".
func launcherAsset(rel *selfupdate.Release) (selfupdate.Asset, bool) {
	for _, name := range append([]string{layout.LauncherExe}, layout.LegacyLauncherExes...) {
		if a, ok := rel.Assets[name]; ok {
			return a, true
		}
	}
	return selfupdate.Asset{}, false
}

// renameOldLauncher gives the launcher its current name, FA11y_Launcher.exe,
// when it still has an old one. An old copy that can't be removed (it is the
// launcher that started this update) is set aside as "<name>.old" and removed
// on a later run. It reports whether an old launcher took the new name.
func renameOldLauncher(l layout.Layout) (renamed bool) {
	for _, name := range layout.LegacyLauncherExes {
		old := filepath.Join(l.Root, name)
		selfupdate.CleanupOld(old)
		if _, err := os.Stat(old); err != nil {
			continue
		}
		if _, err := os.Stat(l.Launcher()); err != nil {
			if err := os.Rename(old, l.Launcher()); err != nil {
				console.Say("Could not rename %s to %s: %v", name, layout.LauncherExe, err)
			} else {
				renamed = true
			}
			continue
		}
		if os.Remove(old) != nil {
			os.Rename(old, old+".old")
		}
	}
	return renamed
}

func restartSelf(l layout.Layout) int {
	os.Setenv(restartedEnv, "1")
	attr := &os.ProcAttr{Dir: l.Root, Env: os.Environ(), Files: []*os.File{os.Stdin, os.Stdout, os.Stderr}}
	args := os.Args
	if console.InWindow() {
		// The new updater shows its own window.
		console.Hide()
		attr.Files = nil
		attr.Sys = &syscall.SysProcAttr{HideWindow: true, CreationFlags: windows.CREATE_NO_WINDOW}
		args = append(slices.Clone(args), "--window")
	}
	restartedChild = true
	p, err := os.StartProcess(l.Updater(), args, attr)
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
// versionNewer reports whether remote is newer than local. Versions look like
// "18.11.17" or "19.0.0-beta.1"; a pre-release sorts before its release.
func versionNewer(remote, local string) bool {
	if local == "" {
		return true
	}
	rCore, rPre, _ := strings.Cut(remote, "-")
	lCore, lPre, _ := strings.Cut(local, "-")
	if c := compareNumbers(rCore, lCore); c != 0 {
		return c > 0
	}
	switch {
	case rPre == "" && lPre == "":
		return false
	case rPre == "":
		return true // the release after a pre-release
	case lPre == "":
		return false
	}
	return compareNumbers(rPre, lPre) > 0
}

// compareNumbers compares dot separated numbers, ignoring parts that aren't numbers.
func compareNumbers(a, b string) int {
	numbers := func(s string) []int {
		var out []int
		for _, part := range strings.Split(s, ".") {
			var n int
			if _, err := fmt.Sscan(part, &n); err == nil {
				out = append(out, n)
			}
		}
		return out
	}
	x, y := numbers(a), numbers(b)
	for i := 0; i < len(x) || i < len(y); i++ {
		var p, q int
		if i < len(x) {
			p = x[i]
		}
		if i < len(y) {
			q = y[i]
		}
		if p != q {
			if p > q {
				return 1
			}
			return -1
		}
	}
	return 0
}

func isElevated() bool {
	return windows.GetCurrentProcessToken().IsElevated()
}

func offerChangelog(l layout.Layout, newVersion string) {
	path := filepath.Join(l.Files, "CHANGELOG.txt")
	if _, err := os.Stat(path); err != nil {
		return
	}
	open := false
	if console.InWindow() {
		open = console.Ask("FA11y was updated to " + newVersion + ". Open the changelog?")
	} else {
		console.Say("FA11y was updated to %s. Type Y and press Enter to open the changelog, or press Enter to continue.", newVersion)
		answer, _ := bufio.NewReader(os.Stdin).ReadString('\n')
		open = strings.EqualFold(strings.TrimSpace(answer), "y")
	}
	if open {
		verb, _ := windows.UTF16PtrFromString("open")
		file, _ := windows.UTF16PtrFromString(path)
		windows.ShellExecute(0, verb, file, nil, nil, windows.SW_SHOWNORMAL)
	}
}
