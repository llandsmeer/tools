# Various tools

# i3focus.py

i3-focus highlights the current window with focus.
By default it shows a blue 8px inset border.
Works only on linux (timerfd) and with i3 running.

## Installation

```bash
./i3focus.py setup install
``` 

## Requirements

 - pytimerfd
 - xcffib
 
```bash
pip3 install pytimerfd xcffib
```

# PyLineProf

Proof of concept line by line python profiler.
It naively rewrites the input file by inserting begin and end statements around every line.
Simple statements (`x = a + b`) have a large 3x overhead,
but overal it gives a good idea where performance issues are located.

Requires Python 3.5.

## Usage

`./lineprof.py /script/to/profile.py`

## Example

![Profiling a simple script](img/pylineprof-example.gif)

## Dependencies

* astunparse (optional)

# Git Vim Read Undofile

Parse a vim undo file and transform it into a set of git commits.

## Usage

```text
usage: git-vim-read-undofile [-h] -f FILE [-u FILE] [-n NAME]
                             [--blobs | --trees] [-q]

import a vim undofile in git

optional arguments:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  path to file
  -u FILE, --undo FILE  path to undofile
  -n NAME, --name NAME  filename in git
  --blobs               write only blobs
  --trees               write only blobs and trees
  -q, --quiet           show only last commmit hash
```


# Git Dot

Export all the objects in a git repository in DOT format.

## Usage

    git dot [--show] [--commits] [--trees] [--refs] [--heads]

            --show      do not write to stdout; render to temporary file as svg
                        and show using default viewer
    
        turn on filtering and enable: (multiple allowed)
            --commits   commit objects
            --trees     commit objects and tree objects
            --refs      refs ($GIT_DIR/refs)
            --heads     heads ($GIT_DIR/*HEAD)

## Installation

    $ install git-dot /usr/bin

## Example

    $ touch file-a file-b
    $ git init
    $ git add file-a && git commit -m a
    $ git branch branch-a
    $ git add file-b && git commit -m b
    $ git dot --show

![Repository graph](img/git-dot-example.svg)

### Visualizing detached HEAD state

    $ git checkout HEAD^
    ...
    You are in 'detached HEAD' state.
    ...
    $ git dot --show

![Repository graph](img/git-dot-detached.svg)

# vi100.py

Minimal vi clone in python when no editor is available (like a microcontroller).
Depends on Python 3 or MicroPython.

# dconv.c

Simple data conversion for tab or space separated text files.
Arguments are of the form `<key>` of `<src>:<dst>`
where the column `<key>` is extracted as is and `<src>` is extracted and renamed to `<dst>`.
Only support for the most simple use cases is implemented.
Its main purpose is fast dataconversion of large files
between different bioinformatics tools.


```bash
$ cc -O3 dconv.c -o dconv
$ ./dconv.c x y << EOF
x y z
0 1 2
3 4 5
6 7 8
EOF
x y
0 1
3 4
6 7
$ ./dconv.c src:dst  << EOF
src
1
EOF
dst
1
```
 
