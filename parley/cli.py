"""Parley CLI - thin dispatch layer over parley.core and parley.workflows.

Usage:
    parley list
    parley read <tab_id>
    parley send <tab_id> <text...>
    parley send-wait <tab_id> <text...> [--timeout N]
    parley type <tab_id> <text...>
    parley click <tab_id> <selector>
    parley navigate <tab_id> <url>
    parley eval <tab_id> <js...>
    parley wait-stream <tab_id> [timeout_ms=60000] [silence_ms=1500]
    parley poll <tab_id> [interval_ms=2000]
    parley bridge <tab_from> <tab_to> [rounds=3]

Generic browser-automation commands:
    parley read-dom <tab_id> [selector]        Read innerText of page or selector
    parley extract <tab_id> <selector> [attr]  Extract text/attribute from all matches
    parley wait-for <tab_id> <selector> [timeout_ms=10000]
    parley cookies <tab_id> [domain]           List cookies (incl. HttpOnly) via CDP
    parley set-cookie <tab_id> <name> <value> <domain> [path=/]

Environment:
    PARLEY_CDP_HOST   CDP host (default: localhost)
    PARLEY_CDP_PORT   CDP port (default: 9222)
"""

import sys
import json

from . import core
from . import workflows
from .adapters.js import make_focus_and_type_js


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_type(tab_id, text):
    val = core.evaluate(tab_id, make_focus_and_type_js(text))
    _print(val)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print(__doc__)
        return

    cmd = argv[1]

    if cmd == "list":
        _print(core.list_tabs())

    elif cmd == "read":
        _print(workflows.read_response(argv[2]))

    elif cmd == "send":
        _print(workflows.send(argv[2], " ".join(argv[3:])))

    elif cmd == "send-wait":
        parts = argv[3:]
        timeout_ms = 60000
        text_parts = []
        i = 0
        while i < len(parts):
            p = parts[i]
            if p == "--timeout":
                timeout_ms = int(parts[i + 1])
                i += 2
                continue
            if p.startswith("--timeout="):
                timeout_ms = int(p.split("=", 1)[1])
                i += 1
                continue
            text_parts.append(p)
            i += 1
        _print(workflows.send_and_wait(argv[2], " ".join(text_parts), wait_timeout_ms=timeout_ms))

    elif cmd == "type":
        cmd_type(argv[2], " ".join(argv[3:]))

    elif cmd == "click":
        _print(core.click(argv[2], argv[3]))

    elif cmd == "navigate":
        _print(core.navigate(argv[2], argv[3]))

    elif cmd == "eval":
        _print(core.evaluate(argv[2], " ".join(argv[3:]), await_promise=True))

    elif cmd == "wait-stream":
        timeout_ms = int(argv[3]) if len(argv) > 3 else 60000
        silence_ms = int(argv[4]) if len(argv) > 4 else 1500
        _print(workflows.wait_stream(argv[2], timeout_ms=timeout_ms, silence_ms=silence_ms))

    elif cmd == "poll":
        interval_ms = int(argv[3]) if len(argv) > 3 else 2000
        _print(workflows.poll(argv[2], interval_ms=interval_ms))

    elif cmd == "bridge":
        rounds = int(argv[4]) if len(argv) > 4 else 3
        _print(workflows.bridge(argv[2], argv[3], rounds=rounds))

    elif cmd == "read-dom":
        selector = argv[3] if len(argv) > 3 else None
        _print(core.read_dom(argv[2], selector))

    elif cmd == "extract":
        attr = argv[4] if len(argv) > 4 else None
        _print(core.extract(argv[2], argv[3], attr=attr))

    elif cmd == "wait-for":
        timeout_ms = int(argv[4]) if len(argv) > 4 else 10000
        _print(core.wait_for(argv[2], argv[3], timeout_ms=timeout_ms))

    elif cmd == "cookies":
        domain = argv[3] if len(argv) > 3 else None
        _print(core.get_cookies(argv[2], domain=domain))

    elif cmd == "set-cookie":
        path = argv[6] if len(argv) > 6 else "/"
        _print(core.set_cookie(argv[2], argv[3], argv[4], argv[5], path=path))

    else:
        print("Unknown command: %s" % cmd)
        print(__doc__)


if __name__ == "__main__":
    main()
