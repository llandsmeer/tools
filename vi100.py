#!/usr/bin/env python3

from __future__ import print_function

import sys
import termios

IS_UPY = getattr(sys, 'implementation', 'cpython') == 'micropython'

if not IS_UPY:
    from string import printable
    import re
    import tty
    try:
        from time import monotonic
    except ImportError:
        from time import time as monotonic
else:
    from utime import time as monotonic
    import ure as re
    printable = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \t\n\r\x0b\x0c'

def zip_longest(a, b):
    a = iter(a)
    b = iter(b)
    while True:
        try:
            ai = next(a)
        except:
            ai = None
        try:
            bi = next(b)
        except:
            bi = None
        if ai is None and bi is None:
            break
        yield ai, bi

MODE_NORMAL, MODE_INSERT, MODE_VISUAL = 'normal', 'insert', 'visual'

class Pointer:
    def __init__(self, editor, line, col):
        self.editor = editor
        self.line = line
        self.vcol = col

    def move(self, dline, dcol):
        self.line += dline
        self.in_bounds()
        self.vcol = self.col + dcol
        self.in_bounds()

    def in_bounds(self):
        if self.line >= len(self.editor.lines):
            self.line = len(self.editor.lines) - 1
        if self.line < 0:
            self.line = 0
        if self.vcol > self.editor.maxcol:
            self.vcol = self.editor.maxcol
        if self.vcol < 0:
            self.vcol = 0

    def move_start(self):
        self.vcol = 0

    def move_end(self):
        self.vcol = len(self.editor.lines[self.line])
        self.in_bounds()

    @property
    def col(self):
        line_len = len(self.editor.lines[self.line])
        return self.vcol if self.vcol <= line_len else line_len

    @property
    def begin(self):
        return self

    @property
    def end(self):
        return self

    def copy(self):
        return Pointer(self.editor, self.line, self.col)

    def __le__(self, other):
        if self.line < other.line:
            return True
        elif self.line == other.line:
            return self.col <= other.col
        return False

    def set_col(self, col):
        self.vcol = col
        self.in_bounds()

class Selection:
    def __init__(self, editor, begin, end=None):
        self.editor = editor
        self.a = begin
        self.b = begin.copy() if end is None else end

    @property
    def begin(self):
        if self.a <= self.b:
            return self.a
        else:
            return self.b

    @property
    def end(self):
        if self.a <= self.b:
            return self.b
        else:
            return self.a

    @property
    def col(self):
        return self.b.col

    @property
    def line(self):
        return self.b.line

    def move(self, dline, dcol):
        self.b.move(dline, dcol)

    def move_start(self):
        self.b.move_start()

    def move_end(self):
        self.b.move_end()

    def in_bounds(self):
        self.begin.in_bounds()
        self.end.in_bounds()

    def set_col(self, col):
        self.b.set_col(col)

class Editor:
    def __init__(self):
        self.lines = ['']
        self.selection = Pointer(self, 0, 0)
        self.mode = MODE_NORMAL
        self.command_buffer = ''
        self.checkpoint_always = True
        self.keymap_range = {
            'd': self.delete,
            'c': self.change,
            's': self.change
        }
        self.keymap_move = {
            'h': lambda count: self.selection.move(0, -count),
            'l': lambda count: self.selection.move(0, +count),
            'k': lambda count: self.selection.move(-count, 0),
            'j': lambda count: self.selection.move(+count, 0),
            '0': lambda count: self.selection.move_start(),
            '$': lambda count: self.selection.move_end(),
            'w': self.times(self.move_word),
            'e': self.times(lambda: self.move_word(end=True)),
            'b': self.times(lambda: self.move_word_backward()),
            'W': self.times(self.move_word),
            'E': self.times(lambda: self.move_word(end=True)),
            'B': self.times(lambda: self.move_word_backward()),
            'f': self.follow,
            't': self.to
        }
        self.keymap_normal = {
            'W': self.write,
            'Q': self.quit,
            ':w': self.write,
            ':q': self.quit,
            '\x04': self.write_quit,
            'x': self.delete,
            'i': self.insert_mode,
            'a': self.append,
            'v': self.visual_mode,
            's': self.change,
            'o': lambda: self.insert_dline(+1),
            'O': lambda: self.insert_dline(-1),
            ' ': self.checkpoint,
            'u': self.undo,
            '\x12': self.redo
        }
        self.running = True
        self.filename = None
        self.log = []
        self.history = [list(self.lines)]
        self.last_keypress = 0
        self.skip_checkpoint = False

    def checkpoint(self):
        if not self.history or any(a != b for a, b in zip_longest(self.lines, self.history[-1])):
            self.history.append(list(self.lines))

    def history_idx(self):
        for idx in range(len(self.history)-1, -1, -1):
            if all(a == b for a, b in zip_longest(self.lines, self.history[idx])):
                return idx
        return len(self.history)

    def undo(self):
        idx = self.history_idx()
        if idx == len(self.history):
            self.checkpoint()
        if idx > 0:
            self.lines = list(self.history[idx-1])
        self.skip_checkpoint = True
        self.invalidate()

    def redo(self):
        idx = self.history_idx()
        if idx < len(self.history) - 1:
            self.lines = list(self.history[idx+1])
        self.skip_checkpoint = True
        self.invalidate()

    def write_quit(self):
        self.write()
        self.running = False

    def quit(self):
        self.running = False

    def stop_running(self):
        self.running = False

    def move_word(self, end=False):
        line = self.lines[self.selection.line]
        col = self.selection.col
        if col == len(line):
            return
        begin_space = line[col].isspace()
        if not begin_space and end:
            col += 1
        while col < len(line) and line[col].isspace():
            col += 1
        if begin_space:
            self.selection.set_col(col)
            return
        while col < len(line) and not line[col].isspace():
            col += 1
        if end:
            col -= 1
            self.selection.set_col(col)
            return
        while col < len(line) and line[col].isspace():
            col += 1
        self.selection.set_col(col)

    def move_word_backward(self):
        line = self.lines[self.selection.line]
        col = self.selection.col
        if col == len(line):
            if col == 0:
                return
            col -= 1
        if col > 1 and not line[col].isspace() and line[col-1].isspace():
            col -= 1
        while col > 0 and line[col].isspace():
            col -= 1
        while col > 0 and not line[col].isspace():
            col -= 1
        if col != 0:
            col += 1
        self.selection.set_col(col)

    def follow(self, count=1):
        ch = self.term.read_char()
        if ch == '\x1b':
            return
        line = self.lines[self.selection.line]
        col = self.selection.col
        if col == len(line):
            return
        for _i in range(count):
            col = line.find(ch, col+1)
            if col == -1:
                break
        if col != -1:
            self.selection.set_col(col)

    def to(self, count=1):
        ch = self.term.read_char()
        if ch == '\x1b':
            return
        line = self.lines[self.selection.line]
        col = self.selection.col
        if col == len(line):
            return
        for _i in range(count):
            col = line.find(ch, col+1)
            if col == -1:
                break
        if col != -1:
            self.selection.set_col(col-1)

    def load(self, filename):
        self.filename = filename
        self.lines = []
        try:
            with open(filename) as f:
                for line in f:
                    self.lines.append(line.rstrip('\n'))
        except IOError:
            pass
        if not self.lines:
            self.lines = ['']
        self.history = []
        self.checkpoint()

    def insert_dline(self, dline):
        if dline == -1:
            self.lines.insert(self.selection.line, '')
        elif dline == 1:
            self.lines.insert(self.selection.line+1, '')
            self.selection.move(+1, 0)
        self.selection.move_start()
        self.insert_mode()

    def write(self, filename=None):
        if filename is None:
            filename = self.filename
        with open(filename, 'w') as f:
            for line in self.lines:
                print(line, file=f)

    @property
    def maxcol(self):
        maxcol = max(map(len, self.lines))
        return maxcol if maxcol > 0 else 0

    def delete(self, escape=True):
        beginl = self.selection.begin.line
        endl = self.selection.end.line
        beginc = self.selection.begin.col
        endc = self.selection.end.col + 1
        if self.selection.begin.line != self.selection.end.line:
            self.lines[beginl] = self.lines[beginl][self.selection.begin.col:]
            self.lines[endl] = self.lines[endl][:endc+1]
            del self.lines[beginl+1:endl]
            if escape:
                self.escape()
        else:
            line = self.lines[endl]
            line = line[:beginc] + line[endc:]
            self.lines[endl] = line
            if escape:
                self.selection = self.selection.begin
                self.mode = MODE_NORMAL
        self.invalidate()

    def change(self):
        self.delete()
        self.insert_mode()

    def insert(self, x):
        line = self.lines[self.selection.line]
        line = line[:self.selection.col] + x + line[self.selection.col:]
        self.lines[self.selection.line] = line
        self.selection.move(0, len(x))

    def invalidate(self):
        if not self.lines:
            self.lines = ['']
        self.screen.full_render()

    def loop(self):
        while self.running:
            self.skip_checkpoint = False
            ch = self.term.read_char()
            if ch == '\x1b':
                self.escape()
            elif self.mode is MODE_NORMAL or self.mode is MODE_VISUAL:
                now = monotonic()
                if now - self.last_keypress > 0.5:
                    self.command_buffer = ''
                self.last_keypress = now
                self.command_buffer = self.command_buffer + ch
                self.command()
            elif self.mode is MODE_INSERT:
                if ch == '\n':
                    self.lines.insert(self.selection.line+1, self.lines[self.selection.line][self.selection.col:])
                    self.lines[self.selection.line] = self.lines[self.selection.line][:self.selection.col]
                    self.selection.move(1, 0)
                    self.selection.move_start()
                elif ch == '\x7f':
                    self.delete(escape=False)
                    self.selection.move(0, -1)
                elif ch == '\x04':
                    self.write_quit()
                elif ch == '\t':
                    self.insert(' ')
                    col = self.selection.col
                    while (col+1) % 4 != 0:
                        col = self.selection.col
                        self.insert(' ')
                elif ch in printable:
                    self.insert(ch)
                else:
                    self.insert(repr(ch)[1:-1])
                self.invalidate()

    def escape(self):
        self.command_buffer = ''
        if self.mode is MODE_INSERT:
            self.mode = MODE_NORMAL
            self.selection.move(0, -1)
        elif self.mode is MODE_VISUAL:
            self.selection = self.selection.begin
            self.mode = MODE_NORMAL
        self.checkpoint()
        self.invalidate()

    def insert_mode(self):
        self.escape()
        self.mode = MODE_INSERT

    def append(self):
        self.selection.move(0, 1)
        self.insert_mode()

    def visual_mode(self):
        self.mode = MODE_VISUAL
        self.selection = Selection(self, Pointer(self, self.selection.line, self.selection.col))

    def times(self, f):
        def times_(count):
            for _i in range(count):
                f()
        return times_

    def command(self):
        m = re.match(r'(\d+)(.*)', self.command_buffer)
        if m and self.command_buffer[0] != '0':
            count = int(m.group(1))
            command = m.group(2)
        else:
            count = 1
            command = self.command_buffer
        if command in self.keymap_move:
            self.keymap_move[command](count=count)
            self.command_buffer = ''
            self.invalidate()
        elif self.mode is MODE_NORMAL and command in self.keymap_normal:
            for _i in range(count):
                self.keymap_normal[command]()
            self.command_buffer = ''
        elif self.mode is MODE_VISUAL and command in self.keymap_range:
            for _i in range(count):
                self.keymap_range[command]()
            self.command_buffer = ''
        elif self.mode is MODE_NORMAL and len(command) >= 2:
            if command[0] in self.keymap_range and command[1:] in self.keymap_move:
                self.visual_mode()
                self.keymap_move[command[1:]](count=count)
                self.keymap_range[command[0]]()
                self.command_buffer = ''
        elif len(command) > 10:
            self.command_buffer == 0
        if not self.skip_checkpoint:
            self.checkpoint()

class Screen:
    def __init__(self, editor, term):
        self.editor = editor
        self.editor.screen = self
        self.term = term
        self.editor.term = term
        self.scroll = 0
        self.w = self.term.get_width()
        self.h = self.term.get_height()

    def full_render(self):
        self.term.clear()
        self.term.set_cursor_pos(1, 1)
        beginl, endl = self.editor.selection.begin.line, self.editor.selection.end.line
        beginc, endc = self.editor.selection.begin.col, self.editor.selection.end.col
        assert beginl <= endl
        for lineno, line in enumerate(self.editor.lines):
            if self.editor.mode is MODE_VISUAL and beginl <= lineno <= endl:
                if beginl == endl:
                    endc = endc + 1
                    self.term.write(line[:beginc])
                    self.term.set_underline(True)
                    self.term.write(line[beginc:endc])
                    self.term.set_underline(False)
                    self.term.write(line[endc:])
                else:
                    if lineno == beginl:
                        self.term.write(line[:beginc])
                        self.term.set_underline(True)
                        self.term.write(line[beginc:])
                        self.term.set_underline(False)
                    elif lineno == endl:
                        self.term.set_underline(True)
                        self.term.write(line[:endc+1])
                        self.term.set_underline(False)
                        self.term.write(line[endc+1:])
                    else:
                        self.term.set_underline(True)
                        self.term.write(line)
                        self.term.set_underline(False)
            else:
                self.term.write(line)
            self.term.next_line()
        self.term.set_cursor_pos(
                self.editor.selection.line+1,
                self.editor.selection.col+1)

class VT100:
    def __init__(self):
        self.tattr = None

    def begin(self):
        self.tattr = termios.tcgetattr(sys.stdin.fileno())
        if IS_UPY:
            termios.setraw(sys.stdin.fileno())
        else:
            tty.setcbreak(sys.stdin.fileno(), termios.TCSANOW)

    def end(self):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self.tattr)

    def read_char(self):
        try:
            return sys.stdin.read(1)
        except KeyboardInterrupt:
            return '\x1b'

    def clear(self):
        self.emit('\033[2J')

    def write(self, x):
        self.emit(x)

    def next_line(self):
        self.emit('\033E')

    def set_underline(self, x=True):
        if x:
            self.emit('\033[4m')
        else:
            self.emit('\033[24m')

    def unset(self):
        self.emit('\033[m')

    def clear_line(self):
        self.emit('\033[2K')

    def set_cursor_pos(self, line, col):
        self.emit('\033[{line};{col}f'.format(line=line, col=col))

    def get_cursor_pos(self):
        self.emit('\033[6n')
        buf = ''
        while True:
            buf += sys.stdin.read(1)
            if buf[-1] == 'R':
                break
        matches = re.match(r"^\x1b\[(\d*);(\d*)R", buf)
        if not matches:
            return 10, 10
            return None
        groups = matches.groups()
        return int(matches.group(1)), int(matches.group(2))

    def emit(self, x):
        sys.stdout.write(x)
        if not IS_UPY:
            sys.stdout.flush()

    def get_width(self):
        i = 1
        w = 0
        while True:
            self.set_cursor_pos(1, i)
            _l, c = self.get_cursor_pos()
            if w == c:
                return c
            w = c
            i += 1

    def get_height(self):
        i = 1
        h = 0
        while True:
            self.set_cursor_pos(i, 1)
            l, _c = self.get_cursor_pos()
            if h == l:
                return l
            h = l
            i += 1

def e(filename):
    term = VT100()
    editor = Editor()
    editor.load(filename)
    try:
        term.begin()
        screen = Screen(editor, term)
        screen.full_render()
        editor.loop()
    except KeyboardInterrupt:
        pass
    finally:
        term.end()
    return editor

if __name__ == '__main__':
    editor = e(sys.argv[1])
    for line in editor.log:
        print(repr(line))
