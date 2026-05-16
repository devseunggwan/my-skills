"""Shared tokenization helpers for praxis PreToolUse(Bash) hooks.

Three hooks reuse the exact same `safe_tokenize` / `strip_prefix` /
`iter_command_starts` pipeline plus the constants they consume:

- `block-gh-state-all.py` — blocks invalid `gh search ... --state all`
- `side-effect-scan.py` — surfaces collateral side effects via `ask`
- `memory-hint.py` — emits stderr hints for `hookable: true` memories

Per the TODO that lived at `block-gh-state-all.py:25`, this module is the
extraction triggered by the third consumer (issue #139). The helpers move
verbatim — see git history for the prior duplicated copies.
"""
from __future__ import annotations

import re
import shlex


SHELL_SEPARATORS = {";", "&&", "||", "|", "&"}

ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Shell keywords that appear at the start of a command segment but are purely
# syntactic. `if true; then git push; fi` segments as `['if','true']`,
# `['then','git','push']`, `['fi']` — we peel the keyword so argv[0] becomes
# the real executable.
SHELL_KEYWORDS = {
    "if", "then", "elif", "else", "fi",
    "while", "until", "do", "done",
    "case", "esac", "in", "for",
    "{", "}", "!", "function",
}

# Prefix wrappers that execute the following command as a new process. The
# scanner looks past them to find the real argv[0]. Per-wrapper option
# dictionaries list *only* flags that take a separate-token argument so that
# `sudo --user admin kubectl ...` peels both `--user` and `admin`. Bare flags
# (with no arg) and `--long=value` forms are handled generically below.
PREFIX_WRAPPERS = {"env", "sudo", "nice", "time", "stdbuf", "ionice"}
WRAPPER_OPTS_WITH_ARG = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {
        "-u", "-g", "-p", "-C", "-D", "-r", "-t", "-T", "-U", "-h",
        "--user", "--group", "--prompt", "--close-from", "--chdir",
        "--role", "--type", "--host", "--other-user",
    },
    "nice": {"-n", "--adjustment"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "time": {"-f", "--format", "-o", "--output"},
    "ionice": {
        "-c", "--class", "-n", "--classdata",
        "-p", "--pid", "-P", "--pgid", "-u", "--uid",
    },
}


def safe_tokenize(command: str) -> list[str]:
    """Tokenize with shell operators and line breaks split into tokens.

    Uses shlex.shlex(punctuation_chars=';|&') so that `git push&&echo` and
    `git push;echo` split into `['git', 'push', '&&', 'echo']` etc. Plain
    shlex.split keeps operators glued to adjacent words, which would let a
    whitespace-free one-liner bypass detection entirely.

    Newlines are a command separator in Bash but shlex's whitespace_split
    consumes them as generic whitespace, flattening multi-line scripts into
    one token stream. We pre-split the raw command on `\\n` and insert a
    synthetic `;` between line tokens so iter_command_starts sees the break.
    Lines that fail to parse (unmatched quote, runaway heredoc, etc.) are
    skipped — better a silent pass than a crashed hook.

    Caller note: a multi-line value inside a quoted flag (e.g.
    ``gh pr create --body "line1\\nline2"``) is split at the unescaped
    newline, separating ``--body`` from its value. In test payloads, use a
    heredoc-assigned variable instead::

        BODY=$(cat <<'EOF'
        Caller chain verified: ...
        EOF
        )
        gh pr create --body "$BODY"
    """
    lines = [ln for ln in command.split("\n") if ln.strip()]
    if not lines:
        return []
    tokens: list[str] = []
    for idx, line in enumerate(lines):
        if idx > 0:
            tokens.append(";")
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=";|&")
            lex.whitespace_split = True
            lex.commenters = ""  # raw `#` is not a comment here; opt-out marker
            tokens.extend(list(lex))
        except ValueError:
            continue
    return tokens


def strip_prefix(argv: list[str]) -> list[str]:
    """Peel shell keywords, `KEY=VAL` assignments, and wrapper commands off
    the front so argv[0] becomes the real executable.

    Handles (in any order, iteratively):
    - shell keywords (`if`, `then`, `do`, `while`, etc.) — pure syntax, drop
    - env assignments (`FOO=1`) — drop
    - wrapper commands (`env`, `sudo`, `nice`, `time`, `stdbuf`, `ionice`) —
      drop the wrapper plus its option flags. Option flags are peeled
      generically: any `-*` token is consumed, and if it's a known arg-taking
      flag for this wrapper the following value token is peeled too. The
      `--long=value` form counts as a single token and is handled naturally.
    """
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok in SHELL_KEYWORDS:
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        if tok in PREFIX_WRAPPERS:
            wrapper = tok
            i += 1
            opts_with_arg = WRAPPER_OPTS_WITH_ARG.get(wrapper, set())
            while i < n:
                nxt = argv[i]
                if ENV_ASSIGN_RE.match(nxt):
                    i += 1
                    continue
                if not nxt.startswith("-"):
                    break
                if "=" in nxt:
                    # --long=value — value embedded; peel this token only
                    i += 1
                    continue
                if nxt in opts_with_arg and i + 1 < n:
                    # --user admin / -u admin — peel pair
                    i += 2
                    continue
                # bare flag (-E, -i, -oL, etc.) — peel single token
                i += 1
            continue
        break
    return argv[i:]


def iter_command_starts(tokens: list[str]):
    """Yield argv slices at each command start across shell separators."""
    start = 0
    for i, tok in enumerate(tokens):
        if tok in SHELL_SEPARATORS:
            if start < i:
                yield tokens[start:i]
            start = i + 1
    if start < len(tokens):
        yield tokens[start:]


# ---------------------------------------------------------------------------
# Compound-Bash cascade advisory (issue #229)
# ---------------------------------------------------------------------------
#
# When a PreToolUse(Bash) hook rejects a compound command (block, or denied
# ask), bash never runs ANY part — including state-changing redirects, mkdir,
# download-to-file, etc. The classic failure mode is
# `cat <<EOF > /tmp/body.md && gh pr create --body-file /tmp/body.md` where
# the agent assumes the file was written by the rejected redirect and retries
# the second half, hitting `No such file or directory`.

STATE_CHANGING_COMMANDS = frozenset({
    "mkdir", "tee", "cp", "mv", "ln", "rm", "touch",
    "rsync", "dd", "install",
})

# curl: -o/-O/--output/--remote-name write the response body to a file.
# wget: -O/--output-document write the response body. wget's -o is the log
# file, NOT a download target — excluded to avoid false positives on
# `wget -o log.txt URL` (which writes only the log, not a file the agent
# would assume exists at the URL's name).
_CURL_OUTPUT_FLAGS = frozenset({"-o", "-O", "--output", "--remote-name"})
_WGET_OUTPUT_FLAGS = frozenset({"-O", "--output-document"})


def _segment_has_redirect(argv: list[str]) -> bool:
    """True iff argv contains an unquoted `>`, `>>`, or `<<` redirect.

    safe_tokenize strips quotes but preserves internal whitespace, so a token
    containing whitespace cannot be an unquoted shell word — any redirect-like
    substring is literal (e.g. `--body "<<EOF foo"` tokenizes to `<<EOF foo`,
    which is a quoted string, not a heredoc). Tokens without whitespace that
    start with or embed `<<` / `>` / `>>` are treated as redirects, covering
    standalone (`>`, `<<EOF`), attached (`>file`, `<<EOF`), and embedded
    (`foo<<EOF`, `foo>file`) forms.
    """
    for tok in argv:
        if " " in tok or "\t" in tok:
            continue
        if "<<" in tok or ">" in tok:
            return True
    return False


def _segment_has_state_change(argv: list[str]) -> bool:
    argv = strip_prefix(argv)
    if not argv:
        return False
    cmd = argv[0].rsplit("/", 1)[-1]
    if cmd in STATE_CHANGING_COMMANDS:
        return True
    if cmd == "curl":
        for tok in argv[1:]:
            if tok in _CURL_OUTPUT_FLAGS or tok.startswith("--output="):
                return True
    if cmd == "wget":
        for tok in argv[1:]:
            if tok in _WGET_OUTPUT_FLAGS or tok.startswith("--output-document="):
                return True
    return _segment_has_redirect(argv)


def is_compound_command(command: str) -> bool:
    """True iff `command` tokenizes into ≥2 command segments.

    Compound means at least one shell separator (`&&`, `||`, `;`, `|`, or a
    newline-induced synthetic `;`) splits the command into multiple segments.
    Separators inside quoted strings do NOT split (shlex preserves quoting).
    """
    tokens = safe_tokenize(command)
    if not tokens:
        return False
    segments = list(iter_command_starts(tokens))
    return len(segments) >= 2


def has_state_changing_redirect(command: str) -> bool:
    """True iff any segment of `command` performs a file/dir mutation.

    Detects the side-effects that vanish silently when the parent compound
    invocation is rejected at PreToolUse: redirects (`> file`, `>> file`,
    `<<EOF > file`), `mkdir`, `tee`, `cp`/`mv`/`ln`/`rm`/`touch`/`rsync`,
    `curl -o`, `wget -O`.
    """
    tokens = safe_tokenize(command)
    if not tokens:
        return False
    for argv in iter_command_starts(tokens):
        if _segment_has_state_change(argv):
            return True
    return False


COMPOUND_CASCADE_HINT = (
    "\n"
    "Note: this command chains a state-changing step (`> file`, `mkdir`, "
    "`curl -o`, `<<EOF > file`, `tee file`) with another step. PreToolUse "
    "rejection (block or denied ask) aborts ALL parts atomically — files the "
    "redirect/mkdir/download would have created do NOT exist. Before retrying, "
    "use the Write tool to materialize the file first, then issue a separate "
    "Bash call.\n"
)


def compound_cascade_hint(command: str) -> str:
    """Return the canonical cascade-abort hint when applicable, else `""`.

    Called by every PreToolUse(Bash) hook that may reject a command, so the
    same advisory text appears consistently across the chain (issue #229).
    Returns empty string for single commands or compound commands without a
    state-changing segment — the hint is only useful when the cascade was
    likely to leave the agent's mental model out of sync with disk state.
    """
    if not command or not command.strip():
        return ""
    if not is_compound_command(command):
        return ""
    if not has_state_changing_redirect(command):
        return ""
    return COMPOUND_CASCADE_HINT
