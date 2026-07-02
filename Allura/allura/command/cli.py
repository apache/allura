#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""The `allura` command-line script.  A replacement for the old `paster` script from PasteScript.

Commands are registered under the "allura.commands" entry point group, by Allura itself and by any
tool packages (e.g. ForgeBlog, ForgeChat).
"""

from collections import defaultdict
import importlib.metadata
import sys

from allura.command.base import BadCommand

ENTRY_POINT_GROUP = 'allura.commands'


def load_commands() -> dict[str, importlib.metadata.EntryPoint]:
    return {ep.name: ep for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)}


def print_help(eps: dict[str, importlib.metadata.EntryPoint]) -> None:
    print('Usage: allura COMMAND [command_options]')
    print("Run 'allura COMMAND --help' for details on a command.")
    by_group = defaultdict(list)
    for name, ep in sorted(eps.items()):
        cmd_class = ep.load()
        summary = (cmd_class.summary or '').strip().splitlines()
        by_group[cmd_class.group_name].append((name, summary[0] if summary else ''))
    for group in sorted(by_group):
        print(f'\n{group or "Other"} commands:')
        for name, summary in by_group[group]:
            print(f'  {name:35} {summary}')


def main(argv: list | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    eps = load_commands()
    if not argv or argv[0] in ('help', '-h', '--help'):
        print_help(eps)
        return 0
    command_name = argv[0]
    ep = eps.get(command_name)
    if ep is None:
        print(f'Unknown command: {command_name}\n')
        print_help(eps)
        return 2
    cmd_class = ep.load()
    try:
        return cmd_class(command_name).run(argv[1:])
    except BadCommand as e:
        print(e.message)
        return e.exit_code


if __name__ == '__main__':
    sys.exit(main())
