package main

import (
	"slices"
	"testing"
)

func TestWaitPIDArgsArePassedToTheUpdater(t *testing.T) {
	got := waitPIDArgs([]string{"--update", "--wait-pid", "1234", "--branch", "overhaul", "--wait-pid=99"})
	want := []string{"--wait-pid", "1234", "--wait-pid=99"}
	if !slices.Equal(got, want) {
		t.Errorf("waitPIDArgs = %v, want %v", got, want)
	}
	if got := waitPIDArgs([]string{"--update", "--wait-pid"}); len(got) != 0 {
		t.Errorf("a trailing --wait-pid without a value gave %v", got)
	}
}
