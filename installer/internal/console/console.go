// Package console holds the small amount of console handling the launcher
// and updater share. Output is plain text so screen readers read it as it
// appears in the console window.
package console

import (
	"bufio"
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

var (
	kernel32         = syscall.NewLazyDLL("kernel32.dll")
	setConsoleTitle  = kernel32.NewProc("SetConsoleTitleW")
	getConsoleWindow = kernel32.NewProc("GetConsoleWindow")
	allocConsole     = kernel32.NewProc("AllocConsole")
	title            = ""
)

// SetTitle sets the console window title, now or when Ensure opens one.
func SetTitle(text string) {
	title = text
	p, err := syscall.UTF16PtrFromString(text)
	if err == nil {
		setConsoleTitle.Call(uintptr(unsafe.Pointer(p)))
	}
}

// Ensure gives a windowless program (FA11y Launcher.exe is built with
// -H windowsgui) a console window the first time it has something to
// show. Say and Fail call it, so the launcher only opens a window when it
// installs, updates or reports an error. A program that already has a
// console, even a hidden one, keeps it.
func Ensure() {
	if window, _, _ := getConsoleWindow.Call(); window != 0 {
		return
	}
	if ok, _, _ := allocConsole.Call(); ok == 0 {
		return
	}
	if out, err := os.OpenFile("CONOUT$", os.O_RDWR, 0); err == nil {
		os.Stdout, os.Stderr = out, out
	}
	if in, err := os.OpenFile("CONIN$", os.O_RDWR, 0); err == nil {
		os.Stdin = in
	}
	if title != "" {
		SetTitle(title)
	}
}

// Say prints one line of status.
func Say(format string, args ...any) {
	Ensure()
	fmt.Printf(format+"\n", args...)
}

// Fail prints an error, waits for Enter so the message can be read, and
// exits with code.
func Fail(code int, format string, args ...any) {
	Ensure()
	fmt.Printf("Error: "+format+"\n", args...)
	fmt.Println("Press Enter to close.")
	bufio.NewReader(os.Stdin).ReadString('\n')
	os.Exit(code)
}
