package main

import (
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	"golang.org/x/sys/windows"

	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/filesync"
	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
)

// Older FA11y versions kept everything in one folder and ran on the
// user's own Python. Updater.exe placed in that folder moves the install
// to the new layout:
//
//  1. back up user data to FA11y_backup_<time>
//  2. copy user data into FA11y Files
//  3. install FA11y into FA11y Files as usual
//  4. remove the old program files from the root folder
//
// Only paths the old installer put there are removed. Anything else the
// user keeps in the folder stays.

const backupPrefix = "FA11y_backup_"

// legacyConfigFiles are user files very old versions kept in the root
// folder instead of config\.
var legacyConfigFiles = []string{
	"config.txt", "CUSTOM_POI.txt", "FAVORITE_POIS.txt",
	"epic_auth_cache.json", "fortnite_locker_cache.json", "display_name_cache.json",
	"social_cache.json", "favorite_friends.json", "mouse_config.json",
}

// legacyExtras are generated files of the old layout that are not in the
// repository.
var legacyExtras = []string{"README.txt", "legendary.exe", "FortniteManager.py", "config", "logs", "debug", "whls", "__pycache__"}

// isLegacy reports whether the root folder holds an old single-folder install.
func isLegacy(l layout.Layout) bool {
	_, err := os.Stat(filepath.Join(l.Root, "FA11y.py"))
	return err == nil
}

// waitForExit waits up to two minutes for each process to exit, so files
// they hold open can be moved.
func waitForExit(pids []int) {
	for _, pid := range pids {
		h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
		if err != nil {
			continue // already gone
		}
		console.Say("Waiting for the old FA11y to close...")
		windows.WaitForSingleObject(h, 120000)
		windows.CloseHandle(h)
	}
}

// prepareMigration backs up user data and copies it into FA11y Files.
func prepareMigration(l layout.Layout) (string, error) {
	if _, err := os.Stat(filepath.Join(l.Root, ".git")); err == nil {
		return "", fmt.Errorf("%s is a git checkout, so it will not be converted to the new layout", l.Root)
	}
	console.Say("Moving FA11y to the new install layout. Your settings are backed up first.")
	backup := filepath.Join(l.Root, backupPrefix+time.Now().Format("20060102-150405"))

	copies := []struct{ from, to string }{
		{"config", "config"},
		{"logs", "logs"},
		{filepath.Join("assets", "sounds"), filepath.Join("assets", "sounds")},
	}
	for _, name := range legacyConfigFiles {
		copies = append(copies, struct{ from, to string }{name, name})
	}
	matches, _ := filepath.Glob(filepath.Join(l.Root, "*.premigration"))
	for _, m := range matches {
		copies = append(copies, struct{ from, to string }{filepath.Base(m), filepath.Base(m)})
	}
	for _, c := range copies {
		src := filepath.Join(l.Root, c.from)
		if _, err := os.Stat(src); err != nil {
			continue
		}
		if err := copyTree(src, filepath.Join(backup, c.to), true); err != nil {
			return "", fmt.Errorf("backing up %s failed: %w", c.from, err)
		}
	}

	// Restore into the new layout without overwriting anything already there.
	restores := []struct{ from, to string }{
		{"config", "config"},
		{filepath.Join("assets", "sounds"), filepath.Join("assets", "sounds")},
	}
	for _, name := range legacyConfigFiles {
		restores = append(restores, struct{ from, to string }{name, filepath.Join("config", name)})
	}
	for _, r := range restores {
		src := filepath.Join(backup, r.from)
		if _, err := os.Stat(src); err != nil {
			continue
		}
		if err := copyTree(src, filepath.Join(l.Files, r.to), false); err != nil {
			return "", fmt.Errorf("restoring %s failed: %w", r.from, err)
		}
	}
	console.Say("Settings backed up to %s", backup)
	return backup, nil
}

// cleanupLegacy removes the old program files from the root folder.
func cleanupLegacy(l layout.Layout, tree []filesync.Entry) {
	top := map[string]bool{}
	for _, e := range tree {
		top[strings.SplitN(e.Path, "/", 2)[0]] = true
	}
	for _, name := range legacyExtras {
		top[name] = true
	}
	// Root-level config files are in the backup and in FA11y Files\config.
	for _, name := range legacyConfigFiles {
		top[name] = true
	}
	premigration, _ := filepath.Glob(filepath.Join(l.Root, "*.premigration"))
	for _, m := range premigration {
		top[filepath.Base(m)] = true
	}
	keep := map[string]bool{
		layout.FilesDirName: true, layout.LauncherExe: true, layout.UpdaterExe: true,
	}
	var names []string
	for name := range top {
		if !keep[name] && !strings.HasPrefix(name, backupPrefix) {
			names = append(names, name)
		}
	}
	sort.Strings(names)
	for _, name := range names {
		path := filepath.Join(l.Root, name)
		info, err := os.Lstat(path)
		if err != nil {
			continue
		}
		if info.IsDir() {
			err = removeTrackedDir(l.Root, name, tree)
		} else {
			err = os.Remove(path)
		}
		if err != nil {
			console.Say("Could not remove old %s: %v", name, err)
		}
	}
}

// removeTrackedDir removes a top-level folder of the old install. Folders
// that only held program or generated files are removed entirely; a
// folder like assets\ keeps any files the repository never had.
func removeTrackedDir(root, name string, tree []filesync.Entry) error {
	full := filepath.Join(root, name)
	for _, extra := range legacyExtras {
		if name == extra {
			return os.RemoveAll(full)
		}
	}
	tracked := map[string]bool{}
	for _, e := range tree {
		tracked[filepath.FromSlash(e.Path)] = true
	}
	var dirs []string
	err := filepath.WalkDir(full, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(root, p)
		if d.IsDir() {
			if d.Name() == "__pycache__" {
				os.RemoveAll(p)
				return filepath.SkipDir
			}
			dirs = append(dirs, p)
			return nil
		}
		if tracked[rel] || strings.HasPrefix(rel, filepath.Join("assets", "sounds")+string(os.PathSeparator)) {
			return os.Remove(p)
		}
		return nil
	})
	// Remove now-empty folders, deepest first.
	for i := len(dirs) - 1; i >= 0; i-- {
		os.Remove(dirs[i])
	}
	return err
}

// removeOldBackups deletes migration backups older than two weeks.
func removeOldBackups(l layout.Layout) {
	matches, _ := filepath.Glob(filepath.Join(l.Root, backupPrefix+"*"))
	for _, m := range matches {
		if info, err := os.Stat(m); err == nil && time.Since(info.ModTime()) > 14*24*time.Hour {
			os.RemoveAll(m)
		}
	}
}

// startLauncher opens FA11y in a new console window after a migration.
func startLauncher(l layout.Layout) {
	cmd := exec.Command(l.Launcher())
	cmd.Dir = l.Root
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_CONSOLE}
	if err := cmd.Start(); err != nil {
		console.Say("Start FA11y with %s.", layout.LauncherExe)
	}
}

// copyTree copies a file or folder. With overwrite false, existing files
// at the destination are kept.
func copyTree(src, dest string, overwrite bool) error {
	return filepath.WalkDir(src, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		target := filepath.Join(dest, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		if !overwrite {
			if _, err := os.Stat(target); err == nil {
				return nil
			}
		}
		return copyFile(p, target)
	})
}

func copyFile(src, dest string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	_, err = io.Copy(out, in)
	if closeErr := out.Close(); err == nil {
		err = closeErr
	}
	return err
}

// pidList is a repeatable --wait-pid flag.
type pidList []int

func (p *pidList) String() string { return fmt.Sprint(*p) }
func (p *pidList) Set(s string) error {
	n, err := strconv.Atoi(s)
	if err != nil {
		return err
	}
	*p = append(*p, n)
	return nil
}
