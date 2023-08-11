- [Environment Setup](#environment-setup)
  - [Required Packages](#required-packages)
  - [Cloning](#cloning)
  - [Python](#python)
    - [System-wide Python Installation](#system-wide-python-installation)
    - [Specific versions of Python, using Homebrew/MacPorts/rtx/asdf/pyenv](#specific-versions-of-python-using-homebrewmacportsrtxasdfpyenv)
      - [rtx Example](#rtx-example)
      - [Homebrew Example](#homebrew-example)
    - [Python virtualenv](#python-virtualenv)
  - [Rust Setup](#rust-setup)
- [Building](#building)
  - [Installer Log](#installer-log)

# Environment Setup
## Required Packages
To build the installer, you will need the following packages:

1. p7zip (`brew install p7zip` if using Homebrew)
2. Rust with `aarch64-unknown-none-softfloat` (see [Rust setup](#rust-setup))

## Cloning
The project requires a recursive clone, to pull in the m1n1 submodule.

1. `git clone https://github.com/AsahiLinux/asahi-installer --recursive`
2. `cd asahi-installer`

Then if you have everything setup, and are eager to build, you can run `./build.sh`.

## Python
This project targets Python 3.9.6. You can find the latest targeted version of Python in build.sh.

### System-wide Python Installation
Running build.sh will download and setup this version of Python for you, installed globally. This will also install packages globally.

If you develop using Python, or need a specific global Python version, you might not want this. The Asahi Installer does target this specific version in the build.sh shell script, so you should be okay to install multiple system wide versions of Python, for example through pkg files from python.org, or through Homebrew/MacPorts.

Otherwise, you can just use the downloaded version of Python 3.9, and skip to [Rust setup](#rust-setup)

### Specific versions of Python, using Homebrew/MacPorts/rtx/asdf/pyenv
If you wish to use something like rtx/asdf/pyenv, this should be fine. You will, however, need to alter the build.sh file
to not download Python, and also target your Python virtualenv. Maybe if you're brave, you could submit this as PR?

Ensure you target 3.9.6 if possible, though future versions should be okay, but untested.

#### rtx Example
In the below example, I'll use [rtx](https://github.com/jdxcode/rtx), in the `.rtx.toml` file:

```toml
[tools]
python = {version='3.9.6', virtualenv='.venv'}
```
This allows you to target a specific version of Python in this directory, and also create a virtualenv in the `.venv` directory.

#### Homebrew Example
Untested, as this might break the packaged version of `python-asn1`:
```shell
brew install python@3.9
```

### Python virtualenv
If you don't want to use the pkg version of Python, you should use a virtualenv. This will allow you to install packages locally, and not globally.

```shell
# First, check the version of Python is 3.9.6, to ensure rtx/asdf/pyenv/brew etc is working
python3 --version
# Create a new virtualenv, in future you can just run `source .venv/bin/activate`
python3 -m venv .venv
# Activate the virtualenv
source .venv/bin/activate
```

## Rust Setup
The Asahi Installer uses Rust, and is required to build the installer. It however needs ` aarch64-unknown-none-softfloat` to build, which can be installed using [rustup](https://rustup.rs/).

Once you have rustup installed, you can install the target using:

```shell
rustup target add aarch64-unknown-none-softfloat
```

# Building
To build, you can run `./build.sh`.

On the first build, Rust will compile `m1n1` and might take a minute or so to run. Subsequent builds will be faster, if you don't change any Rust code.

The build output should look similar to this:

```shell
Determining version...
Version: v0.6.2-2-g6b0c19a
Downloading installer components...
--2023-08-11 23:25:27--  https://www.python.org/ftp/python/3.9.6/python-3.9.6-macos11.pkg
Resolving www.python.org (www.python.org)... 151.101.28.223, 2a04:4e42:7::223
Connecting to www.python.org (www.python.org)|151.101.28.223|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 38033506 (36M) [application/octet-stream]
Saving to: ‘python-3.9.6-macos11.pkg’

python-3.9.6-macos11.pkg           100%[================================================================>]  36.27M  20.4MB/s    in 1.8s

2023-08-11 23:25:29 (20.4 MB/s) - ‘python-3.9.6-macos11.pkg’ saved [38033506/38033506]

Building m1n1...
INFO: Building on Darwin
INFO: Toolchain path: /opt/homebrew/opt/llvm/bin/
  CC    build/adt.o

# MORE RUST BUILD OUTPUT....

Copying files...
Extracting Python framework...
Brief Usage:
  List:    cpio -it < archive
  Extract: cpio -i < archive
  Create:  cpio -o < filenames > archive
  Help:    cpio --help
```

You should now be able to run `./test.sh` to test the installer.

## Installer Log
The Asahi Installer will log to `installer.log` in the root directory.