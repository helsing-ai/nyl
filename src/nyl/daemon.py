"""
Pass Nyl commands to an automatically managed Nyl daemon process to improve performance.
"""

# Important: This file tries to import as little as possible to keep startup time low.

import argparse
from dataclasses import dataclass
import errno
import fcntl
from io import TextIOWrapper
import os
from pathlib import Path
import pickle
import select
import socket as sock
import sys
import threading
import time
from typing import Any, Literal, Protocol
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

parser = argparse.ArgumentParser(prog="nyl-daemon", description=__doc__)
parser.add_argument("--socket", type=Path, help="The socket to connect to.", required=True)
parser.add_argument("--foreground", action="store_true", help="Run the daemon in the foreground.")
parser.add_argument("args", nargs=argparse.REMAINDER, help="The arguments to execute in the Nyl daemon.")


class HasFileno(Protocol):
    def fileno(self) -> int:
        """Return the file descriptor for the socket."""
        ...


def set_nonblocking(fd: HasFileno | int) -> None:
    if hasattr(fd, "fileno"):
        fd = fd.fileno()

    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


class PickleSocketTransport:
    """
    A socket transport that uses pickle to serialize and deserialize data.
    """

    def __init__(
        self,
        socket: Path | sock.socket,
        mode: Literal["client", "server"],
        connect_retries: int = 5,
        connect_retry_sleep: float = 0.2,
        timeout: float = 1,
    ) -> None:
        self.mode = mode

        if isinstance(socket, sock.socket):
            self.socket = socket
        else:
            self.socket = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)

            if mode == "client":
                for _ in range(connect_retries):
                    try:
                        self.socket.connect(str(socket))
                        break
                    except sock.error as e:
                        if _ == connect_retries - 1:
                            raise e
                        self.socket.close()
                        self.socket = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
                        time.sleep(connect_retry_sleep)

                self.socket.settimeout(None)
            else:
                socket.unlink(missing_ok=True)
                self.socket.bind(str(socket))
                self.socket.listen(1)

        self.socket.settimeout(timeout)

    def __enter__(self) -> "PickleSocketTransport":
        return self

    def __exit__(self, exc_type: type, exc_value: Exception, traceback: Any) -> None:
        self.close()

    def accept(self) -> "PickleSocketTransport | None":
        """Accept a connection from a client. Only in server mode."""
        try:
            socket, _ = self.socket.accept()
        except sock.timeout:
            return None
        return PickleSocketTransport(socket, "client")

    def recv(self) -> Any | None:
        """Receive a single message from the socket."""
        try:
            content_length = int.from_bytes(self.socket.recv(4), "big")
        except sock.timeout:
            return None
        data = b""
        while len(data) < content_length:
            chunk = self.socket.recv(content_length - len(data))
            if not chunk:
                break
            data += chunk
        return pickle.loads(data)

    def send(self, data: Any) -> None:
        """Send a single message via the socket."""
        data = pickle.dumps(data)
        content_length = len(data).to_bytes(4, "big")
        self.socket.sendall(content_length)
        self.socket.sendall(data)

    def close(self) -> None:
        try:
            socket_name = self.socket.getsockname()
        except OSError as exc:
            if exc.errno == errno.EBADF:
                socket_name = None
            else:
                raise

        self.socket.close()
        if self.mode == "server" and socket_name:
            Path(socket_name).unlink(missing_ok=True)


class NylDaemon:
    @dataclass
    class Run:
        cwd: str
        args: list[str]
        env: dict[str, str]

        def __repr__(self) -> str:
            return f"Run(cwd={self.cwd}, args={self.args}, env.keys()={self.env.keys()})"

    @dataclass
    class Stdout:
        text: str

    @dataclass
    class Stderr:
        text: str

    @dataclass
    class RunResult:
        error: str
        code: int

    @dataclass
    class Error:
        message: str

    def __init__(self, transport: PickleSocketTransport) -> None:
        self.transport = transport
        self.is_shutdown = False

    def shutdown(self) -> None:
        self.is_shutdown = True

    def server_forever(self) -> None:
        while not self.is_shutdown:
            client = self.transport.accept()
            if not client:
                continue
            threading.Thread(target=lambda: self._handle_request(client)).start()

    def _handle_request(self, client: PickleSocketTransport) -> None:
        with client:
            message = client.recv()
            match message:
                case None:
                    pass
                case self.Run():
                    self._do_run(client, message)
                case _:
                    logger.warning("Received unknown message type: %s", message)
                    client.send(self.Error("Unknown message type"))

    def _do_run(self, client: PickleSocketTransport, message: Run) -> None:
        logger.info("Running command: %s", message)

        # Import the app here so that the fork can benefit from it being preloaded.
        from nyl.commands import app

        r_out, w_out = os.pipe()
        r_err, w_err = os.pipe()
        r_error, w_error = os.pipe()  # To send an actual error message

        pid = os.fork()
        if pid == 0:
            os.close(r_out)
            os.close(r_err)
            os.close(r_error)

            w1 = os.fdopen(w_out, "w")
            w2 = os.fdopen(w_err, "w")
            w3 = os.fdopen(w_error, "w")
            sys.stdout = w1
            sys.stderr = w2

            try:
                os.environ.update(message.env)  # TODO: Maybe replace instead?
                os.chdir(message.cwd)
                app(message.args)
                w3.write("0\n")
            except BaseException as e:
                if isinstance(e, SystemExit):
                    logger.info("Command exited with code %s", e.code)
                    code = e.code if isinstance(e.code, int) else 1
                else:
                    logger.exception("Error running command, using exit code = 1")
                    code = 1
                w3.write(str(code) + "\n")
                if not isinstance(e, SystemExit):
                    w3.write(f"{type(e).__name__}: {e}")
            finally:
                w1.flush()
                w2.flush()
                w3.flush()
                w1.close()
                w2.close()
                w3.close()

                # TODO: We could maybe propagate the real exit code, but couldn't figure out how to retrieve it from
                # the parent process, yet. We send it via the pipe anyway.
                os._exit(0)
        else:
            logger.info("Forked child process %d", pid)

            os.close(w_out)
            os.close(w_err)
            os.close(w_error)
            rout = os.fdopen(r_out)
            rerr = os.fdopen(r_err)
            rerror = os.fdopen(r_error)

            set_nonblocking(rout)
            set_nonblocking(rerr)
            set_nonblocking(rerror)

            exit_code: int | None = None
            error_message = ""

            def read_output() -> None:
                nonlocal exit_code, error_message
                read_list = [rout, rerr, rerror]
                while read_list:
                    try:
                        read_ready, _, _ = select.select(read_list, [], [], 1)
                        if not read_ready:
                            time.sleep(0.01)
                            continue
                        fp: TextIOWrapper
                        for fp in read_ready:
                            output: str = fp.read()
                            if not output:
                                read_list.remove(fp)
                                continue
                            if fp == rerror:
                                if exit_code is None:
                                    lines = output.splitlines()
                                    exit_code = int(lines.pop(0).strip())
                                    output = "\n".join(lines)
                                error_message += output
                                continue
                            if fp == rerr:
                                print(output, end="", file=sys.stderr)
                            client.send(NylDaemon.Stdout(output) if fp == rout else NylDaemon.Stderr(output))
                    except BlockingIOError:
                        time.sleep(0.01)
                rout.close()
                rerr.close()

            read_output_thread = threading.Thread(target=read_output)
            read_output_thread.start()
            read_output_thread.join()

            _, wait_status = os.waitpid(pid, 0)
            if exit_code is None:
                exit_code = os.WEXITSTATUS(wait_status)
            logger.info("Child process %d exited (status code %s)", pid, exit_code)

            client.send(self.RunResult(error_message, exit_code))
            client.close()


def main() -> None:
    args = parser.parse_args()
    if args.foreground:
        with PickleSocketTransport(args.socket, "server") as transport:
            daemon = NylDaemon(transport)
            daemon.server_forever()

    else:
        client = PickleSocketTransport(args.socket, "client")
        client.send(NylDaemon.Run(os.getcwd(), args.args, dict(os.environ)))

        while True:
            message = client.recv()
            if message is None:
                continue
            if isinstance(message, NylDaemon.Stdout):
                sys.stdout.write(message.text)
                sys.stdout.flush()
            elif isinstance(message, NylDaemon.Stderr):
                # If enabled, this means stderr output will show in the error message in the ArgoCD UI
                # when the command fails.
                if os.getenv("NYL_DAEMON_LOG_STDERR") == "1":
                    sys.stderr.write(message.text)
                    sys.stderr.flush()
            elif isinstance(message, NylDaemon.RunResult):
                if message.error:
                    print(message.error + f" (status code {message.code})", file=sys.stderr)
                elif message.code != 0:
                    print(f"Command failed without error message (status code {message.code})", file=sys.stderr)
                sys.exit(message.code)
            else:
                logger.error("Unknown message type:", message)
                sys.exit(1)


if __name__ == "__main__":
    main()
