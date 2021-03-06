from __future__ import (unicode_literals, absolute_import, division,
                        print_function)
from prettytable import PrettyTable
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
    CONDA_BUILD_START_LINE = "BUILD START: "
    PACKAGE_NAME_LINE = '# $ anaconda upload '
    full_path = os.path.abspath(path_to_log)
    output = []
    package_name = ''
    built_name = ''
    with open(full_path, 'r') as f:
        for line in f.readlines():
            # remove white space and newline characters
            line = line.strip()
            if line.startswith(PACKAGE_NAME_LINE):
                # split the line on the whitespace that looks something like:
                # "# $ anaconda upload /tmp/root/ramdisk/mc/conda-bld/linux-64/album-v0.0.2_py35.tar.bz2"
                built_package_path = line.split()[-1]
                # remove the folder path
                built_package_name = os.path.split(built_package_path)[-1]
                # trim the '.tar.bz2'
                built_name = built_package_name[:-8]
            if line.startswith(CONDA_BUILD_START_LINE) and built_name == '':
                # this is the start of the build section in the conda-build CLI
                built_name = line.split(CONDA_BUILD_START_LINE)[1].strip()
                package_name = built_name.split('-')[0]
            if line.startswith(BUILD_START_LINE):
                # this is the start of *my* cron job script
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
    bundle = []
    gen = (line for line in lines_iterable)
    ret = OrderedDict()
    # parse the init section
    for line in gen:
        bundle.append(line)
        if line.startswith("BUILD START"):
            # remove the build start line from the init section
            line = bundle.pop()
            ret['init'] = bundle
            bundle = [line]
            break
    else:
        ret['init'] = bundle
        return ret
    # parse the build section
    for line in gen:
        bundle.append(line)
        if line.startswith("BUILD END"):
            ret['build'] = bundle
            bundle = []
            break
    else:
        ret['build'] = bundle
        return ret
    # parse the test section
    line = next(gen)
    bundle.append(line)
    if line.startswith("TEST START"):
        # we are in the test section
        for line in gen:
            bundle.append(line)
            if line.startswith("TEST END"):
                ret['test'] = bundle
                bundle = []
                break
        else:
            # we have exhausted the generator without finding
            # the end of the test section.
            ret['test'] = bundle
            return ret
    elif 'test' in line:
        # This line will appear if there is no test section
        ret['test'] = [line]
        bundle = []
    # the rest is the upload section
    ret['upload'] = list(gen)
    return ret


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

    TODO: Join the error on a new line. Need to verify that tests still pass
          after I do this
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
    return line, '\n'.join(err)


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
    ret = {'err': []}
    error = False
    traceback = False
    lines = []
    for line in gen:
        if PACKAGE_NAME in line:
            # format the package name
            ret['built_name'] = line[len(PACKAGE_NAME):]
        line, err = check_for_errors(line, gen)
        if err:
            ret['err'].append(err)
            ret['built_name'] = 'failed'
    return ret


def parse_test(test_section):
    gen = (line for line in test_section)
    ret = {'err': [], 'nothing_to_test': False}
    NOTHING_TO_TEST = 'Nothing to test for: '
    NO_PKGS_FOUND = 'Error: No packages found in'
    for line in gen:
        if line.startswith(NOTHING_TO_TEST):
            ret['nothing_to_test'] = True
        line, err = check_for_errors(line, gen)
        if err:
            ret['err'].append(err)

    return ret


def parse_upload(upload_section):
    ret = {'auto_upload': True}
    AUTO_UPLOAD_NOT_SET = '# $ anaconda upload'
    FILE_ALREADY_EXISTS = '[Conflict]'
    ret['err'] = []
    gen = (line for line in upload_section)
    for line in gen:
        line, err = check_for_errors(line, gen)
        if line.startswith(AUTO_UPLOAD_NOT_SET):
            ret['auto_upload'] = False
        if line.startswith(FILE_ALREADY_EXISTS):
            ret['err'].append(line)
        if err:
            ret['err'].append(err)
    return ret


def simple_parse(path_to_log):
    """Do the whole parsing in a single function call

    Parameters
    ----------
    path_to_log : str
        The path to the log that you want to parse

    Returns
    -------
    dict
        Top level keys are the package name. For each top level key there will
        be up to four keys, {'init', 'build', 'test', and 'upload'}
        package_name:
          init:
            build_command: string
            err: list of strings
          build:
            built_name: string
            err: list of strings
          test:
            nothing_to_test: bool
            err: list of strings
          upload:

    """
    parsed = {}
    for name, built_name, lines in read_log_from_script(path_to_log):
        grouped = parse_conda_build(lines)
        parsed[built_name] = {}
        for section, group in grouped.items():
            func = globals()['parse_%s' % section]
            parsed[built_name][section] = func(group)
            parsed[built_name]['package_name'] = name

    return parsed


def summarize(parsed_log):
    """Summarize the parsed log into a table

    Parameters
    ----------
    parsed_log : output of simple_parse()
    """
    sections = ['init', 'build', 'test', 'upload']
    table = PrettyTable(['library name', 'built package name'] + sections)
    table.align['library name'] = 'l'
    table.align['built package name'] = 'l'
    for pkg_name, parsed_groups in sorted(parsed_log.items()):
        lib_name = parsed_groups['package_name']
        if len(table._rows) > 0 and table._rows[-1][0] == lib_name:
            lib_name = ''
        row = [lib_name, pkg_name]

        for section in sections:
            if section in parsed_groups and parsed_groups[section]['err'] == []:
                msg = 'pass'
            else:
                msg = 'fail'
            row.append(msg)
        table.add_row(row)
    print(table)

if __name__ == "__main__":
    log = os.path.join('test_data', 'build.log')
    summarize(simple_parse(log))
