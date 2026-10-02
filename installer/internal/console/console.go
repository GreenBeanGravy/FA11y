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

var setConsoleTitle = syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleTitleW")

// SetTitle sets the console window title.
func SetTitle(title string) {
	p, err := syscall.UTF16PtrFromString(title)
	if err == nil {
		setConsoleTitle.Call(uintptr(unsafe.Pointer(p)))
	}
}

// Say prints one line of status.
func Say(format string, args ...any) {
	fmt.Printf(format+"\n", args...)
}

// Fail prints an error, waits for Enter so the message can be read, and
// exits with code.
func Fail(code int, format string, args ...any) {
	fmt.Printf("Error: "+format+"\n", args...)
	fmt.Println("Press Enter to close.")
	bufio.NewReader(os.Stdin).ReadString('\n')
	os.Exit(code)
}
