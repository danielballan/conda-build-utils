
from __future__ import (unicode_literals, absolute_import, division,
                        print_function)
import six

import os
from collections import OrderedDict

def read_log_from_script(path_to_log):
    """
    Parse the log that is output from the `dev-build` script

    Parameters
    ----------
    path_to_log : str
        The path to the log file that results from `bash dev-build > log 2>&1`

    Yields
    ------
    package : str
        The name of the package that is being built
    output : list
        The lines that were output for the build/test/upload of `package`
    """
    BUILD_START_LINE = '/tmp/staged-recipes'
    PACKAGE_NAME_LINE = '# $ anaconda upload '
    full_path = os.path.abspath(path_to_log)
    output = []
    package_name = ''
    with open(full_path, 'r') as f:
        for line in f.readlines():
            # remove white space and newline characters
            line = line.strip()
            if line.startswith(PACKAGE_NAME_LINE):
                # split the line on the whitespace that looks something like:
                # "# $ anaconda upload /some/path/album-v0.0.2_py35.tar.bz2"
                built_package_path = line.split()[-1]
                # remove the folder path
                built_package_name = os.path.split(built_package_path)[-1]
                # trim the '.tar.bz2'
                built_name = built_package_name[:-8]
            if line.startswith(BUILD_START_LINE):
                # always have to treat the first package differently...
                if package_name != '':
                    yield package_name, built_name, output
                package_name = os.path.split(line)[1]
                built_name = '%s-build-name-not-found' % package_name
                output = []
            else:
                output.append(line)

    yield package_name, built_name, output


def parse_conda_build(lines_iterable):
    """
    Group the output from conda-build into
    - 'build_init'
    - 'build'
    - 'test'
    - 'upload'
    """
    from collections import defaultdict
    bundle = []
    next_line_might_be_test = False
    init = True
    build = False
    test = False
    key = 'init'
    ret = []
    for line in lines_iterable:
        bundle.append(line)
        # init
        if init:
            if line.startswith("BUILD START"):
                line = bundle.pop()
                ret.append((key, bundle))
                bundle = [line]
                init = False
                build = True
                key = 'build'
        # build
        if build:
            if line.startswith("BUILD END"):
                next_line_might_be_test = True
                build = False
                continue
        # determine if test or upload comes next
        if next_line_might_be_test:
            next_line_might_be_test = False
            line = bundle.pop()
            ret.append((key, bundle))
            if line.startswith("TEST START"):
                test = True
                key = 'test'
                bundle = [line]
            elif line.startswith('Nothing to test for'):
                ret.append(('test', [line]))
                bundle = []
                key = 'upload'
            else:
                key = 'upload'
                bundle = [line]
        # test
        if test:
            if line.startswith("TEST END"):
                ret.append((key, bundle))
                bundle = []
                test = False
                key='upload'

    if bundle:
        ret.append((key, bundle))
    return OrderedDict(ret)

def check_for_errors(line, gen):
    """Check for errors in the generator `gen` that is passed in.

    Specifically look at `line` and see if it starts with "Error: " or
    "Traceback". If so, start iterating over `gen` until there is a blank line
    or the generator ends.  Return the last line and any lines that are errors

    Parameters
    ----------
    line : str
        The last line that was taken from `gen`
    gen : generator
        The generator that should be iterated over if `line` is the start of
        an error message

    Returns
    -------
    line : str
        The last line that was taken from `gen`. Might be the same line that
        was passed in
    err : list
        The list of lines that make up the error message. If `err` is an empty
        list, that signifies that the input `line` is not an error message.
    """
    ERROR = "Error: "
    TRACEBACK = 'Traceback (most recent call last):'
    err = []
    if line.startswith(ERROR) or line == TRACEBACK:
        if line.startswith(ERROR) or line == TRACEBACK:
            try:
                while line != '':
                    err.append(line)
                    line = next(gen)
            except StopIteration:
                # this is thrown when the error goes to the end of the
                # log section
                pass
    return line, err


def parse_init(init_section):
    """Parse the init section from the output of conda build

    Specifically look for the build_command and any errors that may have
    occurred

    Parameters
    ----------
    init_section : iterable
        Iterable of the lines that occur before conda-build spits out the line
        that reads: "BUILD START"

    Returns
    -------
    dict
        Keyed on
        - 'build_command': something like this: conda-build /tmp/staged-recipes/recipes/tifffile --python=3.5
        - 'err': Might be an empty list. Otherwise it will be a list of lists,
                 where each top level list will be the output of
                 `check_for_errors()`
    """
    ret = {}
    gen = (line for line in init_section)
    ret['err'] = []
    for line in gen:
        if 'CONDA_CMD' in line:
            ret['build_command'] = line.split('-->')[1].strip()
        line, err = check_for_errors(line, gen)
        if err:
            ret['err'].append(err)
    return ret


def parse_build(build_section):
    """Parse the build section output from `conda-build`. This is everything
    between the lines that start with "BUILD START" and "BUILD FINISH".

    Parameters
    ----------
    build_section : iterable
        Iterable of all lines between "BUILD START" and "BUILD END"

    Returns
    -------
    dict
        Keyed on
        - 'built_name': Will either be 'failed' or the full name of the
                        package that will look something like
                        suitcase-0.2.1-py35_0
        - 'err': Might be an empty list. Otherwise it will be a list of lists,
                 where each top level list will be the output of
                 `check_for_errors()`
    """
    gen = (line for line in build_section)
    PACKAGE_NAME = 'Package: '
    ret = {'error': []}
    error = False
    traceback = False
    lines = []
    for line in gen:
        if PACKAGE_NAME in line:
            # format the package name
            ret['built_name'] = line[len(PACKAGE_NAME):]
        line, err = check_for_errors(line, gen)
        if err:
            ret['error'].append(err)
            ret['built_name'] = 'failed'
    return ret


if __name__ == "__main__":
    log = 'build.log'
    gen = list(read_log_from_script(log))
    parsed = {built_name: parse_conda_build(lines) for name, built_name, lines in gen}
    width = max([len(name) for name in parsed.keys()])
    for name, groups in parsed.items():
        print(('{:%ds} -- {}' % width).format(name, [key for key, bundle in groups]))