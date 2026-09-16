#!/usr/bin/env python3
import json
import os
import selectors
import subprocess
import sys
import time


ENTRYPOINT = os.environ.get(
    "KIMMIZO_ENTRYPOINT",
    os.path.expanduser("~/.kimmizo-secretary/auto/kimmizo-desktop-entrypoint"),
)


def send(process, message):
    process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    process.stdin.flush()


def read_message(selector, deadline):
    while time.monotonic() < deadline:
        events = selector.select(max(0.0, deadline - time.monotonic()))
        if not events:
            break
        line = events[0][0].fileobj.readline()
        if not line:
            raise RuntimeError("app-server closed stdout")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise TimeoutError("timed out waiting for app-server")


def response_for(process, selector, request_id, timeout):
    deadline = time.monotonic() + timeout
    while True:
        message = read_message(selector, deadline)
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(f"request {request_id} failed: {message['error']}")
            return message


def main():
    if not os.path.isfile(ENTRYPOINT) or not os.access(ENTRYPOINT, os.X_OK):
        raise RuntimeError("installed Kimmizo entrypoint is unavailable")
    process = subprocess.Popen(
        [ENTRYPOINT, "app-server", "--analytics-default-enabled"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        send(
            process,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "kimmizo-e2e", "version": "1.1.0"},
                    "capabilities": {},
                },
            },
        )
        response_for(process, selector, 1, 30)

        send(process, {"id": 2, "method": "model/list", "params": {}})
        models_response = response_for(process, selector, 2, 30)
        models = models_response.get("result", {}).get("data", [])
        if not any(model.get("model") == "athena-auto" for model in models):
            raise RuntimeError("Auto preset is absent from model/list")

        send(
            process,
            {
                "id": 3,
                "method": "thread/start",
                "params": {
                    "model": "athena-auto",
                    "ephemeral": True,
                    "cwd": os.getcwd(),
                },
            },
        )
        try:
            thread_response = response_for(process, selector, 3, 60)
        except RuntimeError as error:
            summary = [
                {
                    "model": model.get("model", model.get("id", "")),
                    "efforts": model.get("supportedReasoningEfforts", []),
                }
                for model in models
                if model.get("model", model.get("id", "")) != "athena-auto"
            ]
            raise RuntimeError(
                f"{error}; safe catalog summary={json.dumps(summary, ensure_ascii=False)}"
            ) from error
        thread_id = (
            thread_response.get("result", {}).get("thread", {}).get("id", "")
        )
        if not thread_id:
            raise RuntimeError("ephemeral Auto thread did not start")

        send(
            process,
            {
                "id": 4,
                "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "model": "athena-auto",
                    "input": [{"type": "text", "text": "ตอบคำว่า OK เท่านั้น"}],
                },
            },
        )
        response_for(process, selector, 4, 60)
        deadline = time.monotonic() + 180
        while True:
            message = read_message(selector, deadline)
            method = message.get("method")
            if method == "error":
                raise RuntimeError("real Auto turn emitted an error notification")
            if method == "turn/completed":
                break

        print("PASS: real app-server completed an ephemeral turn through Auto.")
        return 0
    finally:
        selector.close()
        if process.stdin:
            process.stdin.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
