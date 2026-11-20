# SPDX-License-Identifier: GPL-2.0-or-later
import logging, sys

from core.util import SUCCESS, ssize, user_log

BLACK     = 30
RED       = 31
GREEN     = 32
YELLOW    = 33
BLUE      = 34
MAGENTA   = 35
CYAN      = 36
WHITE     = 37

BRIGHT    = 1
DIM       = 2
BLINK     = 5
NBLINK    = 25
NORMAL    = 22
RESET_ALL = 0

def col(*color):
    color = ";".join(map(str, color))
    return f"\033[{color}m"

SPINNER = "/-\\|"
progress_open = False
spin = 0

def end_progress():
    global progress_open
    if progress_open:
        sys.stdout.write("\n")
        progress_open = False

def p_style(*args, color=[], **kwargs):
    end_progress()
    if isinstance(color, int):
        color = [color]
    text = " ".join(map(str, args))
    print(col(*color) + text + col(), **kwargs)
    if "\033" in text:
        text += col()
    logging.info(f"MSG: {text}")

def p_plain(*args):
    p_style(*args)

def p_info(*args):
    p_style(*args, color=(BRIGHT, BLUE))

def p_progress(*args):
    p_style(*args, color=(BRIGHT, MAGENTA))

def p_message(*args):
    p_style(*args, color=BRIGHT)

def p_error(*args):
    p_style(*args, color=(BRIGHT, RED))

def p_warning(*args):
    p_style(*args, color=(BRIGHT, YELLOW))

def p_question(*args):
    p_style(*args, color=(BRIGHT, CYAN))

def p_success(*args):
    p_style(*args, color=(BRIGHT, GREEN))

def p_prompt(*args):
    p_style(*args, color=(BRIGHT, CYAN))

def p_choice(*args):
    p_style(*args)

def input_prompt(*args):
    while True:
        p_style(f"{col(BRIGHT, WHITE)}»{col(BRIGHT, CYAN)}", *args, end="")
        val = input()
        if any (ord(c) < 0x20 for c in val):
            p_error("Invalid input")
            continue
        break
    logging.info(f"INPUT: {val!r}")
    return val

def describe_os(os):
    kind = os.kind
    if kind.startswith("recovery"):
        return str(os)

    lbl = col(BRIGHT) + os.label + col()
    ids = f"[{os.sys_volume}, {os.vgid}]"
    stub = f" (macOS {os.version} stub)"
    if kind == "macos_m1n1":
        return f"[{lbl}] {col(BRIGHT, GREEN)}macOS v{os.version}{col()} + {col(CYAN)}m1n1 {os.m1n1_ver}{col()} {ids}"
    elif kind == "macos_fuos":
        return f"[{lbl}] {col(BRIGHT, GREEN)}macOS v{os.version}{col()} + {col(YELLOW)}unknown fuOS{col()} {ids}"
    elif kind == "macos":
        return f"[{lbl}] {col(BRIGHT, GREEN)}macOS v{os.version}{col()} {ids}"
    elif kind == "stub_m1n1":
        return f"[{lbl}] {col(BRIGHT, CYAN)}m1n1 {os.m1n1_ver}{col()}{stub} {ids}"
    elif kind == "stub_fuos":
        return f"[{lbl}] {col(BRIGHT, YELLOW)}unknown fuOS{col()}{stub} {ids}"
    else:
        return f"[{lbl}] {col(BRIGHT, RED)}incomplete install{col()}{stub} {ids}"

def terminal_progress(fraction, rate=None):
    global progress_open, spin
    if fraction is None:
        spin = (spin + 1) % len(SPINNER)
        sys.stdout.write(f"\r{SPINNER[spin]} ")
    else:
        sys.stdout.write(f"\033[3G{fraction * 100:6.2f}%")
        sys.stdout.write(" " if rate is None else f" ({ssize(rate)}/s)")
    sys.stdout.flush()
    progress_open = True
    if fraction is not None and rate is None:
        end_progress()

class TerminalLogHandler(logging.Handler):
    def emit(self, record):
        text = record.getMessage()
        end_progress()
        if record.levelno >= logging.ERROR:
            print(col(BRIGHT, RED) + text + col())
        elif record.levelno >= logging.WARNING:
            print(col(BRIGHT, YELLOW) + text + col())
        elif record.levelno == SUCCESS:
            print()
            print(col(BRIGHT, GREEN) + text + col())
            print()
        elif text.startswith(" "):
            print(text)
        else:
            print(col(BRIGHT, MAGENTA) + text + col())

def attach_log_handler():
    if not any(isinstance(h, TerminalLogHandler) for h in user_log.handlers):
        user_log.addHandler(TerminalLogHandler())
        user_log.setLevel(logging.INFO)
