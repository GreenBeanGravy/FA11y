package main

import (
	"errors"
	"net/http"

	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
)

// betaBranch is installed when no branch is chosen and main can't be
// installed by this updater yet.
const betaBranch = "overhaul"

// resolveBranch picks the branch to use: an explicit --branch first, then
// the branch recorded by the last install, then main.
func resolveBranch(flagValue, remembered string) string {
	if flagValue != "" {
		return flagValue
	}
	if remembered != "" {
		return remembered
	}
	return defaultBranch
}

// branchSwitch reports whether an installed FA11y is on a different branch
// than the one about to be used. An install that never recorded a branch
// is on main.
func branchSwitch(installed bool, remembered, branch string) bool {
	if !installed {
		return false
	}
	if remembered == "" {
		remembered = defaultBranch
	}
	return remembered != branch
}

// branchMissing reports whether err means GitHub has no such branch.
func branchMissing(err error) bool {
	var se *fetch.StatusError
	return errors.As(err, &se) && (se.Code == http.StatusNotFound || se.Code == http.StatusUnprocessableEntity)
}
