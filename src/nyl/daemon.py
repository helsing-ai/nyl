"""
Pass Nyl commands to an automatically managed Nyl daemon process to improve performance.
"""

# Important: This file tries to import as little as possible to keep startup time low.

import argparse
from dataclasses import dataclass, field
import errno
import os
from pathlib import Path
import pickle
import select
import socket as sock
import sys
import threading
import time
from typing import Any, Literal
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

parser = argparse.ArgumentParser(prog="nyl-daemon", description=__doc__)
parser.add_argument("--socket", type=Path, help="The socket to connect to.", required=True)
parser.add_argument("--foreground", action="store_true", help="Run the daemon in the foreground.")
parser.add_argument("args", nargs=argparse.REMAINDER, help="The arguments to execute in the Nyl daemon.")


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
        env: dict[str, str] = field(repr=False)

    @dataclass
    class Stdout:
        text: str

    @dataclass
    class Stderr:
        text: str

    @dataclass
    class RunResult:
        result: Any

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

        pid = os.fork()
        if pid == 0:
            os.close(r_out)
            os.close(r_err)

            w1 = os.fdopen(w_out, "w")
            w2 = os.fdopen(w_err, "w")
            sys.stdout = w1
            sys.stderr = w2

            try:
                os.environ.update(message.env)  # TODO: Maybe replace instead?
                os.chdir(message.cwd)
                app(message.args)
            except SystemExit:
                # This flush may seem unnecessary, but it is required before we call os._exit().
                w1.flush()
                w2.flush()
                # os._exit(e.code if isinstance(e.code, int) else 1 if isinstance(e.code, str) else 0)
                raise  # Actually we do want a regular exit maybe, to ensure atexit is invoked
            finally:
                w1.flush()
                w2.flush()
                w1.close()
                w2.close()
        else:
            logger.info("Forked child process %d", pid)

            os.close(w_out)
            os.close(w_err)
            rout = os.fdopen(r_out)
            rerr = os.fdopen(r_err)

            def read_output() -> None:
                # TODO: Need to set nonblocking mode on the pipes?
                read_list = [rout, rerr]
                while read_list:
                    try:
                        read_ready, _, _ = select.select(read_list, [], [], 0.1)
                        if not read_ready:
                            time.sleep(0.01)
                            continue
                        for fp in read_ready:
                            output = fp.read()
                            if not output:
                                read_list.remove(fp)
                                continue
                            client.send(NylDaemon.Stdout(output) if fp == rout else NylDaemon.Stderr(output))
                    except BlockingIOError:
                        time.sleep(0.01)
                rout.close()
                rerr.close()

            read_output_thread = threading.Thread(target=read_output)
            read_output_thread.start()
            read_output_thread.join()

            # TODO: Determine the exit code of the child process.
            os.waitpid(pid, 0)
            logger.info("Child process %d exited", pid)

        result = {"status": "success", "output": "Command executed successfully."}
        client.send(self.RunResult(result))
        client.close()


# def run_daemon(queue: Queue[RunCommand]) -> None:
#     from nyl.commands import app

#     # This is a workaround for the fact that we can't pass the socket to the app directly.
#     # We need to pass it as an environment variable.
#     import os

#     os.environ["NYL_DAEMON_SOCKET"] = args.socket
#     app()


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
                sys.stderr.write(message.text)
                sys.stderr.flush()
            elif isinstance(message, NylDaemon.RunResult):
                print(message.result)
                break
            else:
                print("Unknown message type:", message)
                break


if __name__ == "__main__":
    main()
