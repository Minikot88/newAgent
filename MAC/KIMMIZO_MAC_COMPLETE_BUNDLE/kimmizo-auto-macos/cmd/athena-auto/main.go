package main

import (
	"os"

	"athena-auto/internal/app"
)

func main() {
	executable, _ := os.Executable()
	os.Exit(app.Run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr, os.Environ(), executable))
}
