"""Who is acting. Taken from git config so every change is attributable.

user code: short unique handle per person (git config alpilla.usercode, or
ALPILLA_USER_CODE). It names the person's changelog file and prefixes auto IDs,
so two users working in parallel never collide.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass


def _git(root, *args) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


@dataclass(frozen=True)
class Identity:
    name: str
    email: str
    code: str
    agent: str | None  # e.g. "claude-code" when an AI session performs the action
    code_is_derived: bool = False

    def stamp(self) -> dict:
        d = {"user": self.code, "name": self.name, "email": self.email}
        if self.agent:
            d["agent"] = self.agent
        return d


def derive_code(name: str, email: str) -> str:
    words = re.findall(r"[A-Za-z]+", name or "")
    code = "".join(w[0] for w in words)[:3].upper()
    if len(code) < 2:
        code = re.sub(r"[^A-Za-z]", "", (email or "user").split("@")[0])[:3].upper()
    return code or "USR"


def current(root) -> Identity:
    name = os.environ.get("ALPILLA_USER_NAME") or _git(root, "config", "user.name") or "unknown"
    email = os.environ.get("ALPILLA_USER_EMAIL") or _git(root, "config", "user.email") or "unknown"
    code = os.environ.get("ALPILLA_USER_CODE") or _git(root, "config", "alpilla.usercode")
    derived = not code
    if derived:
        code = derive_code(name, email)
    code = code.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", code):
        raise SystemExit(f"Invalid user code '{code}': 2-8 chars, letters/digits, starting with a letter. "
                         "Set it with: git config alpilla.usercode ABC")
    agent = "claude-code" if os.environ.get("CLAUDECODE") else os.environ.get("ALPILLA_AGENT")
    return Identity(name, email, code, agent, derived)
