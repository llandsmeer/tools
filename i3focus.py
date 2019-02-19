#!/usr/bin/env python3
#
# i3focus - Highlight the current window using an inset border
# Copyright (C) 2017 Lennart Landsmeer <lennart@landsmeer.email>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

import sys
import collections
import contextlib
import json
import os
import select
import socket
import struct
import subprocess

import timerfd
import xcffib
import xcffib.xproto

DEFAULT_INTERVAL = 0.8
DEFAULT_SIZE = 8
DEFAULT_COLOR = 0xffff0000
DEFAULT_COLOR = 0xff007fff

I3Event = collections.namedtuple('I3Event', 'type message')
FocusEvent = collections.namedtuple('FocusEvent', 'x y w h')

BorderWindows = collections.namedtuple('BorderWindows', 'top left right bot')

class Border:
    def __init__(self, size=DEFAULT_SIZE, color=DEFAULT_COLOR):
        self.size = size
        self.color = color
        self.connection = xcffib.connect()
        setup = self.connection.get_setup()
        self.screen = setup.roots[self.connection.pref_screen]
        self.windows = BorderWindows._make(self.create_window() for _ in range(4))

    def show(self, x, y, w, h):
        b = self.size
        mask = (xcffib.xproto.ConfigWindow.X |
                xcffib.xproto.ConfigWindow.Y |
                xcffib.xproto.ConfigWindow.Width |
                xcffib.xproto.ConfigWindow.Height)
        self.connection.core.ConfigureWindow(self.windows.top, mask, [x, y, w, b])
        self.connection.core.ConfigureWindow(self.windows.left, mask, [x, y, b, h])
        self.connection.core.ConfigureWindow(self.windows.right, mask, [x+w-b, y, b, h])
        self.connection.core.ConfigureWindow(self.windows.bot, mask, [x, y+h-b, w, b])
        for window in self.windows:
            self.connection.core.MapWindow(window)
        self.connection.flush()

    def hide(self):
        for window in self.windows:
            self.connection.core.UnmapWindow(window)
        self.connection.flush()

    def create_window(self):
        window = self.connection.generate_id()
        self.connection.core.CreateWindow(
            xcffib.CopyFromParent,
            window,
            self.screen.root,
            0, 0, 1, 1,
            0,
            xcffib.xproto.WindowClass.InputOutput,
            self.screen.root_visual,
            xcffib.xproto.CW.BackPixel | xcffib.xproto.CW.OverrideRedirect,
            [self.color, 1])
        return window

    def fileno(self):
        return self.connection.get_file_descriptor()

    def close(self):
        self.connection.disconnect()
        self.connection = None

    def poll(self):
        self.connection.poll_for_event()


class I3:
    MAGIC = 'i3-ipc'.encode('utf8')
    HEADER_FORMAT = 'II'
    TYPE_SUBSCRIBE = 2
    TYPE_GET_TREE = 4
    REPLY_TYPE_TREE = 4
    EVENT_WINDOW = (1 << 31) | 3
    EVENT_WORKSPACE = (1 << 31) | 0
    EVENT_OUTPUT = (1 << 31) | 1

    def __init__(self):
        self.socket = self.create_socket()
        self.subscribe()
        assert self.read().message['success']
        self.get_tree()

    @classmethod
    def socket_path(cls):
        return subprocess.getoutput('i3 --get-socketpath')

    @classmethod
    def create_socket(cls):
        socket_path = cls.socket_path()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        return sock

    def subscribe(self):
        self.write(self.TYPE_SUBSCRIBE, ['window', 'workspace', 'output'])

    def get_tree(self):
        self.write(self.TYPE_GET_TREE, "")

    def write(self, type_, message):
        if not isinstance(message, str):
            message = json.dumps(message)
        if isinstance(message, str):
            message = message.encode('utf8')
        size = len(message)
        header = self.MAGIC + struct.pack(self.HEADER_FORMAT, size, type_)
        self.socket.sendall(header)
        self.socket.sendall(message)

    def read(self, magic=None):
        if magic is None:
            magic = self.socket.recv(6)
        assert magic == self.MAGIC
        header = self.socket.recv(8)
        size, type_ = struct.unpack(self.HEADER_FORMAT, header)
        message = self.socket.recv(size)
        message = json.loads(message.decode('utf8'))
        return I3Event(type_, message)

    def read_nonblocking(self):
        self.socket.setblocking(False)
        try:
            magic = self.socket.recv(6)
        except BlockingIOError:
            return
        self.socket.setblocking(True)
        return self.read(magic=magic)

    def fileno(self):
        return self.socket.fileno()

    def close(self):
        self.socket.close()
        self.socket = None

    def poll(self):
        event = self.read_nonblocking()
        if event is None:
            return
        message = event.message
        if event.type == self.EVENT_WINDOW:
            change = message['change']
            tree = message['container']
            if change == 'focus':
                return self.parse_focus_rect(tree)
            elif change in {'new', 'close', 'move'}:
                self.get_tree()
            else:
                print('unknown window change', change)
        elif event.type == self.EVENT_WORKSPACE:
            change = message['change']
            if change == 'focus':
                return self.parse_focus_rect(message['current'])
            else:
                print('unknown workspace change', change)
        elif event.type == self.EVENT_OUTPUT:
            self.get_tree()
        elif event.type == self.REPLY_TYPE_TREE:
            return self.parse_focus_tree(message)
        else:
            print('unkown type', event.type)

    @classmethod
    def parse_focus_rect(cls, tree):
        rect = tree['rect']
        return FocusEvent(rect['x'], rect['y'], rect['width'], rect['height'])

    @classmethod
    def parse_focus_tree(cls, tree):
        if tree.get('focused') and tree['type'] == 'con':
            return cls.parse_focus_rect(tree)
        for node in tree.get('nodes', []):
            event = cls.parse_focus_tree(node)
            if event:
                return event


class Timer:
    def __init__(self, seconds=DEFAULT_INTERVAL):
        self.fd = timerfd.create(timerfd.CLOCK_MONOTONIC, timerfd.TFD_NONBLOCK)
        self.seconds = seconds

    def fileno(self):
        return self.fd

    def set(self, seconds=None):
        if seconds is None:
            seconds = self.seconds
        timerfd.settime(self.fd, 0, seconds, 0)

    def clear(self):
        self.set(0)

    def poll(self):
        os.read(self.fd, 8)

def setup():
    from setuptools import setup
    setup(name='i3focus',
          py_modules=['i3focus'],
          author='Lennart Landsmeer',
          author_email='lennart@landsmeer.email',
          license='GPLv3',
          entry_points={
              'console_scripts': [
                  'i3-focus = i3focus:main'
              ]
     })

def main():
    i3 = I3()
    border = Border()
    timer = Timer()
    try:
        with contextlib.closing(i3), contextlib.closing(border):
            while True:
                readable, _w, _r = select.select([i3, border, timer], [], [])
                if i3 in readable:
                    event = i3.poll()
                    if isinstance(event, FocusEvent):
                        border.show(*event)
                        timer.set()
                if timer in readable:
                    timer.poll()
                    border.hide()
                if border in readable:
                    border.poll()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    if 'setup' in sys.argv:
        sys.argv.remove('setup')
        setup()
    else:
        main()
