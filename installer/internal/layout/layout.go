// Package layout describes where an FA11y installation keeps its files.
//
//	<root>\
//	  FA11y Launcher.exe
//	  Updater.exe
//	  FA11y Files\
//	    FA11y.py, lib\, assets\, config\ ...
//	    runtime\python-<version>\   private base Python
//	    .venv\                      virtual environment FA11y runs in
package layout

import (
	"os"
	"path/filepath"
)

const (
	FilesDirName = "FA11y Files"
	LauncherExe  = "FA11y Launcher.exe"
	UpdaterExe   = "Updater.exe"
)

// Exit codes shared by Updater.exe and its callers.
const (
	ExitNoUpdate = 0
	ExitUpdated  = 1
)

type Layout struct {
	Root  string // folder holding the launcher and updater
	Files string // Root\FA11y Files
}

// New returns the layout for an installation rooted at root.
func New(root string) Layout {
	return Layout{Root: root, Files: filepath.Join(root, FilesDirName)}
}

// FromExecutable returns the layout for the installation containing the
// running executable.
func FromExecutable() (Layout, error) {
	exe, err := os.Executable()
	if err != nil {
		return Layout{}, err
	}
	exe, err = filepath.EvalSymlinks(exe)
	if err != nil {
		return Layout{}, err
	}
	return New(filepath.Dir(exe)), nil
}

func (l Layout) Updater() string     { return filepath.Join(l.Root, UpdaterExe) }
func (l Layout) Launcher() string    { return filepath.Join(l.Root, LauncherExe) }
func (l Layout) Entry() string       { return filepath.Join(l.Files, "FA11y.py") }
func (l Layout) ConfigFile() string  { return filepath.Join(l.Files, "config", "config.txt") }
func (l Layout) VenvDir() string     { return filepath.Join(l.Files, ".venv") }
func (l Layout) VenvPython() string  { return filepath.Join(l.VenvDir(), "Scripts", "python.exe") }
func (l Layout) RuntimeRoot() string { return filepath.Join(l.Files, "runtime") }

// RuntimeDir is the folder holding the private base Python of a version.
func (l Layout) RuntimeDir(version string) string {
	return filepath.Join(l.RuntimeRoot(), "python-"+version)
}
