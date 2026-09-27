import signal
import sys

from .cli import main

if hasattr(signal, "SIGPIPE"):  # `python -m engine status | head` must not print a traceback
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
sys.exit(main())
