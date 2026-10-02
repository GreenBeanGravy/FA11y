// Package filesync installs FA11y's repository files into the FA11y Files
// folder, downloading only files whose content changed.
//
// Every request is pinned to one commit, so a push during an update cannot
// mix files from two versions, and raw.githubusercontent.com caching cannot
// serve stale content. Each download is checked against the git blob SHA
// from the tree listing.
package filesync

import (
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
	"github.com/GreenBeanGravy/FA11y/installer/internal/state"
)

const workers = 8

// Entry is one file in the repository tree.
type Entry struct {
	Path string `json:"path"`
	Type string `json:"type"`
	SHA  string `json:"sha"`
	Size int64  `json:"size"`
}

// Source is where repository files come from.
type Source interface {
	Tree() ([]Entry, error)
	Read(path string) ([]byte, error)
	Fetch(path, dest string) error
}

// GitHub serves files from one commit of a GitHub repository.
type GitHub struct{ Repo, Commit string }

func (g GitHub) Tree() ([]Entry, error)           { return Tree(g.Repo, g.Commit) }
func (g GitHub) Read(path string) ([]byte, error) { return fetch.Bytes(RawURL(g.Repo, g.Commit, path)) }
func (g GitHub) Fetch(path, dest string) error {
	return fetch.File(RawURL(g.Repo, g.Commit, path), dest, fetch.Expect{})
}

// Local serves files from a folder, such as an exported checkout, so an
// install can be tested before anything is pushed.
type Local struct{ Dir string }

func (s Local) Tree() ([]Entry, error) {
	var files []Entry
	err := filepath.WalkDir(s.Dir, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if name := d.Name(); name == ".git" || name == "__pycache__" {
				return filepath.SkipDir
			}
			return nil
		}
		rel, err := filepath.Rel(s.Dir, p)
		if err != nil {
			return err
		}
		files = append(files, Entry{Path: filepath.ToSlash(rel), Type: "blob", SHA: BlobSHA(p)})
		return nil
	})
	return files, err
}

func (s Local) Read(path string) ([]byte, error) {
	return os.ReadFile(filepath.Join(s.Dir, filepath.FromSlash(path)))
}

func (s Local) Fetch(path, dest string) error {
	data, err := s.Read(path)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	return os.WriteFile(dest, data, 0o644)
}

// Commit resolves a branch name to its current commit SHA.
func Commit(repo, branch string) (string, error) {
	data, err := fetch.Bytes(fmt.Sprintf("https://api.github.com/repos/%s/commits/%s", repo, url.PathEscape(branch)))
	if err != nil {
		return "", err
	}
	var c struct {
		SHA string `json:"sha"`
	}
	if err := json.Unmarshal(data, &c); err != nil || c.SHA == "" {
		return "", fmt.Errorf("could not read commit for branch %s: %v", branch, err)
	}
	return c.SHA, nil
}

// Tree lists every file in the repository at commit.
func Tree(repo, commit string) ([]Entry, error) {
	data, err := fetch.Bytes(fmt.Sprintf("https://api.github.com/repos/%s/git/trees/%s?recursive=1", repo, commit))
	if err != nil {
		return nil, err
	}
	var t struct {
		Tree      []Entry `json:"tree"`
		Truncated bool    `json:"truncated"`
	}
	if err := json.Unmarshal(data, &t); err != nil {
		return nil, err
	}
	if t.Truncated {
		return nil, fmt.Errorf("repository tree listing was truncated by GitHub")
	}
	files := t.Tree[:0]
	for _, e := range t.Tree {
		if e.Type == "blob" {
			files = append(files, e)
		}
	}
	return files, nil
}

// RawURL is the download URL of a file at a commit.
func RawURL(repo, commit, path string) string {
	parts := strings.Split(path, "/")
	for i, p := range parts {
		parts[i] = url.PathEscape(p)
	}
	return fmt.Sprintf("https://raw.githubusercontent.com/%s/%s/%s", repo, commit, strings.Join(parts, "/"))
}

// BlobSHA returns the git blob SHA-1 of a file on disk, or "" if it is missing.
func BlobSHA(path string) string {
	f, err := os.Open(path)
	if err != nil {
		return ""
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return ""
	}
	h := sha1.New()
	fmt.Fprintf(h, "blob %d\x00", info.Size())
	if _, err := io.Copy(h, f); err != nil {
		return ""
	}
	return hex.EncodeToString(h.Sum(nil))
}

// Result summarizes a sync.
type Result struct {
	Updated []string
	Removed []string
}

func (r Result) Changed() bool { return len(r.Updated) > 0 || len(r.Removed) > 0 }

// Sync makes filesDir match src, following the
// manifest's sync rules, and records installed files in st.
func Sync(filesDir string, src Source, rules manifest.Sync, tree []Entry, st *state.State, say func(string, ...any)) (Result, error) {
	var res Result
	wanted := map[string]bool{}
	var todo []Entry
	for _, e := range tree {
		if rules.Excluded(e.Path) {
			continue
		}
		local := filepath.Join(filesDir, filepath.FromSlash(e.Path))
		if rules.IsAddOnly(e.Path) {
			// Never tracked, so never overwritten or removed.
			if _, err := os.Stat(local); err != nil {
				todo = append(todo, e)
			}
			continue
		}
		wanted[e.Path] = true
		if BlobSHA(local) == e.SHA {
			st.Files[e.Path] = e.SHA
			continue
		}
		todo = append(todo, e)
	}

	if len(todo) > 0 {
		say("Downloading %d changed files...", len(todo))
	}
	var mu sync.Mutex
	var firstErr error
	jobs := make(chan Entry)
	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for e := range jobs {
				err := download(filesDir, src, e)
				mu.Lock()
				if err != nil && firstErr == nil {
					firstErr = err
				}
				if err == nil {
					res.Updated = append(res.Updated, e.Path)
					if !rules.IsAddOnly(e.Path) {
						st.Files[e.Path] = e.SHA
					}
				}
				mu.Unlock()
			}
		}()
	}
	for _, e := range todo {
		jobs <- e
	}
	close(jobs)
	wg.Wait()
	if firstErr != nil {
		return res, firstErr
	}

	// Remove files a previous run installed that the repository no longer
	// has. Files the updater never installed (user config, logs) are never
	// touched.
	var stale []string
	for path := range st.Files {
		if !wanted[path] {
			stale = append(stale, path)
		}
	}
	sort.Strings(stale)
	for _, path := range stale {
		local := filepath.Join(filesDir, filepath.FromSlash(path))
		if err := os.Remove(local); err != nil && !os.IsNotExist(err) {
			say("Could not remove %s: %v", path, err)
			continue
		}
		delete(st.Files, path)
		res.Removed = append(res.Removed, path)
		removeEmptyParents(filesDir, filepath.Dir(local))
	}
	sort.Strings(res.Updated)
	return res, nil
}

func download(filesDir string, src Source, e Entry) error {
	local := filepath.Join(filesDir, filepath.FromSlash(e.Path))
	tmp := local + ".download"
	if err := src.Fetch(e.Path, tmp); err != nil {
		return err
	}
	if got := BlobSHA(tmp); got != e.SHA {
		os.Remove(tmp)
		return fmt.Errorf("%s: downloaded content does not match the repository (got %s, want %s)", e.Path, got, e.SHA)
	}
	os.Remove(local)
	return os.Rename(tmp, local)
}

func removeEmptyParents(root, dir string) {
	root = filepath.Clean(root)
	for dir = filepath.Clean(dir); dir != root && strings.HasPrefix(dir, root); dir = filepath.Dir(dir) {
		if os.Remove(dir) != nil {
			return
		}
	}
}
