# SPDX-License-Identifier: GPL-2.0-or-later
import asyncio, logging, os, secrets, string, sys, webbrowser

from server.backend import Backend
from server.session import Session
from server.transport import Transport

from terminal import *

class InstallerGUI:
    ALPHABET = string.ascii_letters + string.digits
    MAX_AUTH_ATTEMPTS = 5

    def __init__(self, version):
        self.version = version
        attach_log_handler()

    async def run(self, backend, token):
        session = Session(backend, token, asyncio.get_running_loop(), self.MAX_AUTH_ATTEMPTS)
        transport = Transport(session.handle_connection, "ui")
        try:
            await transport.start()
        except OSError as e:
            p_error(f"Cannot start the installer server: {e}")
            session.close()
            return None
        url = f"http://localhost:{transport.port}/#{token}"
        p_progress(f"Installer interface: {url}")
        p_message("Please do not close this terminal window while using the installer.")
        webbrowser.open(url)
        await session.done.wait()
        await transport.stop()
        session.close()
        return session.exit_action

    def main(self):
        logging.info("Startup (server)")

        backend = Backend(self.version, expert=bool(os.environ.get("EXPERT")), verbose="-v" in sys.argv)
        p_progress("Collecting system information...")
        backend.collect()
        p_progress("Starting the installer...")

        token = "".join(secrets.choice(self.ALPHABET) for _ in range(128))
        action = asyncio.run(self.run(backend, token))
        if action is None:
            sys.exit(1)
        if action == "shutdown":
            backend.shutdown()
        elif action == "reboot":
            backend.reboot()
