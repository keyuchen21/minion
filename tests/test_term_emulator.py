#!/usr/bin/env python3
"""Minimal VT100 terminal emulator to test minion's status-bar scroll region.

Implements just the control sequences minion.py emits:
  - CSI <t>;<b>r            DECSTBM (set scroll region)
  - CSI <row>;<col>H        CUP (cursor position)
  - CSI <n>A/B/C/D          CUU/CUD/CUF/CUB
  - CSI 2K                  EL (erase line, all)
  - CSI 0J / CSI J          ED (erase from cursor to end)
  - printable chars, \r, \n

After feeding a byte stream, we can inspect the screen grid row-by-row to see
whether row 1 (the status bar) survived a scroll.
"""
import re


class Screen:
    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.grid = [[" "] * cols for _ in range(rows)]
        # cursor
        self.cy = 0  # 0-indexed row
        self.cx = 0  # 0-indexed col
        # scroll region (0-indexed, inclusive), default whole screen
        self.top = 0
        self.bot = rows - 1

    def _scroll_up(self, n=1):
        """Scroll the current scroll region up by n lines (top lines lost,
        n blank lines appended at the bottom of the region)."""
        for _ in range(n):
            del self.grid[self.top]
            self.grid.insert(self.bot, [" "] * self.cols)

    def _index(self):
        """Cursor down one line; if at bottom margin of scroll region, scroll."""
        if self.cy == self.bot:
            self._scroll_up(1)
        elif self.cy < self.rows - 1:
            self.cy += 1
        # if cy > bot already (cursor outside region below), still move down

    def _newline(self):
        # \n -> move down (index); ONLCR means \r\n combo, but we handle \n as LF
        self._index()

    def _carriage_return(self):
        self.cx = 0

    def _write_char(self, ch):
        if self.cx >= self.cols:
            # auto-wrap: move to next line
            self._carriage_return()
            self._index()
        self.grid[self.cy][self.cx] = ch
        self.cx += 1

    def feed(self, data):
        i = 0
        n = len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":  # ESC
                # parse a CSI sequence
                if i + 1 < n and data[i + 1] == "[":
                    j = i + 2
                    params = ""
                    while j < n and (data[j].isdigit() or data[j] == ";"):
                        params += data[j]
                        j += 1
                    if j < n:
                        cmd = data[j]
                        self._csi(params, cmd)
                        i = j + 1
                        continue
                    else:
                        break
                else:
                    # bare ESC <x>, skip
                    i += 2
                    continue
            elif ch == "\r":
                self._carriage_return()
                i += 1
            elif ch == "\n":
                self._newline()
                i += 1
            else:
                self._write_char(ch)
                i += 1

    def _parse_params(self, params, count, defaults):
        parts = params.split(";") if params else []
        out = []
        for k in range(count):
            if k < len(parts) and parts[k] != "":
                out.append(int(parts[k]))
            else:
                out.append(defaults[k])
        return out

    def _csi(self, params, cmd):
        if cmd == "r":  # DECSTBM
            t, b = self._parse_params(params, 2, [1, self.rows])
            # 1-indexed -> 0-indexed
            self.top = t - 1
            self.bot = b - 1
            # DECSTBM moves cursor to home (origin) of the region per spec
            self.cy = self.top
            self.cx = 0
        elif cmd == "H":  # CUP
            r, c = self._parse_params(params, 2, [1, 1])
            self.cy = r - 1
            self.cx = c - 1
            if self.cy < 0:
                self.cy = 0
            if self.cx < 0:
                self.cx = 0
        elif cmd == "A":  # CUU
            n = self._parse_params(params, 1, [1])[0]
            self.cy = max(0, self.cy - n)
        elif cmd == "B":  # CUD
            n = self._parse_params(params, 1, [1])[0]
            self.cy = min(self.rows - 1, self.cy + n)
        elif cmd == "C":  # CUF
            n = self._parse_params(params, 1, [1])[0]
            self.cx = min(self.cols - 1, self.cx + n)
        elif cmd == "D":  # CUB
            n = self._parse_params(params, 1, [1])[0]
            self.cx = max(0, self.cx - n)
        elif cmd == "K":  # EL
            mode = self._parse_params(params, 1, [0])[0]
            if mode == 2:
                self.grid[self.cy] = [" "] * self.cols
            elif mode == 0:
                for x in range(self.cx, self.cols):
                    self.grid[self.cy][x] = " "
            elif mode == 1:
                for x in range(0, self.cx + 1):
                    self.grid[self.cy][x] = " "
        elif cmd == "J":  # ED
            mode = self._parse_params(params, 1, [0])[0]
            if mode == 0:  # cursor to end of screen
                for x in range(self.cx, self.cols):
                    self.grid[self.cy][x] = " "
                for r in range(self.cy + 1, self.rows):
                    self.grid[r] = [" "] * self.cols
            elif mode == 2:
                for r in range(self.rows):
                    self.grid[r] = [" "] * self.cols
        # ignore unknown (e.g. ?25h, ?2004h) — private mode sets

    def dump(self):
        for r in range(self.rows):
            line = "".join(self.grid[r]).rstrip()
            print(f"{r+1:2d}|{line}")
        print(f"   cursor=({self.cy+1},{self.cx+1}) region={self.top+1}..{self.bot+1}")


def strip_ansi_color(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


if __name__ == "__main__":
    # Reproduce minion's exact setup sequence for a 10-row x 40-col terminal.
    rows, cols = 10, 40
    sc = Screen(rows, cols)

    # Pre-fill stale content (simulating previous shell output in rows 2..)
    stale = "OLD STALE LINE"
    for r in range(2, rows + 1):
        sc.feed(f"\x1b[{r};1H{stale} #{r}")

    print("=== BEFORE setup ===")
    sc.dump()

    # Now emit minion's _setup_status_bar() sequence
    status = "minion | MODEL | auto:low"
    seq = ""
    seq += f"\x1b[2;{rows}r"               # DECSTBM 2..rows
    seq += f"\x1b[1;1H\x1b[2K{status}"     # paint row 1
    seq += f"\x1b[2;1H\x1b[J"              # erase rows 2.. from cursor
    seq += f"\x1b[{rows};1H"               # park cursor at bottom
    sc.feed(seq)

    print("\n=== AFTER setup (stale wiped, bar pinned) ===")
    sc.dump()

    # Now simulate the banner + many lines of chat output that fill the region
    # and force scrolling.
    sc.feed("\r\n")  # banner line (minion ...)
    sc.feed("banner line here\r\n")
    for k in range(rows + 4):
        sc.feed(f"chat line {k}\r\n")

    print("\n=== AFTER enough output to force scrolling ===")
    sc.dump()

    row1 = "".join(sc.grid[0]).rstrip()
    print(f"\n>>> row 1 now: {row1!r}")
    print(">>> STATUS BAR SURVIVED" if "minion" in row1.lower() else ">>> STATUS BAR LOST / SCROLLED AWAY")
