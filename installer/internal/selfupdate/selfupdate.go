// Package selfupdate replaces Updater.exe and FA11y Launcher.exe with newer
// builds published as GitHub release assets.
//
// Installer releases are tagged "installer-vMAJOR.MINOR.PATCH", separate
// from FA11y's own release tags. Windows lets a running executable be
// renamed but not overwritten, so the old file is renamed to "<name>.old"
// and removed on the next run.
package selfupdate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
)

const TagPrefix = "installer-v"

// Release is the newest installer release.
type Release struct {
	Version string
	Assets  map[string]Asset
}

type Asset struct {
	URL    string
	SHA256 string
}

// Latest returns the newest installer release, or nil when none exists.
// Pre-releases (Beta installer builds) count only when includePre is set,
// which the updater does for installs on a branch other than main.
func Latest(repo string, includePre bool) (*Release, error) {
	data, err := fetch.Bytes(fmt.Sprintf("https://api.github.com/repos/%s/releases?per_page=50", repo))
	if err != nil {
		return nil, err
	}
	var releases []struct {
		Tag        string `json:"tag_name"`
		Draft      bool   `json:"draft"`
		Prerelease bool   `json:"prerelease"`
		Assets     []struct {
			Name   string `json:"name"`
			URL    string `json:"browser_download_url"`
			Digest string `json:"digest"` // "sha256:<hex>"
		} `json:"assets"`
	}
	if err := json.Unmarshal(data, &releases); err != nil {
		return nil, err
	}
	var best *Release
	for _, r := range releases {
		if r.Draft || (r.Prerelease && !includePre) || !strings.HasPrefix(r.Tag, TagPrefix) {
			continue
		}
		v := strings.TrimPrefix(r.Tag, TagPrefix)
		if _, ok := parse(v); !ok {
			continue
		}
		if best != nil && !Newer(v, best.Version) {
			continue
		}
		rel := &Release{Version: v, Assets: map[string]Asset{}}
		for _, a := range r.Assets {
			sha, _ := strings.CutPrefix(a.Digest, "sha256:")
			rel.Assets[a.Name] = Asset{URL: a.URL, SHA256: sha}
		}
		best = rel
	}
	return best, nil
}

// Newer reports whether version a is newer than b. Unparseable versions
// (such as "dev" builds) are never newer and never replaced.
func Newer(a, b string) bool {
	va, okA := parse(a)
	vb, okB := parse(b)
	if !okA || !okB {
		return false
	}
	for i := range va {
		if va[i] != vb[i] {
			return va[i] > vb[i]
		}
	}
	return false
}

func parse(v string) ([3]int, bool) {
	var out [3]int
	parts := strings.Split(v, ".")
	if len(parts) != 3 {
		return out, false
	}
	for i, p := range parts {
		n, err := strconv.Atoi(p)
		if err != nil || n < 0 {
			return out, false
		}
		out[i] = n
	}
	return out, true
}

// Replace downloads asset and swaps it in for the executable at target,
// which may be running.
func Replace(target string, asset Asset) error {
	if asset.SHA256 == "" {
		return fmt.Errorf("release asset for %s has no SHA-256 digest", filepath.Base(target))
	}
	staged := target + ".new"
	if err := fetch.File(asset.URL, staged, fetch.Expect{SHA256: asset.SHA256}); err != nil {
		return err
	}
	old := target + ".old"
	os.Remove(old)
	if _, err := os.Stat(target); err == nil {
		if err := os.Rename(target, old); err != nil {
			os.Remove(staged)
			return err
		}
	}
	if err := os.Rename(staged, target); err != nil {
		os.Rename(old, target)
		return err
	}
	return nil
}

// CleanupOld removes "<name>.old" files left by earlier replacements.
func CleanupOld(paths ...string) {
	for _, p := range paths {
		os.Remove(p + ".old")
	}
}
