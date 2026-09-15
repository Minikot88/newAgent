package proxy

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
)

const MaxJSONRPCLineBytes = 64 << 20

// FilterChildEnvironment prevents CODEX_CLI_PATH from recursively launching
// Athena and keeps the private real-CLI handoff out of the child environment.
func FilterChildEnvironment(environ []string) []string {
	filtered := make([]string, 0, len(environ))
	for _, entry := range environ {
		key := entry
		if index := strings.IndexByte(entry, '='); index >= 0 {
			key = entry[:index]
		}
		switch strings.ToUpper(key) {
		case "CODEX_CLI_PATH", "ATHENA_REAL_CODEX":
			continue
		default:
			filtered = append(filtered, entry)
		}
	}
	return filtered
}

// RunChild executes the real Codex command, forwards termination signals, and
// returns the child's exit code without ever reusing the Athena launcher path.
func RunChild(ctx context.Context, executable string, args []string, stdin io.Reader, stdout, stderr io.Writer, environ []string) int {
	command := exec.CommandContext(ctx, executable, args...)
	command.Stdin = stdin
	command.Stdout = stdout
	command.Stderr = stderr
	command.Env = FilterChildEnvironment(environ)
	if err := command.Start(); err != nil {
		return 127
	}

	signals := make(chan os.Signal, 2)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	done := make(chan struct{})
	go func() {
		defer close(done)
		for received := range signals {
			if command.Process != nil {
				_ = command.Process.Signal(received)
			}
		}
	}()

	err := command.Wait()
	signal.Stop(signals)
	close(signals)
	<-done
	if err == nil {
		return 0
	}
	if exitError, ok := err.(*exec.ExitError); ok {
		return exitError.ExitCode()
	}
	return 1
}

// RunAppServer proxies newline-delimited JSON-RPC between Codex Desktop and the
// real Codex app-server. Unknown or malformed messages remain byte-for-byte
// unchanged except for the framing newline.
func RunAppServer(ctx context.Context, executable string, args []string, transformer *Transformer, stdin io.Reader, stdout, stderr io.Writer, environ []string) int {
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = FilterChildEnvironment(environ)
	childStdin, err := command.StdinPipe()
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: create stdin pipe: %v\n", err)
		return 127
	}
	childStdout, err := command.StdoutPipe()
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: create stdout pipe: %v\n", err)
		return 127
	}
	childStderr, err := command.StderrPipe()
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: create stderr pipe: %v\n", err)
		return 127
	}
	if err := command.Start(); err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: start real Codex: %v\n", err)
		return 127
	}

	signals := make(chan os.Signal, 2)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	signalDone := make(chan struct{})
	go func() {
		defer close(signalDone)
		for received := range signals {
			if command.Process != nil {
				_ = command.Process.Signal(received)
			}
		}
	}()

	var outputMu sync.Mutex
	clientDone := make(chan error, 1)
	serverDone := make(chan error, 1)
	stderrDone := make(chan error, 1)
	go func() {
		defer childStdin.Close()
		clientDone <- transformClientStream(stdin, childStdin, stdout, &outputMu, transformer)
	}()
	go func() {
		serverDone <- transformServerStream(childStdout, stdout, &outputMu, transformer)
	}()
	go func() {
		_, copyErr := io.Copy(stderr, childStderr)
		stderrDone <- copyErr
	}()

	waitErr := command.Wait()
	signal.Stop(signals)
	close(signals)
	<-signalDone
	serverErr := <-serverDone
	stderrErr := <-stderrDone
	select {
	case clientErr := <-clientDone:
		if clientErr != nil {
			_, _ = fmt.Fprintf(stderr, "athena-auto: client stream: %v\n", clientErr)
			return 1
		}
	default:
	}
	if serverErr != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: server stream: %v\n", serverErr)
		return 1
	}
	if stderrErr != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: stderr stream: %v\n", stderrErr)
		return 1
	}
	if waitErr == nil {
		return 0
	}
	if exitError, ok := waitErr.(*exec.ExitError); ok {
		return exitError.ExitCode()
	}
	return 1
}

func transformClientStream(source io.Reader, child io.Writer, parent io.Writer, parentMu *sync.Mutex, transformer *Transformer) error {
	return forEachLine(source, func(line []byte) error {
		forward, immediate, err := transformer.ClientLine(line)
		if err != nil {
			return err
		}
		if len(immediate) > 0 {
			if err := writeFramed(parent, parentMu, immediate); err != nil {
				return err
			}
		}
		if len(forward) > 0 {
			return writeFramed(child, nil, forward)
		}
		return nil
	})
}

func transformServerStream(source io.Reader, parent io.Writer, parentMu *sync.Mutex, transformer *Transformer) error {
	return forEachLine(source, func(line []byte) error {
		transformed, err := transformer.ServerLine(line)
		if err != nil {
			return err
		}
		return writeFramed(parent, parentMu, transformed)
	})
}

func forEachLine(source io.Reader, visit func([]byte) error) error {
	reader := bufio.NewReaderSize(source, 64*1024)
	for {
		line, err := readLimitedLine(reader)
		if len(line) > 0 {
			if visitErr := visit(line); visitErr != nil {
				return visitErr
			}
		}
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return err
		}
	}
}

func readLimitedLine(reader *bufio.Reader) ([]byte, error) {
	line := make([]byte, 0, 64*1024)
	for {
		fragment, err := reader.ReadSlice('\n')
		if len(line)+len(fragment) > MaxJSONRPCLineBytes {
			return nil, errLineTooLarge
		}
		line = append(line, fragment...)
		if errors.Is(err, bufio.ErrBufferFull) {
			continue
		}
		line = bytes.TrimSuffix(line, []byte{'\n'})
		line = bytes.TrimSuffix(line, []byte{'\r'})
		return line, err
	}
}

func writeFramed(destination io.Writer, mu *sync.Mutex, line []byte) error {
	if mu != nil {
		mu.Lock()
		defer mu.Unlock()
	}
	if _, err := destination.Write(line); err != nil {
		return err
	}
	_, err := destination.Write([]byte{'\n'})
	return err
}
