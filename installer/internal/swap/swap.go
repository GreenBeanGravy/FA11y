// Package swap replaces files that may be in use.
//
// Windows refuses to delete or overwrite a file that is open without
// FILE_SHARE_DELETE (a running .exe, a loaded .dll or .pyd), but it does let
// it be renamed. So a file that is in the way is set aside as "<name>.old"
// and the new one moved into its place. When "<name>.old" itself is still
// in use (the program set aside last time is still running), the next free
// "<name>.<n>.old" is used instead, so a stale set-aside file can never
// block an update. Cleanup removes every set-aside copy that is no longer
// in use; ones that still are stay until a later run.
package swap

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// maxAside bounds the "<name>.<n>.old" names tried before giving up.
const maxAside = 50

// Into moves staged to target, replacing target even when it is in use.
// It returns the path target was set aside to ("" when target didn't exist
// or could simply be deleted), so the caller can remove it later.
func Into(staged, target string) (aside string, err error) {
	if err := os.Remove(target); err == nil || errors.Is(err, fs.ErrNotExist) {
		return "", os.Rename(staged, target)
	}
	aside, err = SetAside(target)
	if err != nil {
		return "", err
	}
	if err := os.Rename(staged, target); err != nil {
		if os.Rename(aside, target) != nil {
			return aside, fmt.Errorf("%w (and %s could not be put back from %s)", err, filepath.Base(target), filepath.Base(aside))
		}
		return "", err
	}
	return aside, nil
}

// SetAside renames path to the first free "<path>.old" or
// "<path>.<n>.old", removing a stale one first when it isn't in use.
func SetAside(path string) (string, error) {
	var lastErr error
	for n := 0; n < maxAside; n++ {
		candidate := asideName(path, n)
		if err := os.Remove(candidate); err != nil && !errors.Is(err, fs.ErrNotExist) {
			continue // a copy set aside earlier is still in use; try the next name
		}
		if err := os.Rename(path, candidate); err != nil {
			lastErr = err
			continue
		}
		return candidate, nil
	}
	if lastErr == nil {
		lastErr = errors.New("every set-aside name is in use")
	}
	return "", fmt.Errorf("could not set %s aside: %w", filepath.Base(path), lastErr)
}

func asideName(path string, n int) string {
	if n == 0 {
		return path + ".old"
	}
	return fmt.Sprintf("%s.%d.old", path, n)
}

// Cleanup removes the set-aside copies of each path ("<path>.old",
// "<path>.<n>.old") and a download left staged as "<path>.new", skipping
// any still in use. It returns the copies that could not be removed yet.
func Cleanup(paths ...string) (left []string) {
	for _, p := range paths {
		os.Remove(p + ".new")
		matches, _ := filepath.Glob(globEscape(p) + ".*old")
		for _, m := range matches {
			if !isAsideOf(p, m) {
				continue
			}
			if err := os.Remove(m); err != nil && !errors.Is(err, fs.ErrNotExist) {
				left = append(left, m)
			}
		}
	}
	return left
}

// isAsideOf reports whether name is one of asideName(path, n).
func isAsideOf(path, name string) bool {
	rest, ok := strings.CutPrefix(name, path)
	if !ok {
		return false
	}
	if rest == ".old" {
		return true
	}
	digits, ok := strings.CutSuffix(strings.TrimPrefix(rest, "."), ".old")
	if !ok || digits == "" || !strings.HasPrefix(rest, ".") {
		return false
	}
	for _, r := range digits {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

// globEscape quotes the characters filepath.Glob treats specially.
func globEscape(p string) string {
	r := strings.NewReplacer("[", "[[]", "*", "[*]", "?", "[?]")
	return r.Replace(p)
}
