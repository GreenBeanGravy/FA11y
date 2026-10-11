package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/GreenBeanGravy/FA11y/installer/internal/filesync"
	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
	"github.com/GreenBeanGravy/FA11y/installer/internal/state"
)

type failingTree struct{ filesync.Local }

func (failingTree) Tree() ([]filesync.Entry, error) { return nil, os.ErrDeadlineExceeded }

func TestFilesChangedFindsAPushWithoutAVersionBump(t *testing.T) {
	src := t.TempDir()
	os.WriteFile(filepath.Join(src, "VERSION"), []byte("19.0.0-beta.1"), 0o644)
	os.WriteFile(filepath.Join(src, "FA11y.py"), []byte("v1"), 0o644)
	m := &manifest.Manifest{}
	tree, _ := filesync.Local{Dir: src}.Tree()
	st := &state.State{Files: map[string]string{}}
	for _, e := range tree {
		st.Files[e.Path] = e.SHA
	}
	if filesChanged(filesync.Local{Dir: src}, m, st) {
		t.Fatal("an install matching the branch reported a change")
	}

	os.WriteFile(filepath.Join(src, "FA11y.py"), []byte("v2, same VERSION"), 0o644)
	if !filesChanged(filesync.Local{Dir: src}, m, st) {
		t.Error("a changed file with the same VERSION was not seen")
	}

	st.Source = "local"
	if filesChanged(filesync.Local{Dir: src}, m, st) {
		t.Error("a test install from a checkout would be overwritten with GitHub's files")
	}
	st.Source = ""
	if filesChanged(failingTree{}, m, st) {
		t.Error("an unreadable tree (offline, rate limited) must not count as an update")
	}
}
