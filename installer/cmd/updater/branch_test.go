package main

import "testing"

func TestResolveBranchPrecedence(t *testing.T) {
	cases := []struct{ flag, remembered, want string }{
		{"", "", "main"},
		{"", "overhaul", "overhaul"},
		{"main", "overhaul", "main"},
		{"beta", "", "beta"},
	}
	for _, c := range cases {
		if got := resolveBranch(c.flag, c.remembered); got != c.want {
			t.Errorf("resolveBranch(%q, %q) = %q, want %q", c.flag, c.remembered, got, c.want)
		}
	}
}

func TestBranchSwitch(t *testing.T) {
	if branchSwitch(false, "", "overhaul") {
		t.Error("a fresh install is not a switch")
	}
	if branchSwitch(true, "", "main") {
		t.Error("an install with no saved branch is on main")
	}
	if !branchSwitch(true, "", "overhaul") || !branchSwitch(true, "overhaul", "main") {
		t.Error("changing branch should be a switch")
	}
}
