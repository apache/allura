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

import re
import sys
import logging

from ming.orm import session
from mock import patch, Mock

from . import base

from allura import model as M
import six

log = logging.getLogger(__name__)


class CreateTroveCategoriesCommand(base.Command):
    min_args = 1
    max_args = None
    usage = '<ini file>'
    summary = 'Remove any existing trove categories and load new ones'
    parser = base.Command.standard_parser(verbose=True)

    # NOTE: order is important
    # To add new migration append it's name to following list,
    # and create method m__<migration_name>
    migrations = [
        'sync',
        'set_parent_only',
        'add_license',
        'set_show_as_skills',
    ]

    def create_trove_cat(self, cat_data):
        data = {'trove_cat_id': cat_data[0],
                'trove_parent_id': cat_data[1],
                'shortname': cat_data[2],
                'fullname': cat_data[3],
                'fullpath': cat_data[4]}
        if len(cat_data) > 5:
            data['show_as_skill'] = cat_data[5]
        M.TroveCategory(**data)

    def update_trove_cat(self, trove_cat_id, attr_dict):
        ts = M.TroveCategory.query.find(dict(trove_cat_id=trove_cat_id))
        if ts.count() < 1:
            sys.exit("Couldn't find TroveCategory with trove_cat_id=%s" %
                     trove_cat_id)
        for t in ts:
            for k, v in attr_dict.items():
                setattr(t, k, v)

    # patching to avoid a *lot* of event hooks firing, and taking a long long time
    @patch.object(M.project.TroveCategoryMapperExtension, 'after_insert', Mock())
    @patch.object(M.project.TroveCategoryMapperExtension, 'after_update', Mock())
    @patch.object(M.project.TroveCategoryMapperExtension, 'after_delete', Mock())
    def command(self):
        self.basic_setup()
        M.TroveCategory.query.remove()
        self.create_trove_cat(
            (617, 274, "kirghiz", "Kirghiz", "Translations :: Kirghiz", True))
        self.create_trove_cat(
            (372, 274, "croatian", "Croatian", "Translations :: Croatian", True))
        self.create_trove_cat(
            (351, 274, "thai", "Thai", "Translations :: Thai", True))
        self.create_trove_cat(
            (349, 274, "tamil", "Tamil", "Translations :: Tamil", True))
        self.create_trove_cat(
            (347, 274, "romanian", "Romanian", "Translations :: Romanian", True))
        self.create_trove_cat(
            (339, 274, "korean", "Korean", "Translations :: Korean", True))
        self.create_trove_cat(
            (632, 160, "cobol", "COBOL", "Programming Language :: COBOL", True))
        self.create_trove_cat(
            (598, 160, "aspectj", "AspectJ", "Programming Language :: AspectJ", True))
        self.create_trove_cat(
            (167, 160, "euler", "Euler", "Programming Language :: Euler", True))
        self.create_trove_cat(
            (185, 160, "shell", "Unix Shell", "Programming Language :: Unix Shell", True))
        self.create_trove_cat(
            (184, 160, "asp", "ASP", "Programming Language :: ASP", True))
        self.create_trove_cat(
            (273, 160, "Pike", "Pike", "Programming Language :: Pike", True))
        self.create_trove_cat(
            (271, 160, "csharp", "C#", "Programming Language :: C#", True))
        self.create_trove_cat(
            (170, 160, "lisp", "Lisp", "Programming Language :: Lisp", True))
        self.create_trove_cat(
            (169, 160, "fortran", "Fortran", "Programming Language :: Fortran", True))
        self.create_trove_cat(
            (625, 160, "simulink", "Simulink", "Programming Language :: Simulink", True))
        self.create_trove_cat(
            (626, 160, "matlab", "MATLAB", "Programming Language :: MATLAB", True))
        self.create_trove_cat(
            (1, 0, "audience", "Intended Audience", "Intended Audience", False))
        self.create_trove_cat(
            (618, 535, "nonprofit", "Non-Profit Organizations",
             "Intended Audience :: by Industry or Sector :: Non-Profit Organizations", False))
        self.create_trove_cat((599, 535, "aerospace", "Aerospace",
                               "Intended Audience :: by Industry or Sector :: Aerospace", False))
        self.create_trove_cat((569, 535, "government", "Government",
                               "Intended Audience :: by Industry or Sector :: Government", False))
        self.create_trove_cat(
            (363, 535, "informationtechnology", "Information Technology",
             "Intended Audience :: by Industry or Sector :: Information Technology", False))
        self.create_trove_cat(
            (361, 535, "financialinsurance", "Financial and Insurance Industry",
             "Intended Audience :: by Industry or Sector :: Financial and Insurance Industry", False))
        self.create_trove_cat(
            (362, 535, "healthcareindustry", "Healthcare Industry",
             "Intended Audience :: by Industry or Sector :: Healthcare Industry", False))
        self.create_trove_cat((367, 535, "scienceresearch", "Science/Research",
                               "Intended Audience :: by Industry or Sector :: Science/Research", False))
        self.create_trove_cat((359, 535, "customerservice", "Customer Service",
                               "Intended Audience :: by Industry or Sector :: Customer Service", False))
        self.create_trove_cat((360, 535, "education", "Education",
                               "Intended Audience :: by Industry or Sector :: Education", False))
        self.create_trove_cat((365, 535, "manufacturing", "Manufacturing",
                               "Intended Audience :: by Industry or Sector :: Manufacturing", False))
        self.create_trove_cat(
            (368, 535, "telecommunications", "Telecommunications Industry",
             "Intended Audience :: by Industry or Sector :: Telecommunications Industry", False))
        self.create_trove_cat(
            (166, 160, "eiffel", "Eiffel", "Programming Language :: Eiffel", True))
        self.create_trove_cat(
            (550, 160, "oberon", "Oberon", "Programming Language :: Oberon", True))
        self.create_trove_cat(
            (553, 160, "realbasic", "REALbasic", "Programming Language :: REALbasic", True))
        self.create_trove_cat(
            (178, 160, "python", "Python", "Programming Language :: Python", True))
        self.create_trove_cat(
            (179, 160, "rexx", "Rexx", "Programming Language :: Rexx", True))
        self.create_trove_cat(
            (177, 160, "prolog", "Prolog", "Programming Language :: Prolog", True))
        self.create_trove_cat(
            (176, 160, "perl", "Perl", "Programming Language :: Perl", True))
        self.create_trove_cat(
            (175, 160, "pascal", "Pascal", "Programming Language :: Pascal", True))
        self.create_trove_cat(
            (536, 534, "enduser_advanced", "Advanced End Users",
             "Intended Audience :: by End-User Class :: Advanced End Users", False))
        self.create_trove_cat((4, 534, "sysadmins", "System Administrators",
                               "Intended Audience :: by End-User Class :: System Administrators", False))
        self.create_trove_cat(
            (471, 456, "ui_swing", "Java Swing", "User Interface :: Graphical :: Java Swing", True))
        self.create_trove_cat(
            (469, 456, "ui_dotnet", ".NET/Mono", "User Interface :: Graphical :: .NET/Mono", True))
        self.create_trove_cat(
            (231, 456, "gnome", "Gnome", "User Interface :: Graphical :: Gnome", True))
        self.create_trove_cat((229, 456, "x11", "X Window System (X11)",
                               "User Interface :: Graphical :: X Window System (X11)", True))
        self.create_trove_cat(
            (475, 456, "ui_opengl", "OpenGL", "User Interface :: Graphical :: OpenGL", True))
        self.create_trove_cat(
            (474, 456, "ui_framebuffer", "Framebuffer", "User Interface :: Graphical :: Framebuffer", True))
        self.create_trove_cat(
            (472, 456, "ui_swt", "Java SWT", "User Interface :: Graphical :: Java SWT", True))
        self.create_trove_cat(
            (470, 456, "ui_awt", "Java AWT", "User Interface :: Graphical :: Java AWT", True))
        self.create_trove_cat((230, 456, "win32", "Win32 (MS Windows)",
                               "User Interface :: Graphical :: Win32 (MS Windows)", True))
        self.create_trove_cat(
            (232, 456, "kde", "KDE", "User Interface :: Graphical :: KDE", True))
        self.create_trove_cat((310, 456, "cocoa", "Cocoa (MacOS X)",
                               "User Interface :: Graphical :: Cocoa (MacOS X)", True))
        self.create_trove_cat(
            (476, 456, "ui_tabletpc", "TabletPC", "User Interface :: Graphical :: TabletPC", True))
        self.create_trove_cat((314, 456, "handhelds", "Handheld/Mobile/PDA",
                               "User Interface :: Graphical :: Handheld/Mobile/PDA", True))
        self.create_trove_cat(
            (462, 225, "ui_groupingdesc", "Grouping and Descriptive Categories (UI)",
             "User Interface :: Grouping and Descriptive Categories (UI)", True))
        self.create_trove_cat(
            (466, 462, "ui_meta_3d", "Project is a 3D engine",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a 3D engine", True))
        self.create_trove_cat(
            (464, 462, "ui_meta_template", "Project is a templating system",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a templating system", True))
        self.create_trove_cat(
            (463, 462, "ui_meta_system", "Project is a user interface (UI) system",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a user interface (UI) system",
             True))
        self.create_trove_cat(
            (465, 462, "ui_meta_windowmanager", "Project is a window manager",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a window manager", True))
        self.create_trove_cat(
            (467, 462, "ui_meta_toolkit", "Project is a graphics toolkit",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a graphics toolkit", True))
        self.create_trove_cat(
            (468, 462, "ui_meta_remotecontrol", "Project is a remote control application",
             "User Interface :: Grouping and Descriptive Categories (UI) :: Project is a remote control application",
             True))
        self.create_trove_cat(
            (237, 225, "web", "Web-based", "User Interface :: Web-based", True))
        self.create_trove_cat((238, 225, "daemon", "Non-interactive (Daemon)",
                               "User Interface :: Non-interactive (Daemon)", True))
        self.create_trove_cat(
            (457, 225, "textual_ui", "Textual", "User Interface :: Textual", True))
        self.create_trove_cat((460, 457, "ui_consoleterm", "Console/Terminal",
                               "User Interface :: Textual :: Console/Terminal", True))
        self.create_trove_cat(
            (459, 457, "ui_commandline", "Command-line", "User Interface :: Textual :: Command-line", True))
        self.create_trove_cat(
            (225, 0, "environment", "User Interface", "User Interface", True))
        self.create_trove_cat(
            (461, 225, "ui_plugins", "Plugins", "User Interface :: Plugins", True))
        self.create_trove_cat(
            (583, 461, "eclipse_plugins", "Eclipse", "User Interface :: Plugins :: Eclipse", True))
        self.create_trove_cat(
            (458, 225, "ui_toolkit", "Toolkits/Libraries", "User Interface :: Toolkits/Libraries", True))
        self.create_trove_cat((495, 458, "ui_othertoolkit", "Other toolkit",
                               "User Interface :: Toolkits/Libraries :: Other toolkit", True))
        self.create_trove_cat((493, 458, "ui_motif", "Motif/LessTif",
                               "User Interface :: Toolkits/Libraries :: Motif/LessTif", True))
        self.create_trove_cat((491, 458, "ui_crystalspace", "Crystal Space",
                               "User Interface :: Toolkits/Libraries :: Crystal Space", True))
        self.create_trove_cat((489, 458, "ui_clanlib", "ClanLib",
                               "User Interface :: Toolkits/Libraries :: ClanLib", True))
        self.create_trove_cat(
            (516, 500, "db_group_objmap", "Project is a relational object mapper",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a relational object mapper",  # nopep8
             True))
        self.create_trove_cat(
            (487, 458, "ui_ggi", "GGI", "User Interface :: Toolkits/Libraries :: GGI", True))
        self.create_trove_cat((485, 458, "ui_directx", "DirectX",
                               "User Interface :: Toolkits/Libraries :: DirectX", True))
        self.create_trove_cat((483, 458, "ui_svgalib", "SVGAlib",
                               "User Interface :: Toolkits/Libraries :: SVGAlib", True))
        self.create_trove_cat((481, 458, "ui_wxwidgets", "wxWidgets",
                               "User Interface :: Toolkits/Libraries :: wxWidgets", True))
        self.create_trove_cat(
            (511, 500, "db_group_mgmt", "Project is a database management tool",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a database management tool",  # nopep8
             True))
        self.create_trove_cat(
            (479, 458, "ui_qt", "Qt", "User Interface :: Toolkits/Libraries :: Qt", True))
        self.create_trove_cat(
            (477, 458, "ui_gtk", "GTK+", "User Interface :: Toolkits/Libraries :: GTK+", True))
        self.create_trove_cat(
            (513, 500, "db_group_netdbms", "Project is a network-based DBMS (database system)",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a network-based DBMS (database system)",  # nopep8
             True))
        self.create_trove_cat(
            (228, 458, "newt", "Newt", "User Interface :: Toolkits/Libraries :: Newt", True))
        self.create_trove_cat((227, 458, "curses", "Curses/Ncurses",
                               "User Interface :: Toolkits/Libraries :: Curses/Ncurses", True))
        self.create_trove_cat(
            (515, 500, "db_group_conv", "Project is a database conversion tool",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a database conversion tool",  # nopep8
             True))
        self.create_trove_cat(
            (478, 458, "ui_tk", "Tk", "User Interface :: Toolkits/Libraries :: Tk", True))
        self.create_trove_cat(
            (480, 458, "ui_sdl", "SDL", "User Interface :: Toolkits/Libraries :: SDL", True))
        self.create_trove_cat((33, 28, "postoffice", "Post-Office",
                               "Topic :: Communications :: Email :: Post-Office", True))
        self.create_trove_cat(
            (514, 500, "db_group_propfmt", "Project is a tool for a proprietary database file format",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a tool for a proprietary database file format",  # nopep8
             True))
        self.create_trove_cat(
            (482, 458, "ui_aalib", "AAlib", "User Interface :: Toolkits/Libraries :: AAlib", True))
        self.create_trove_cat(
            (484, 458, "ui_fltk", "FLTK", "User Interface :: Toolkits/Libraries :: FLTK", True))
        self.create_trove_cat(
            (512, 500, "db_group_filedbms", "Project is a file-based DBMS (database system)",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a file-based DBMS (database system)",  # nopep8
             True))
        self.create_trove_cat(
            (486, 458, "ui_plib", "Plib", "User Interface :: Toolkits/Libraries :: Plib", True))
        self.create_trove_cat(
            (488, 458, "ui_glide", "Glide", "User Interface :: Toolkits/Libraries :: Glide", True))
        self.create_trove_cat(
            (510, 500, "db_group_api", "Project is a database abstraction layer (API)",
             "Database Environment :: Grouping and Descriptive Categories (DB) :: Project is a database abstraction layer (API)",  # nopep8
             True))
        self.create_trove_cat(
            (490, 458, "ui_glut", "GLUT", "User Interface :: Toolkits/Libraries :: GLUT", True))
        self.create_trove_cat((492, 458, "ui_allegro", "Allegro",
                               "User Interface :: Toolkits/Libraries :: Allegro", True))
        self.create_trove_cat(
            (500, 496, "db_grouping", "Grouping and Descriptive Categories (DB)",
             "Database Environment :: Grouping and Descriptive Categories (DB)", True))
        self.create_trove_cat(
            (494, 458, "ui_quartz", "Quartz", "User Interface :: Toolkits/Libraries :: Quartz", True))
        self.create_trove_cat(
            (456, 225, "graphical_ui", "Graphical", "User Interface :: Graphical", True))
        self.create_trove_cat(
            (276, 274, "french", "French", "Translations :: French", True))
        self.create_trove_cat((473, 456, "ui_carbon", "Carbon (Mac OS X)",
                               "User Interface :: Graphical :: Carbon (Mac OS X)", True))
        self.create_trove_cat(
            (535, 1, "by_industrysector", "by Industry or Sector",
             "Intended Audience :: by Industry or Sector", False))
        self.create_trove_cat((364, 535, "legalindustry", "Legal Industry",
                               "Intended Audience :: by Industry or Sector :: Legal Industry", False))
        self.create_trove_cat(
            (353, 274, "ukrainian", "Ukrainian", "Translations :: Ukrainian", True))
        self.create_trove_cat(
            (330, 274, "dutch", "Dutch", "Translations :: Dutch", True))
        self.create_trove_cat(
            (343, 274, "persian", "Persian", "Translations :: Persian", True))
        self.create_trove_cat(
            (344, 274, "polish", "Polish", "Translations :: Polish", True))
        self.create_trove_cat(
            (455, 274, "irish_gaelic", "Irish Gaelic", "Translations :: Irish Gaelic", True))
        self.create_trove_cat(
            (413, 274, "lithuanian", "Lithuanian", "Translations :: Lithuanian", True))
        self.create_trove_cat(
            (414, 274, "albanian", "Albanian", "Translations :: Albanian", True))
        self.create_trove_cat(
            (415, 274, "malagasy", "Malagasy", "Translations :: Malagasy", True))
        self.create_trove_cat(
            (416, 274, "mongolian", "Mongolian", "Translations :: Mongolian", True))
        self.create_trove_cat(
            (417, 274, "maltese", "Maltese", "Translations :: Maltese", True))
        self.create_trove_cat(
            (380, 274, "slovenian", "Slovene", "Translations :: Slovene", True))
        self.create_trove_cat(
            (374, 274, "icelandic", "Icelandic", "Translations :: Icelandic", True))
        self.create_trove_cat(
            (376, 274, "macedonian", "Macedonian", "Translations :: Macedonian", True))
        self.create_trove_cat(
            (377, 274, "latin", "Latin", "Translations :: Latin", True))
        self.create_trove_cat(
            (375, 274, "latvian", "Latvian", "Translations :: Latvian", True))
        self.create_trove_cat(
            (373, 274, "czech", "Czech", "Translations :: Czech", True))
        self.create_trove_cat(
            (369, 274, "afrikaans", "Afrikaans", "Translations :: Afrikaans", True))
        self.create_trove_cat(
            (357, 274, "finnish", "Finnish", "Translations :: Finnish", True))
        self.create_trove_cat(
            (186, 160, "visualbasic", "Visual Basic", "Programming Language :: Visual Basic", True))
        self.create_trove_cat((505, 499, "db_pear", "PHP Pear::DB",
                               "Database Environment :: Database API :: PHP Pear::DB", True))
        self.create_trove_cat((507, 499, "db_api_xml", "XML-based",
                               "Database Environment :: Database API :: XML-based", True))
        self.create_trove_cat((509, 499, "db_api_other", "Other API",
                               "Database Environment :: Database API :: Other API", True))
        self.create_trove_cat(
            (532, 497, "db_net_hsql", "HSQL", "Database Environment :: Network-based DBMS :: HSQL", True))
        self.create_trove_cat(
            (547, 160, "applescript", "AppleScript", "Programming Language :: AppleScript", True))
        self.create_trove_cat(
            (173, 160, "modula", "Modula", "Programming Language :: Modula", True))
        self.create_trove_cat(
            (337, 274, "italian", "Italian", "Translations :: Italian", True))
        self.create_trove_cat(
            (333, 274, "hebrew", "Hebrew", "Translations :: Hebrew", True))
        self.create_trove_cat(
            (331, 274, "esperanto", "Esperanto", "Translations :: Esperanto", True))
        self.create_trove_cat(
            (329, 274, "catalan", "Catalan", "Translations :: Catalan", True))
        self.create_trove_cat(
            (327, 274, "bengali", "Bengali", "Translations :: Bengali", True))
        self.create_trove_cat(
            (332, 274, "greek", "Greek", "Translations :: Greek", True))
        self.create_trove_cat(
            (341, 274, "marathi", "Marathi", "Translations :: Marathi", True))
        self.create_trove_cat(
            (355, 274, "vietnamese", "Vietnamese", "Translations :: Vietnamese", True))
        self.create_trove_cat(
            (275, 274, "english", "English", "Translations :: English", True))
        self.create_trove_cat(
            (345, 274, "portuguese", "Portuguese", "Translations :: Portuguese", True))
        self.create_trove_cat(
            (171, 160, "logo", "Logo", "Programming Language :: Logo", True))
        self.create_trove_cat(
            (502, 499, "db_api_jdbc", "JDBC", "Database Environment :: Database API :: JDBC", True))
        self.create_trove_cat((504, 499, "db_api_perldbi", "Perl DBI/DBD",
                               "Database Environment :: Database API :: Perl DBI/DBD", True))
        self.create_trove_cat(
            (274, 0, "natlanguage", "Translations", "Translations", True))
        self.create_trove_cat((506, 499, "db_python", "Python Database API",
                               "Database Environment :: Database API :: Python Database API", True))
        self.create_trove_cat((526, 497, "db_net_oracle", "Oracle",
                               "Database Environment :: Network-based DBMS :: Oracle", True))
        self.create_trove_cat((524, 497, "db_net_mysql", "MySQL",
                               "Database Environment :: Network-based DBMS :: MySQL", True))
        self.create_trove_cat((525, 497, "db_net_pgsql", "PostgreSQL (pgsql)",
                               "Database Environment :: Network-based DBMS :: PostgreSQL (pgsql)", True))
        self.create_trove_cat((527, 497, "db_net_ibmdb2", "IBM DB2",
                               "Database Environment :: Network-based DBMS :: IBM DB2", True))
        self.create_trove_cat((529, 497, "db_net_sybase", "Sybase",
                               "Database Environment :: Network-based DBMS :: Sybase", True))
        self.create_trove_cat((531, 497, "db_net_sqlite", "SQLite",
                               "Database Environment :: Network-based DBMS :: SQLite", True))
        self.create_trove_cat(
            (533, 497, "db_net_other", "Other network-based DBMS",
             "Database Environment :: Network-based DBMS :: Other network-based DBMS", True))
        self.create_trove_cat(
            (497, 496, "db_networkbased", "Network-based DBMS",
             "Database Environment :: Network-based DBMS", True))
        self.create_trove_cat(
            (426, 199, "os_emu_api", "Emulation and API Compatibility",
             "Operating System :: Emulation and API Compatibility", True))
        self.create_trove_cat((311, 236, "macos9", "Apple Mac OS Classic",
                               "Operating System :: Other Operating Systems :: Apple Mac OS Classic", True))
        self.create_trove_cat(
            (224, 236, "beos", "BeOS", "Operating System :: Other Operating Systems :: BeOS", True))
        self.create_trove_cat(
            (215, 236, "msdos", "MS-DOS", "Operating System :: Other Operating Systems :: MS-DOS", True))
        self.create_trove_cat(
            (421, 236, "mswin_95", "Win95", "Operating System :: Other Operating Systems :: Win95", True))
        self.create_trove_cat((508, 499, "db_api_sql", "SQL-based",
                               "Database Environment :: Database API :: SQL-based", True))
        self.create_trove_cat(
            (499, 496, "db_api", "Database API", "Database Environment :: Database API", True))
        self.create_trove_cat(
            (378, 274, "serbian", "Serbian", "Translations :: Serbian", True))
        self.create_trove_cat(
            (379, 274, "slovak", "Slovak", "Translations :: Slovak", True))
        self.create_trove_cat(
            (371, 274, "chinesetraditional", "Chinese (Traditional)", "Translations :: Chinese (Traditional)", True))
        self.create_trove_cat(
            (410, 274, "belarusian", "Belarusian", "Translations :: Belarusian", True))
        self.create_trove_cat(
            (411, 274, "estonian", "Estonian", "Translations :: Estonian", True))
        self.create_trove_cat(
            (412, 274, "galician", "Galician", "Translations :: Galician", True))
        self.create_trove_cat(
            (34, 33, "pop3", "POP3", "Topic :: Communications :: Email :: Post-Office :: POP3", True))
        self.create_trove_cat(
            (35, 33, "imap", "IMAP", "Topic :: Communications :: Email :: Post-Office :: IMAP", True))
        self.create_trove_cat(
            (29, 28, "filters", "Filters", "Topic :: Communications :: Email :: Filters", True))
        self.create_trove_cat((30, 28, "listservers", "Mailing List Servers",
                               "Topic :: Communications :: Email :: Mailing List Servers", True))
        self.create_trove_cat(
            (597, 80, "card_games", "Card Games", "Topic :: Games/Entertainment :: Card Games", True))
        self.create_trove_cat(
            (63, 18, "editors", "Text Editors", "Topic :: Text Editors", True))
        self.create_trove_cat((366, 535, "religion", "Religion",
                               "Intended Audience :: by Industry or Sector :: Religion", False))
        self.create_trove_cat(
            (534, 1, "by_enduser", "by End-User Class", "Intended Audience :: by End-User Class", False))
        self.create_trove_cat(
            (528, 497, "db_net_firebird", "Firebird/InterBase",
             "Database Environment :: Network-based DBMS :: Firebird/InterBase", True))
        self.create_trove_cat((3, 534, "developers", "Developers",
                               "Intended Audience :: by End-User Class :: Developers", False))
        self.create_trove_cat(
            (530, 497, "db_net_mssql", "Microsoft SQL Server",
             "Database Environment :: Network-based DBMS :: Microsoft SQL Server", True))
        self.create_trove_cat((2, 534, "endusers", "End Users/Desktop",
                               "Intended Audience :: by End-User Class :: End Users/Desktop", False))
        self.create_trove_cat(
            (498, 496, "db_filebased", "File-based DBMS", "Database Environment :: File-based DBMS", True))
        self.create_trove_cat((537, 534, "enduser_qa", "Quality Engineers",
                               "Intended Audience :: by End-User Class :: Quality Engineers", False))
        self.create_trove_cat(
            (5, 1, "other", "Other Audience", "Intended Audience :: Other Audience", False))
        self.create_trove_cat(
            (517, 498, "db_file_dbm", "Berkeley/Sleepycat/Gdbm (DBM)",
             "Database Environment :: File-based DBMS :: Berkeley/Sleepycat/Gdbm (DBM)", True))
        self.create_trove_cat(
            (358, 6, "inactive", "7 - Inactive", "Development Status :: 7 - Inactive", False))
        self.create_trove_cat((520, 498, "db_file_palm", "PalmOS PDB",
                               "Database Environment :: File-based DBMS :: PalmOS PDB", True))
        self.create_trove_cat(
            (523, 498, "db_file_other", "Other file-based DBMS",
             "Database Environment :: File-based DBMS :: Other file-based DBMS", True))
        self.create_trove_cat(
            (165, 160, "cpp", "C++", "Programming Language :: C++", True))
        self.create_trove_cat(
            (163, 160, "ada", "Ada", "Programming Language :: Ada", True))
        self.create_trove_cat(
            (328, 274, "bulgarian", "Bulgarian", "Translations :: Bulgarian", True))
        self.create_trove_cat(
            (546, 274, "swahili", "Swahili", "Translations :: Swahili", True))
        self.create_trove_cat(
            (348, 274, "swedish", "Swedish", "Translations :: Swedish", True))
        self.create_trove_cat(
            (350, 274, "telugu", "Telugu", "Translations :: Telugu", True))
        self.create_trove_cat(
            (162, 160, "assembly", "Assembly", "Programming Language :: Assembly", True))
        self.create_trove_cat(
            (164, 160, "c", "C", "Programming Language :: C", True))
        self.create_trove_cat(
            (161, 160, "apl", "APL", "Programming Language :: APL", True))
        self.create_trove_cat(
            (267, 160, "zope", "Zope", "Programming Language :: Zope", True))
        self.create_trove_cat(
            (264, 160, "erlang", "Erlang", "Programming Language :: Erlang", True))
        self.create_trove_cat(
            (263, 160, "euphoria", "Euphoria", "Programming Language :: Euphoria", True))
        self.create_trove_cat(
            (183, 160, "php", "PHP", "Programming Language :: PHP", True))
        self.create_trove_cat(
            (182, 160, "tcl", "Tcl", "Programming Language :: Tcl", True))
        self.create_trove_cat(
            (181, 160, "smalltalk", "Smalltalk", "Programming Language :: Smalltalk", True))
        self.create_trove_cat(
            (180, 160, "simula", "Simula", "Programming Language :: Simula", True))
        self.create_trove_cat(
            (174, 160, "objectivec", "Objective C", "Programming Language :: Objective C", True))
        self.create_trove_cat((560, 160, "xsl", "XSL (XSLT/XPath/XSL-FO)",
                               "Programming Language :: XSL (XSLT/XPath/XSL-FO)", True))
        self.create_trove_cat(
            (293, 160, "ruby", "Ruby", "Programming Language :: Ruby", True))
        self.create_trove_cat(
            (265, 160, "Delphi", "Delphi/Kylix", "Programming Language :: Delphi/Kylix", True))
        self.create_trove_cat(
            (281, 160, "REBOL", "REBOL", "Programming Language :: REBOL", True))
        self.create_trove_cat((454, 160, "ocaml", "OCaml (Objective Caml)",
                               "Programming Language :: OCaml (Objective Caml)", True))
        self.create_trove_cat(
            (453, 160, "vb_net", "Visual Basic .NET", "Programming Language :: Visual Basic .NET", True))
        self.create_trove_cat(
            (452, 160, "visual_foxpro", "Visual FoxPro", "Programming Language :: Visual FoxPro", True))
        self.create_trove_cat(
            (451, 160, "haskell", "Haskell", "Programming Language :: Haskell", True))
        self.create_trove_cat(
            (450, 160, "lua", "Lua", "Programming Language :: Lua", True))
        self.create_trove_cat(
            (280, 160, "JavaScript", "JavaScript", "Programming Language :: JavaScript", True))
        self.create_trove_cat(
            (262, 160, "coldfusion", "Cold Fusion", "Programming Language :: Cold Fusion", True))
        self.create_trove_cat(
            (261, 160, "xbasic", "XBasic", "Programming Language :: XBasic", True))
        self.create_trove_cat(
            (258, 160, "objectpascal", "Object Pascal", "Programming Language :: Object Pascal", True))
        self.create_trove_cat(
            (539, 160, "proglang_basic", "BASIC", "Programming Language :: BASIC", True))
        self.create_trove_cat(
            (543, 160, "groovy", "Groovy", "Programming Language :: Groovy", True))
        self.create_trove_cat(
            (545, 160, "proglang_labview", "LabVIEW", "Programming Language :: LabVIEW", True))
        self.create_trove_cat(
            (548, 160, "vbscript", "VBScript", "Programming Language :: VBScript", True))
        self.create_trove_cat(
            (552, 160, "d_proglang", "D", "Programming Language :: D", True))
        self.create_trove_cat(
            (551, 160, "vhdl_verilog", "VHDL/Verilog", "Programming Language :: VHDL/Verilog", True))
        self.create_trove_cat(
            (549, 160, "proglang_lpc", "LPC", "Programming Language :: LPC", True))
        self.create_trove_cat(
            (544, 160, "yacc", "Yacc", "Programming Language :: Yacc", True))
        self.create_trove_cat(
            (352, 274, "turkish", "Turkish", "Translations :: Turkish", True))
        self.create_trove_cat(
            (354, 274, "urdu", "Urdu", "Translations :: Urdu", True))
        self.create_trove_cat(
            (160, 0, "language", "Programming Language", "Programming Language", True))
        self.create_trove_cat(
            (542, 160, "emacs_lisp", "Emacs-Lisp", "Programming Language :: Emacs-Lisp", True))
        self.create_trove_cat(
            (540, 160, "clisp", "Common Lisp", "Programming Language :: Common Lisp", True))
        self.create_trove_cat(
            (12, 6, "mature", "6 - Mature", "Development Status :: 6 - Mature", False))
        self.create_trove_cat(
            (538, 160, "awk", "AWK", "Programming Language :: AWK", True))
        self.create_trove_cat(
            (572, 160, "jsp", "JSP", "Programming Language :: JSP", True))
        self.create_trove_cat(
            (172, 160, "ml", "Standard ML", "Programming Language :: Standard ML", True))
        self.create_trove_cat(
            (255, 160, "progress", "PROGRESS", "Programming Language :: PROGRESS", True))
        self.create_trove_cat(
            (254, 160, "plsql", "PL/SQL", "Programming Language :: PL/SQL", True))
        self.create_trove_cat(
            (242, 160, "scheme", "Scheme", "Programming Language :: Scheme", True))
        self.create_trove_cat(
            (624, 160, "idl", "IDL", "Programming Language :: IDL", True))
        self.create_trove_cat(
            (198, 160, "java", "Java", "Programming Language :: Java", True))
        self.create_trove_cat(
            (589, 160, "asp_dot_net", "ASP.NET", "Programming Language :: ASP.NET", True))
        self.create_trove_cat(
            (608, 160, "mumps", "MUMPS", "Programming Language :: MUMPS", True))
        self.create_trove_cat(
            (541, 160, "dylan", "Dylan", "Programming Language :: Dylan", True))
        self.create_trove_cat(
            (573, 160, "s_slash_r", "S/R", "Programming Language :: S/R", True))
        self.create_trove_cat(
            (584, 160, "actionscript", "ActionScript", "Programming Language :: ActionScript", True))
        self.create_trove_cat(
            (168, 160, "forth", "Forth", "Programming Language :: Forth", True))
        self.create_trove_cat(
            (334, 274, "hindi", "Hindi", "Translations :: Hindi", True))
        self.create_trove_cat(
            (336, 274, "indonesian", "Indonesian", "Translations :: Indonesian", True))
        self.create_trove_cat((521, 498, "db_file_flat", "Flat-file",
                               "Database Environment :: File-based DBMS :: Flat-file", True))
        self.create_trove_cat((519, 498, "db_file_xbase", "xBase",
                               "Database Environment :: File-based DBMS :: xBase", True))
        self.create_trove_cat(
            (338, 274, "javanese", "Javanese", "Translations :: Javanese", True))
        self.create_trove_cat((518, 498, "db_msaccess", "Microsoft Access",
                               "Database Environment :: File-based DBMS :: Microsoft Access", True))
        self.create_trove_cat(
            (522, 498, "db_file_proprietary", "Proprietary file format",
             "Database Environment :: File-based DBMS :: Proprietary file format", True))
        self.create_trove_cat(
            (496, 0, "root_database", "Database Environment", "Database Environment", True))
        self.create_trove_cat(
            (501, 499, "db_api_odbc", "ODBC", "Database Environment :: Database API :: ODBC", True))
        self.create_trove_cat(
            (503, 499, "db_adodb", "ADOdb", "Database Environment :: Database API :: ADOdb", True))
        self.create_trove_cat(
            (340, 274, "malay", "Malay", "Translations :: Malay", True))
        self.create_trove_cat(
            (6, 0, "developmentstatus", "Development Status", "Development Status", False))
        self.create_trove_cat(
            (342, 274, "norwegian", "Norwegian", "Translations :: Norwegian", True))
        self.create_trove_cat(
            (381, 274, "portuguesebrazilian", "Brazilian Portuguese", "Translations :: Brazilian Portuguese", True))
        self.create_trove_cat(
            (382, 274, "chinesesimplified", "Chinese (Simplified)", "Translations :: Chinese (Simplified)", True))
        self.create_trove_cat(
            (356, 274, "danish", "Danish", "Translations :: Danish", True))
        self.create_trove_cat(
            (346, 274, "panjabi", "Panjabi", "Translations :: Panjabi", True))
        self.create_trove_cat(
            (370, 274, "bosnian", "Bosnian", "Translations :: Bosnian", True))
        self.create_trove_cat(
            (279, 274, "german", "German", "Translations :: German", True))
        self.create_trove_cat(
            (278, 274, "japanese", "Japanese", "Translations :: Japanese", True))
        self.create_trove_cat(
            (277, 274, "spanish", "Spanish", "Translations :: Spanish", True))
        self.create_trove_cat((11, 6, "production", "5 - Production/Stable",
                               "Development Status :: 5 - Production/Stable", False))
        self.create_trove_cat(
            (10, 6, "beta", "4 - Beta", "Development Status :: 4 - Beta", False))
        self.create_trove_cat(
            (9, 6, "alpha", "3 - Alpha", "Development Status :: 3 - Alpha", False))
        self.create_trove_cat(
            (8, 6, "prealpha", "2 - Pre-Alpha", "Development Status :: 2 - Pre-Alpha", False))
        self.create_trove_cat(
            (7, 6, "planning", "1 - Planning", "Development Status :: 1 - Planning", False))
        self.create_trove_cat(
            (295, 274, "russian", "Russian", "Translations :: Russian", True))
        self.create_trove_cat(
            (326, 274, "arabic", "Arabic", "Translations :: Arabic", True))
        self.create_trove_cat(
            (335, 274, "hungarian", "Hungarian", "Translations :: Hungarian", True))
        self.create_trove_cat((13, 0, "license", "License", "License", False))
        self.create_trove_cat(
            (14, 13, "osi", "OSI-Approved Open Source", "License :: OSI-Approved Open Source", False))
        self.create_trove_cat((388, 14, "osl", "Open Software License",
                               "License :: OSI-Approved Open Source :: Open Software License", False))
        self.create_trove_cat((321, 14, "motosoto", "Motosoto License",
                               "License :: OSI-Approved Open Source :: Motosoto License", False))
        self.create_trove_cat(
            (325, 14, "attribut", "Attribution Assurance License",
             "License :: OSI-Approved Open Source :: Attribution Assurance License", False))
        self.create_trove_cat(
            (304, 14, "mpl", "Mozilla Public License 1.0 (MPL)",
             "License :: OSI-Approved Open Source :: Mozilla Public License 1.0 (MPL)", False))
        self.create_trove_cat(
            (398, 14, "plan9", "Lucent Public License (Plan9)",
             "License :: OSI-Approved Open Source :: Lucent Public License (Plan9)", False))
        self.create_trove_cat(
            (187, 14, "bsd", "BSD License", "License :: OSI-Approved Open Source :: BSD License", False))
        self.create_trove_cat(
            (393, 14, "historical", "Historical Permission Notice and Disclaimer",
             "License :: OSI-Approved Open Source :: Historical Permission Notice and Disclaimer", False))
        self.create_trove_cat(
            (395, 14, "real", "RealNetworks Public Source License V1.0",
             "License :: OSI-Approved Open Source :: RealNetworks Public Source License V1.0", False))
        self.create_trove_cat((396, 14, "rpl", "Reciprocal Public License",
                               "License :: OSI-Approved Open Source :: Reciprocal Public License", False))
        self.create_trove_cat((392, 14, "eiffel2", "Eiffel Forum License V2.0",
                               "License :: OSI-Approved Open Source :: Eiffel Forum License V2.0", False))
        self.create_trove_cat(
            (320, 14, "w3c", "W3C License", "License :: OSI-Approved Open Source :: W3C License", False))
        self.create_trove_cat((400, 14, "frameworx", "Frameworx Open License",
                               "License :: OSI-Approved Open Source :: Frameworx Open License", False))
        self.create_trove_cat(
            (194, 14, "python", "Python License (CNRI Python License)",
             "License :: OSI-Approved Open Source :: Python License (CNRI Python License)", False))
        self.create_trove_cat((296, 14, "apache", "Apache Software License",
                               "License :: OSI-Approved Open Source :: Apache Software License", False))
        self.create_trove_cat(
            (298, 14, "sissl", "Sun Industry Standards Source License (SISSL)",
             "License :: OSI-Approved Open Source :: Sun Industry Standards Source License (SISSL)", False))
        self.create_trove_cat(
            (196, 13, "other", "Other/Proprietary License", "License :: Other/Proprietary License", False))
        self.create_trove_cat(
            (197, 13, "publicdomain", "Public Domain", "License :: Public Domain", False))
        self.create_trove_cat((301, 14, "nokia", "Nokia Open Source License",
                               "License :: OSI-Approved Open Source :: Nokia Open Source License", False))
        self.create_trove_cat((319, 14, "eiffel", "Eiffel Forum License",
                               "License :: OSI-Approved Open Source :: Eiffel Forum License", False))
        self.create_trove_cat((318, 14, "sunpublic", "Sun Public License",
                               "License :: OSI-Approved Open Source :: Sun Public License", False))
        self.create_trove_cat((190, 14, "qpl", "Qt Public License (QPL)",
                               "License :: OSI-Approved Open Source :: Qt Public License (QPL)", False))
        self.create_trove_cat(
            (390, 14, "oclc", "OCLC Research Public License 2.0",
             "License :: OSI-Approved Open Source :: OCLC Research Public License 2.0", False))
        self.create_trove_cat(
            (407, 14, "nasalicense", "NASA Open Source Agreement",
             "License :: OSI-Approved Open Source :: NASA Open Source Agreement", False))
        self.create_trove_cat(
            (406, 14, "eclipselicense", "Eclipse Public License",
             "License :: OSI-Approved Open Source :: Eclipse Public License", False))
        self.create_trove_cat(
            (316, 14, "opengroup", "Open Group Test Suite License",
             "License :: OSI-Approved Open Source :: Open Group Test Suite License", False))
        self.create_trove_cat((300, 14, "jabber", "Jabber Open Source License",
                               "License :: OSI-Approved Open Source :: Jabber Open Source License", False))
        self.create_trove_cat(
            (297, 14, "vovida", "Vovida Software License 1.0",
             "License :: OSI-Approved Open Source :: Vovida Software License 1.0", False))
        self.create_trove_cat((324, 14, "afl", "Academic Free License (AFL)",
                               "License :: OSI-Approved Open Source :: Academic Free License (AFL)", False))
        self.create_trove_cat(
            (189, 14, "psfl", "Python Software Foundation License",
             "License :: OSI-Approved Open Source :: Python Software Foundation License", False))
        self.create_trove_cat(
            (193, 14, "rscpl", "Ricoh Source Code Public License",
             "License :: OSI-Approved Open Source :: Ricoh Source Code Public License", False))
        self.create_trove_cat((17, 14, "artistic", "Artistic License",
                               "License :: OSI-Approved Open Source :: Artistic License", False))
        self.create_trove_cat(
            (389, 14, "sybase", "Sybase Open Watcom Public License",
             "License :: OSI-Approved Open Source :: Sybase Open Watcom Public License", False))
        self.create_trove_cat(
            (391, 14, "wxwindows", "wxWindows Library Licence",
             "License :: OSI-Approved Open Source :: wxWindows Library Licence", False))
        self.create_trove_cat((397, 14, "entessa", "Entessa Public License",
                               "License :: OSI-Approved Open Source :: Entessa Public License", False))
        self.create_trove_cat(
            (16, 14, "lgpl", "GNU Library or Lesser General Public License (LGPL)",
             "License :: OSI-Approved Open Source :: GNU Library or Lesser General Public License (LGPL)", False))
        self.create_trove_cat(
            (629, 14, "educom", "Educational Community License",
             "License :: OSI-Approved Open Source :: Educational Community License", False))
        self.create_trove_cat(
            (15, 14, "gpl", "GNU General Public License (GPL)",
             "License :: OSI-Approved Open Source :: GNU General Public License (GPL)", False))
        self.create_trove_cat((191, 14, "ibm", "IBM Public License",
                               "License :: OSI-Approved Open Source :: IBM Public License", False))
        self.create_trove_cat(
            (192, 14, "cvw", "MITRE Collaborative Virtual Workspace License (CVW)",
             "License :: OSI-Approved Open Source :: MITRE Collaborative Virtual Workspace License (CVW)", False))
        self.create_trove_cat((299, 14, "iosl", "Intel Open Source License",
                               "License :: OSI-Approved Open Source :: Intel Open Source License", False))
        self.create_trove_cat((399, 14, "php-license", "PHP License",
                               "License :: OSI-Approved Open Source :: PHP License", False))
        self.create_trove_cat(
            (188, 14, "mit", "MIT License", "License :: OSI-Approved Open Source :: MIT License", False))
        self.create_trove_cat(
            (405, 14, "public102", "Lucent Public License Version 1.02",
             "License :: OSI-Approved Open Source :: Lucent Public License Version 1.02", False))
        self.create_trove_cat(
            (404, 14, "fair", "Fair License", "License :: OSI-Approved Open Source :: Fair License", False))
        self.create_trove_cat(
            (403, 14, "datagrid", "EU DataGrid Software License",
             "License :: OSI-Approved Open Source :: EU DataGrid Software License", False))
        self.create_trove_cat((307, 14, "ibmcpl", "Common Public License",
                               "License :: OSI-Approved Open Source :: Common Public License", False))
        self.create_trove_cat(
            (402, 14, "cua", "CUA Office Public License Version 1.0",
             "License :: OSI-Approved Open Source :: CUA Office Public License Version 1.0", False))
        self.create_trove_cat((401, 14, "apache2", "Apache License V2.0",
                               "License :: OSI-Approved Open Source :: Apache License V2.0", False))
        self.create_trove_cat((394, 14, "nausite", "Naumen Public License",
                               "License :: OSI-Approved Open Source :: Naumen Public License", False))
        self.create_trove_cat((317, 14, "xnet", "X.Net License",
                               "License :: OSI-Approved Open Source :: X.Net License", False))
        self.create_trove_cat((195, 14, "zlib", "zlib/libpng License",
                               "License :: OSI-Approved Open Source :: zlib/libpng License", False))
        self.create_trove_cat(
            (323, 14, "ncsa", "University of Illinois/NCSA Open Source License",
             "License :: OSI-Approved Open Source :: University of Illinois/NCSA Open Source License", False))
        self.create_trove_cat((322, 14, "zope", "Zope Public License",
                               "License :: OSI-Approved Open Source :: Zope Public License", False))
        self.create_trove_cat((302, 14, "sleepycat", "Sleepycat License",
                               "License :: OSI-Approved Open Source :: Sleepycat License", False))
        self.create_trove_cat(
            (303, 14, "nethack", "Nethack General Public License",
             "License :: OSI-Approved Open Source :: Nethack General Public License", False))
        self.create_trove_cat((306, 14, "apsl", "Apple Public Source License",
                               "License :: OSI-Approved Open Source :: Apple Public Source License", False))
        self.create_trove_cat(
            (305, 14, "mpl11", "Mozilla Public License 1.1 (MPL 1.1)",
             "License :: OSI-Approved Open Source :: Mozilla Public License 1.1 (MPL 1.1)", False))
        self.create_trove_cat((628, 14, "adaptive", "Adaptive Public License",
                               "License :: OSI-Approved Open Source :: Adaptive Public License", False))
        self.create_trove_cat(
            (630, 14, "cddl", "Common Development and Distribution License",
             "License :: OSI-Approved Open Source :: Common Development and Distribution License", False))
        self.create_trove_cat(
            (631, 14, "catosl", "Computer Associates Trusted Open Source License",
             "License :: OSI-Approved Open Source :: Computer Associates Trusted Open Source License", False))
        self.create_trove_cat(
            (199, 0, "os", "Operating System", "Operating System", True))
        self.create_trove_cat((429, 426, "fink", "Fink (Mac OS X)",
                               "Operating System :: Emulation and API Compatibility :: Fink (Mac OS X)", True))
        self.create_trove_cat((427, 426, "cygwin", "Cygwin (MS Windows)",
                               "Operating System :: Emulation and API Compatibility :: Cygwin (MS Windows)", True))
        self.create_trove_cat(
            (428, 426, "dosemu", "DOSEMU", "Operating System :: Emulation and API Compatibility :: DOSEMU", True))
        self.create_trove_cat(
            (430, 426, "wine", "WINE", "Operating System :: Emulation and API Compatibility :: WINE", True))
        self.create_trove_cat((431, 426, "emx", "EMX (OS/2 and MS-DOS)",
                               "Operating System :: Emulation and API Compatibility :: EMX (OS/2 and MS-DOS)", True))
        self.create_trove_cat(
            (445, 426, "mingw_msys", "MinGW/MSYS (MS Windows)",
             "Operating System :: Emulation and API Compatibility :: MinGW/MSYS (MS Windows)", True))
        self.create_trove_cat(
            (315, 199, "pdasystems", "Handheld/Embedded Operating Systems",
             "Operating System :: Handheld/Embedded Operating Systems", True))
        self.create_trove_cat(
            (222, 315, "wince", "WinCE", "Operating System :: Handheld/Embedded Operating Systems :: WinCE", True))
        self.create_trove_cat(
            (223, 315, "palmos", "PalmOS", "Operating System :: Handheld/Embedded Operating Systems :: PalmOS", True))
        self.create_trove_cat(
            (441, 315, "ecos", "eCos", "Operating System :: Handheld/Embedded Operating Systems :: eCos", True))
        self.create_trove_cat(
            (
            443, 315, "vxworks", "VxWorks", "Operating System :: Handheld/Embedded Operating Systems :: VxWorks", True))  # nopep8
        self.create_trove_cat((444, 315, "symbianos", "SymbianOS",
                               "Operating System :: Handheld/Embedded Operating Systems :: SymbianOS", True))
        self.create_trove_cat(
            (442, 315, "qnx", "QNX", "Operating System :: Handheld/Embedded Operating Systems :: QNX", True))
        self.create_trove_cat(
            (
            440, 315, "uclinux", "uClinux", "Operating System :: Handheld/Embedded Operating Systems :: uClinux", True))  # nopep8
        self.create_trove_cat(
            (418, 199, "modern_oses", "Modern (Vendor-Supported) Desktop Operating Systems",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems", True))
        self.create_trove_cat((420, 418, "mswin_2000", "Win2K",
                               "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Win2K",
                               True))
        self.create_trove_cat(
            (207, 418, "sun", "Solaris",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Solaris", True))
        self.create_trove_cat(
            (201, 418, "linux", "Linux",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Linux", True))
        self.create_trove_cat((205, 418, "openbsd", "OpenBSD",
                               "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: OpenBSD",
                               True))
        self.create_trove_cat((203, 418, "freebsd", "FreeBSD",
                               "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: FreeBSD",
                               True))
        self.create_trove_cat(
            (204, 418, "netbsd", "NetBSD",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: NetBSD", True))
        self.create_trove_cat(
            (309, 418, "macosx", "OS X",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: OS X", True))
        self.create_trove_cat(
            (419, 418, "mswin_xp", "WinXP",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: WinXP", True))
        self.create_trove_cat((236, 199, "other", "Other Operating Systems",
                               "Operating System :: Other Operating Systems", True))
        self.create_trove_cat(
            (206, 236, "bsdos", "BSD/OS", "Operating System :: Other Operating Systems :: BSD/OS", True))
        self.create_trove_cat(
            (634, 236, "console-platforms", "Console-based Platforms",
             "Operating System :: Other Operating Systems :: Console-based Platforms", True))
        self.create_trove_cat((637, 634, "sega-dreamcast", "Sega Dreamcast",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Sega Dreamcast",  # nopep8
                               True))
        self.create_trove_cat((635, 634, "xbox", "Microsoft Xbox",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Microsoft Xbox",  # nopep8
                               True))
        self.create_trove_cat((636, 634, "sony-ps2", "Sony Playstation 2",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Sony Playstation 2",  # nopep8
                               True))
        self.create_trove_cat(
            (422, 236, "mswin_98", "Win98", "Operating System :: Other Operating Systems :: Win98", True))
        self.create_trove_cat((425, 422, "mswin_98_osr2", "Win98 OSR2",
                               "Operating System :: Other Operating Systems :: Win98 :: Win98 OSR2", True))
        self.create_trove_cat(
            (424, 236, "mswin_me", "WinME", "Operating System :: Other Operating Systems :: WinME", True))
        self.create_trove_cat(
            (423, 236, "mswin_nt", "WinNT", "Operating System :: Other Operating Systems :: WinNT", True))
        self.create_trove_cat(
            (220, 236, "os2", "IBM OS/2", "Operating System :: Other Operating Systems :: IBM OS/2", True))
        self.create_trove_cat(
            (211, 236, "irix", "SGI IRIX", "Operating System :: Other Operating Systems :: SGI IRIX", True))
        self.create_trove_cat(
            (210, 236, "aix", "IBM AIX", "Operating System :: Other Operating Systems :: IBM AIX", True))
        self.create_trove_cat(
            (212, 236, "other", "Other", "Operating System :: Other Operating Systems :: Other", True))
        self.create_trove_cat(
            (446, 236, "openvms", "OpenVMS", "Operating System :: Other Operating Systems :: OpenVMS", True))
        self.create_trove_cat(
            (434, 236, "amigaos", "AmigaOS", "Operating System :: Other Operating Systems :: AmigaOS", True))
        self.create_trove_cat(
            (448, 236, "mswin_server2003", "Microsoft Windows Server 2003",
             "Operating System :: Other Operating Systems :: Microsoft Windows Server 2003", True))
        self.create_trove_cat(
            (447, 236, "morphos", "MorphOS", "Operating System :: Other Operating Systems :: MorphOS", True))
        self.create_trove_cat(
            (209, 236, "hpux", "HP-UX", "Operating System :: Other Operating Systems :: HP-UX", True))
        self.create_trove_cat(
            (208, 236, "sco", "SCO", "Operating System :: Other Operating Systems :: SCO", True))
        self.create_trove_cat(
            (240, 236, "gnuhurd", "GNU Hurd", "Operating System :: Other Operating Systems :: GNU Hurd", True))
        self.create_trove_cat((217, 236, "win31", "Microsoft Windows 3.x",
                               "Operating System :: Other Operating Systems :: Microsoft Windows 3.x", True))
        self.create_trove_cat(
            (432, 199, "os_groups", "Grouping and Descriptive Categories",
             "Operating System :: Grouping and Descriptive Categories", True))
        self.create_trove_cat((218, 432, "win95", "32-bit MS Windows (95/98)",
                               "Operating System :: Grouping and Descriptive Categories :: 32-bit MS Windows (95/98)",
                               True))
        self.create_trove_cat(
            (439, 432, "os_projectdistrospecific", "Project is OS Distribution-Specific",
             "Operating System :: Grouping and Descriptive Categories :: Project is OS Distribution-Specific", True))
        self.create_trove_cat(
            (449, 432, "eightbit_oses", "Classic 8-bit Operating Systems (Apple, Atari, Commodore, etc.)",
             "Operating System :: Grouping and Descriptive Categories :: Classic 8-bit Operating Systems (Apple, Atari, Commodore, etc.)",  # nopep8
             True))
        self.create_trove_cat(
            (436, 432, "os_portable", "OS Portable (Source code to work with many OS platforms)",
             "Operating System :: Grouping and Descriptive Categories :: OS Portable (Source code to work with many OS platforms)",  # nopep8
             True))
        self.create_trove_cat(
            (438, 432, "os_projectdistro", "Project is an Operating System Distribution",
             "Operating System :: Grouping and Descriptive Categories :: Project is an Operating System Distribution",
             True))
        self.create_trove_cat(
            (235, 432, "independent", "OS Independent (Written in an interpreted language)",
             "Operating System :: Grouping and Descriptive Categories :: OS Independent (Written in an interpreted language)",  # nopep8
             True))
        self.create_trove_cat(
            (200, 432, "posix", "All POSIX (Linux/BSD/UNIX-like OSes)",
             "Operating System :: Grouping and Descriptive Categories :: All POSIX (Linux/BSD/UNIX-like OSes)", True))
        self.create_trove_cat(
            (219, 432, "winnt", "32-bit MS Windows (NT/2000/XP)",
             "Operating System :: Grouping and Descriptive Categories :: 32-bit MS Windows (NT/2000/XP)", True))
        self.create_trove_cat(
            (202, 432, "bsd", "All BSD Platforms (FreeBSD/NetBSD/OpenBSD/Apple Mac OS X)",
             "Operating System :: Grouping and Descriptive Categories :: All BSD Platforms (FreeBSD/NetBSD/OpenBSD/Apple Mac OS X)",  # nopep8
             True))
        self.create_trove_cat(
            (435, 432, "mswin_all32bit", "All 32-bit MS Windows (95/98/NT/2000/XP)",
             "Operating System :: Grouping and Descriptive Categories :: All 32-bit MS Windows (95/98/NT/2000/XP)",
             True))
        self.create_trove_cat(
            (437, 432, "os_projectkernel", "Project is an Operating System Kernel",
             "Operating System :: Grouping and Descriptive Categories :: Project is an Operating System Kernel", True))
        self.create_trove_cat(
            (64, 63, "emacs", "Emacs", "Topic :: Text Editors :: Emacs", True))
        self.create_trove_cat(
            (65, 63, "ide", "Integrated Development Environments (IDE)",
             "Topic :: Text Editors :: Integrated Development Environments (IDE)", True))
        self.create_trove_cat(
            (69, 63, "documentation", "Documentation", "Topic :: Text Editors :: Documentation", True))
        self.create_trove_cat(
            (70, 63, "wordprocessors", "Word Processors", "Topic :: Text Editors :: Word Processors", True))
        self.create_trove_cat(
            (285, 63, "textprocessing", "Text Processing", "Topic :: Text Editors :: Text Processing", True))
        self.create_trove_cat((611, 18, "formats_and_protocols",
                               "Formats and Protocols", "Topic :: Formats and Protocols", True))
        self.create_trove_cat((554, 611, "data_formats", "Data Formats",
                               "Topic :: Formats and Protocols :: Data Formats", True))
        self.create_trove_cat(
            (559, 554, "xml", "XML", "Topic :: Formats and Protocols :: Data Formats :: XML", True))
        self.create_trove_cat(
            (557, 554, "sgml", "SGML", "Topic :: Formats and Protocols :: Data Formats :: SGML", True))
        self.create_trove_cat(
            (555, 554, "docbook", "DocBook", "Topic :: Formats and Protocols :: Data Formats :: DocBook", True))
        self.create_trove_cat((556, 554, "html_xhtml", "HTML/XHTML",
                               "Topic :: Formats and Protocols :: Data Formats :: HTML/XHTML", True))
        self.create_trove_cat((558, 554, "tex_latex", "TeX/LaTeX",
                               "Topic :: Formats and Protocols :: Data Formats :: TeX/LaTeX", True))
        self.create_trove_cat(
            (612, 611, "protocols", "Protocols", "Topic :: Formats and Protocols :: Protocols", True))
        self.create_trove_cat(
            (616, 612, "xml_rpc", "XML-RPC", "Topic :: Formats and Protocols :: Protocols :: XML-RPC", True))
        self.create_trove_cat(
            (614, 612, "nntp", "NNTP", "Topic :: Formats and Protocols :: Protocols :: NNTP", True))
        self.create_trove_cat(
            (613, 612, "soap", "SOAP", "Topic :: Formats and Protocols :: Protocols :: SOAP", True))
        self.create_trove_cat(
            (615, 612, "rss", "RSS", "Topic :: Formats and Protocols :: Protocols :: RSS", True))
        self.create_trove_cat(
            (156, 18, "terminals", "Terminals", "Topic :: Terminals", True))
        self.create_trove_cat(
            (157, 156, "serial", "Serial", "Topic :: Terminals :: Serial", True))
        self.create_trove_cat(
            (158, 156, "virtual", "Terminal Emulators/X Terminals",
             "Topic :: Terminals :: Terminal Emulators/X Terminals", True))
        self.create_trove_cat(
            (159, 156, "telnet", "Telnet", "Topic :: Terminals :: Telnet", True))
        self.create_trove_cat(
            (20, 18, "communications", "Communications", "Topic :: Communications", True))
        self.create_trove_cat(
            (37, 20, "fido", "FIDO", "Topic :: Communications :: FIDO", True))
        self.create_trove_cat(
            (38, 20, "hamradio", "Ham Radio", "Topic :: Communications :: Ham Radio", True))
        self.create_trove_cat(
            (39, 20, "usenet", "Usenet News", "Topic :: Communications :: Usenet News", True))
        self.create_trove_cat(
            (40, 20, "internetphone", "Internet Phone", "Topic :: Communications :: Internet Phone", True))
        self.create_trove_cat(
            (36, 20, "fax", "Fax", "Topic :: Communications :: Fax", True))
        self.create_trove_cat(
            (22, 20, "chat", "Chat", "Topic :: Communications :: Chat", True))
        self.create_trove_cat((574, 22, "msn_messenger", "MSN Messenger",
                               "Topic :: Communications :: Chat :: MSN Messenger", True))
        self.create_trove_cat((26, 22, "aim", "AOL Instant Messenger",
                               "Topic :: Communications :: Chat :: AOL Instant Messenger", True))
        self.create_trove_cat((24, 22, "irc", "Internet Relay Chat",
                               "Topic :: Communications :: Chat :: Internet Relay Chat", True))
        self.create_trove_cat(
            (25, 22, "talk", "Unix Talk", "Topic :: Communications :: Chat :: Unix Talk", True))
        self.create_trove_cat(
            (23, 22, "icq", "ICQ", "Topic :: Communications :: Chat :: ICQ", True))
        self.create_trove_cat(
            (590, 20, "streaming_comms", "Streaming", "Topic :: Communications :: Streaming", True))
        self.create_trove_cat(
            (27, 20, "conferencing", "Conferencing", "Topic :: Communications :: Conferencing", True))
        self.create_trove_cat(
            (247, 20, "telephony", "Telephony", "Topic :: Communications :: Telephony", True))
        self.create_trove_cat(
            (251, 20, "filesharing", "File Sharing", "Topic :: Communications :: File Sharing", True))
        self.create_trove_cat((622, 251, "bittorrent", "BitTorrent",
                               "Topic :: Communications :: File Sharing :: BitTorrent", True))
        self.create_trove_cat(
            (286, 251, "gnutella", "Gnutella", "Topic :: Communications :: File Sharing :: Gnutella", True))
        self.create_trove_cat(
            (241, 251, "napster", "Napster", "Topic :: Communications :: File Sharing :: Napster", True))
        self.create_trove_cat(
            (21, 20, "bbs", "BBS", "Topic :: Communications :: BBS", True))
        self.create_trove_cat(
            (28, 20, "email", "Email", "Topic :: Communications :: Email", True))
        self.create_trove_cat((31, 28, "mua", "Email Clients (MUA)",
                               "Topic :: Communications :: Email :: Email Clients (MUA)", True))
        self.create_trove_cat((32, 28, "mta", "Mail Transport Agents",
                               "Topic :: Communications :: Email :: Mail Transport Agents", True))
        self.create_trove_cat(
            (234, 18, "other", "Other/Nonlisted Topic", "Topic :: Other/Nonlisted Topic", True))
        self.create_trove_cat(
            (129, 18, "office", "Office/Business", "Topic :: Office/Business", True))
        self.create_trove_cat(
            (576, 129, "enterprise", "Enterprise", "Topic :: Office/Business :: Enterprise", True))
        self.create_trove_cat(
            (579, 576, "crm", "CRM", "Topic :: Office/Business :: Enterprise :: CRM", True))
        self.create_trove_cat(
            (577, 576, "erp", "ERP", "Topic :: Office/Business :: Enterprise :: ERP", True))
        self.create_trove_cat(
            (578, 576, "olap", "OLAP", "Topic :: Office/Business :: Enterprise :: OLAP", True))
        self.create_trove_cat(
            (580, 576, "data_warehousing", "Data Warehousing",
             "Topic :: Office/Business :: Enterprise :: Data Warehousing", True))
        self.create_trove_cat(
            (587, 129, "time_tracking", "Time Tracking", "Topic :: Office/Business :: Time Tracking", True))
        self.create_trove_cat(
            (75, 129, "financial", "Financial", "Topic :: Office/Business :: Financial", True))
        self.create_trove_cat((76, 75, "accounting", "Accounting",
                               "Topic :: Office/Business :: Financial :: Accounting", True))
        self.create_trove_cat((77, 75, "investment", "Investment",
                               "Topic :: Office/Business :: Financial :: Investment", True))
        self.create_trove_cat((78, 75, "spreadsheet", "Spreadsheet",
                               "Topic :: Office/Business :: Financial :: Spreadsheet", True))
        self.create_trove_cat((79, 75, "pointofsale", "Point-Of-Sale",
                               "Topic :: Office/Business :: Financial :: Point-Of-Sale", True))
        self.create_trove_cat(
            (130, 129, "scheduling", "Scheduling", "Topic :: Office/Business :: Scheduling", True))
        self.create_trove_cat(
            (585, 130, "calendar", "Calendar", "Topic :: Office/Business :: Scheduling :: Calendar", True))
        self.create_trove_cat(
            (586, 130, "resource_booking", "Resource Booking",
             "Topic :: Office/Business :: Scheduling :: Resource Booking", True))
        self.create_trove_cat(
            (131, 129, "suites", "Office Suites", "Topic :: Office/Business :: Office Suites", True))
        self.create_trove_cat(
            (588, 129, "todo_lists", "To-Do Lists", "Topic :: Office/Business :: To-Do Lists", True))
        self.create_trove_cat(
            (607, 129, "project_management", "Project Management",
             "Topic :: Office/Business :: Project Management", True))
        self.create_trove_cat(
            (66, 18, "database", "Database", "Topic :: Database", True))
        self.create_trove_cat(
            (68, 66, "frontends", "Front-Ends", "Topic :: Database :: Front-Ends", True))
        self.create_trove_cat((67, 66, "engines", "Database Engines/Servers",
                               "Topic :: Database :: Database Engines/Servers", True))
        self.create_trove_cat(
            (43, 18, "security", "Security", "Topic :: Security", True))
        self.create_trove_cat(
            (44, 43, "cryptography", "Cryptography", "Topic :: Security :: Cryptography", True))
        self.create_trove_cat(
            (55, 18, "desktop", "Desktop Environment", "Topic :: Desktop Environment", True))
        self.create_trove_cat((56, 55, "windowmanagers", "Window Managers",
                               "Topic :: Desktop Environment :: Window Managers", True))
        self.create_trove_cat((59, 56, "enlightenment", "Enlightenment",
                               "Topic :: Desktop Environment :: Window Managers :: Enlightenment", True))
        self.create_trove_cat(
            (60, 59, "themes", "Themes", "Topic :: Desktop Environment :: Window Managers :: Enlightenment :: Themes",
             True))
        self.create_trove_cat((57, 55, "kde", "K Desktop Environment (KDE)",
                               "Topic :: Desktop Environment :: K Desktop Environment (KDE)", True))
        self.create_trove_cat(
            (61, 57, "themes", "Themes", "Topic :: Desktop Environment :: K Desktop Environment (KDE) :: Themes", True))  # nopep8
        self.create_trove_cat(
            (58, 55, "gnome", "Gnome", "Topic :: Desktop Environment :: Gnome", True))
        self.create_trove_cat((62, 55, "screensavers", "Screen Savers",
                               "Topic :: Desktop Environment :: Screen Savers", True))
        self.create_trove_cat(
            (80, 18, "games", "Games/Entertainment", "Topic :: Games/Entertainment", True))
        self.create_trove_cat((633, 80, "console-games", "Console-based Games",
                               "Topic :: Games/Entertainment :: Console-based Games", True))
        self.create_trove_cat(
            (287, 80, "boardgames", "Board Games", "Topic :: Games/Entertainment :: Board Games", True))
        self.create_trove_cat(
            (288, 80, "sidescrolling", "Side-Scrolling/Arcade Games",
             "Topic :: Games/Entertainment :: Side-Scrolling/Arcade Games", True))
        self.create_trove_cat(
            (81, 80, "realtimestrategy", "Real Time Strategy",
             "Topic :: Games/Entertainment :: Real Time Strategy", True))
        self.create_trove_cat(
            (82, 80, "firstpersonshooters", "First Person Shooters",
             "Topic :: Games/Entertainment :: First Person Shooters", True))
        self.create_trove_cat(
            (83, 80, "turnbasedstrategy", "Turn Based Strategy",
             "Topic :: Games/Entertainment :: Turn Based Strategy", True))
        self.create_trove_cat(
            (84, 80, "rpg", "Role-Playing", "Topic :: Games/Entertainment :: Role-Playing", True))
        self.create_trove_cat(
            (85, 80, "simulation", "Simulation", "Topic :: Games/Entertainment :: Simulation", True))
        self.create_trove_cat((86, 80, "mud", "Multi-User Dungeons (MUD)",
                               "Topic :: Games/Entertainment :: Multi-User Dungeons (MUD)", True))
        self.create_trove_cat(
            (268, 80, "Puzzles", "Puzzle Games", "Topic :: Games/Entertainment :: Puzzle Games", True))
        self.create_trove_cat(
            (88, 87, "finger", "Finger", "Topic :: Internet :: Finger", True))
        self.create_trove_cat((89, 87, "ftp", "File Transfer Protocol (FTP)",
                               "Topic :: Internet :: File Transfer Protocol (FTP)", True))
        self.create_trove_cat(
            (270, 87, "WAP", "WAP", "Topic :: Internet :: WAP", True))
        self.create_trove_cat(
            (90, 87, "www", "WWW/HTTP", "Topic :: Internet :: WWW/HTTP", True))
        self.create_trove_cat(
            (91, 90, "browsers", "Browsers", "Topic :: Internet :: WWW/HTTP :: Browsers", True))
        self.create_trove_cat((92, 90, "dynamic", "Dynamic Content",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content", True))
        self.create_trove_cat((95, 92, "messageboards", "Message Boards",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Message Boards", True))
        self.create_trove_cat((96, 92, "cgi", "CGI Tools/Libraries",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries", True))
        self.create_trove_cat((94, 92, "counters", "Page Counters",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Page Counters", True))
        self.create_trove_cat((93, 90, "indexing", "Indexing/Search",
                               "Topic :: Internet :: WWW/HTTP :: Indexing/Search", True))
        self.create_trove_cat((243, 90, "sitemanagement", "Site Management",
                               "Topic :: Internet :: WWW/HTTP :: Site Management", True))
        self.create_trove_cat((244, 243, "linkchecking", "Link Checking",
                               "Topic :: Internet :: WWW/HTTP :: Site Management :: Link Checking", True))
        self.create_trove_cat((250, 90, "httpservers", "HTTP Servers",
                               "Topic :: Internet :: WWW/HTTP :: HTTP Servers", True))
        self.create_trove_cat(
            (149, 87, "dns", "Name Service (DNS)", "Topic :: Internet :: Name Service (DNS)", True))
        self.create_trove_cat(
            (245, 87, "loganalysis", "Log Analysis", "Topic :: Internet :: Log Analysis", True))
        self.create_trove_cat(
            (45, 18, "development", "Software Development", "Topic :: Software Development", True))
        self.create_trove_cat(
            (563, 45, "modeling", "Modeling", "Topic :: Software Development :: Modeling", True))
        self.create_trove_cat(
            (46, 45, "build", "Build Tools", "Topic :: Software Development :: Build Tools", True))
        self.create_trove_cat(
            (575, 45, "testing", "Testing", "Topic :: Software Development :: Testing", True))
        self.create_trove_cat(
            (620, 45, "algorithms", "Algorithms", "Topic :: Software Development :: Algorithms", True))
        self.create_trove_cat(
            (621, 620, "genetic_algorithms", "Genetic Algorithms",
             "Topic :: Software Development :: Algorithms :: Genetic Algorithms", True))
        self.create_trove_cat(
            (606, 45, "frameworks", "Frameworks", "Topic :: Software Development :: Frameworks", True))
        self.create_trove_cat((564, 45, "documentation", "Documentation",
                               "Topic :: Software Development :: Documentation", True))
        self.create_trove_cat((562, 45, "swdev_oo", "Object Oriented",
                               "Topic :: Software Development :: Object Oriented", True))
        self.create_trove_cat((409, 45, "l10n", "L10N (Localization)",
                               "Topic :: Software Development :: L10N (Localization)", True))
        self.create_trove_cat((408, 45, "i18n", "I18N (Internationalization)",
                               "Topic :: Software Development :: I18N (Internationalization)", True))
        self.create_trove_cat((50, 45, "objectbrokering", "Object Brokering",
                               "Topic :: Software Development :: Object Brokering", True))
        self.create_trove_cat(
            (51, 50, "corba", "CORBA", "Topic :: Software Development :: Object Brokering :: CORBA", True))
        self.create_trove_cat((52, 45, "versioncontrol", "Version Control",
                               "Topic :: Software Development :: Version Control", True))
        self.create_trove_cat(
            (53, 52, "cvs", "CVS", "Topic :: Software Development :: Version Control :: CVS", True))
        self.create_trove_cat(
            (54, 52, "rcs", "RCS", "Topic :: Software Development :: Version Control :: RCS", True))
        self.create_trove_cat(
            (260, 52, "SCCS", "SCCS", "Topic :: Software Development :: Version Control :: SCCS", True))
        self.create_trove_cat((259, 45, "codegen", "Code Generators",
                               "Topic :: Software Development :: Code Generators", True))
        self.create_trove_cat(
            (47, 45, "debuggers", "Debuggers", "Topic :: Software Development :: Debuggers", True))
        self.create_trove_cat(
            (48, 45, "compilers", "Compilers", "Topic :: Software Development :: Compilers", True))
        self.create_trove_cat((49, 45, "interpreters", "Interpreters",
                               "Topic :: Software Development :: Interpreters", True))
        self.create_trove_cat((561, 45, "softwaredev_ui", "User Interfaces",
                               "Topic :: Software Development :: User Interfaces", True))
        self.create_trove_cat(
            (565, 45, "quality_assurance", "Quality Assurance",
             "Topic :: Software Development :: Quality Assurance", True))
        self.create_trove_cat(
            (570, 45, "case_tools", "CASE", "Topic :: Software Development :: CASE", True))
        self.create_trove_cat(
            (582, 45, "design", "Design", "Topic :: Software Development :: Design", True))
        self.create_trove_cat((593, 45, "cross_compilers", "Cross Compilers",
                               "Topic :: Software Development :: Cross Compilers", True))
        self.create_trove_cat(
            (603, 45, "profilers", "Profiling", "Topic :: Software Development :: Profiling", True))
        self.create_trove_cat((610, 45, "virtual_machines", "Virtual Machines",
                               "Topic :: Software Development :: Virtual Machines", True))
        self.create_trove_cat(
            (619, 45, "usability", "Usability", "Topic :: Software Development :: Usability", True))
        self.create_trove_cat(
            (581, 71, "library", "Library", "Topic :: Education :: Library", True))
        self.create_trove_cat(
            (604, 581, "opac", "OPAC", "Topic :: Education :: Library :: OPAC", True))
        self.create_trove_cat(
            (605, 581, "marc_and_metadata", "MARC and Book/Library Metadata",
             "Topic :: Education :: Library :: MARC and Book/Library Metadata", True))
        self.create_trove_cat(
            (132, 18, "religion", "Religion and Philosophy", "Topic :: Religion and Philosophy", True))
        self.create_trove_cat(
            (571, 132, "new_age", "New Age", "Topic :: Religion and Philosophy :: New Age", True))
        self.create_trove_cat(
            (136, 18, "system", "System", "Topic :: System", True))
        self.create_trove_cat(
            (638, 136, "storage", "Storage", "Topic :: System :: Storage", True))
        self.create_trove_cat((601, 638, "file_management", "File Management",
                               "Topic :: System :: Storage :: File Management", True))
        self.create_trove_cat(
            (19, 638, "archiving", "Archiving", "Topic :: System :: Storage :: Archiving", True))
        self.create_trove_cat((42, 19, "compression", "Compression",
                               "Topic :: System :: Storage :: Archiving :: Compression", True))
        self.create_trove_cat(
            (137, 19, "backup", "Backup", "Topic :: System :: Storage :: Archiving :: Backup", True))
        self.create_trove_cat(
            (41, 19, "packaging", "Packaging", "Topic :: System :: Storage :: Archiving :: Packaging", True))
        self.create_trove_cat(
            (294, 136, "shells", "System Shells", "Topic :: System :: System Shells", True))
        self.create_trove_cat(
            (74, 136, "emulators", "Emulators", "Topic :: System :: Emulators", True))
        self.create_trove_cat(
            (627, 136, "system_search", "Search", "Topic :: System :: Search", True))
        self.create_trove_cat(
            (257, 136, "softwaredist", "Software Distribution", "Topic :: System :: Software Distribution", True))
        self.create_trove_cat(
            (122, 113, "players", "Players", "Topic :: Multimedia :: Sound/Audio :: Players", True))
        self.create_trove_cat(
            (253, 136, "sysadministration", "Systems Administration",
             "Topic :: System :: Systems Administration", True))
        self.create_trove_cat(
            (289, 253, "authentication", "Authentication/Directory",
             "Topic :: System :: Systems Administration :: Authentication/Directory", True))
        self.create_trove_cat(
            (290, 289, "nis", "NIS", "Topic :: System :: Systems Administration :: Authentication/Directory :: NIS",
             True))
        self.create_trove_cat(
            (291, 289, "ldap", "LDAP", "Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP",
             True))
        self.create_trove_cat(
            (153, 136, "power", "Power (UPS)", "Topic :: System :: Power (UPS)", True))
        self.create_trove_cat(
            (150, 136, "networking", "Networking", "Topic :: System :: Networking", True))
        self.create_trove_cat(
            (566, 150, "wireless", "Wireless", "Topic :: System :: Networking :: Wireless", True))
        self.create_trove_cat(
            (151, 150, "firewalls", "Firewalls", "Topic :: System :: Networking :: Firewalls", True))
        self.create_trove_cat(
            (152, 150, "monitoring", "Monitoring", "Topic :: System :: Networking :: Monitoring", True))
        self.create_trove_cat((155, 152, "watchdog", "Hardware Watchdog",
                               "Topic :: System :: Networking :: Monitoring :: Hardware Watchdog", True))
        self.create_trove_cat(
            (148, 136, "logging", "Logging", "Topic :: System :: Logging", True))
        self.create_trove_cat(
            (592, 148, "log_rotation", "Log Rotation", "Topic :: System :: Logging :: Log Rotation", True))
        self.create_trove_cat((144, 136, "kernels", "Operating System Kernels",
                               "Topic :: System :: Operating System Kernels", True))
        self.create_trove_cat(
            (145, 144, "bsd", "BSD", "Topic :: System :: Operating System Kernels :: BSD", True))
        self.create_trove_cat(
            (239, 144, "gnuhurd", "GNU Hurd", "Topic :: System :: Operating System Kernels :: GNU Hurd", True))
        self.create_trove_cat(
            (143, 144, "linux", "Linux", "Topic :: System :: Operating System Kernels :: Linux", True))
        self.create_trove_cat(
            (147, 136, "setup", "Installation/Setup", "Topic :: System :: Installation/Setup", True))
        self.create_trove_cat(
            (146, 136, "hardware", "Hardware", "Topic :: System :: Hardware", True))
        self.create_trove_cat(
            (313, 146, "mainframe", "Mainframes", "Topic :: System :: Hardware :: Mainframes", True))
        self.create_trove_cat((312, 146, "smp", "Symmetric Multi-processing",
                               "Topic :: System :: Hardware :: Symmetric Multi-processing", True))
        self.create_trove_cat((292, 146, "drivers", "Hardware Drivers",
                               "Topic :: System :: Hardware :: Hardware Drivers", True))
        self.create_trove_cat(
            (138, 136, "benchmark", "Benchmark", "Topic :: System :: Benchmark", True))
        self.create_trove_cat(
            (139, 136, "boot", "Boot", "Topic :: System :: Boot", True))
        self.create_trove_cat(
            (140, 139, "init", "Init", "Topic :: System :: Boot :: Init", True))
        self.create_trove_cat(
            (141, 136, "clustering", "Clustering", "Topic :: System :: Clustering", True))
        self.create_trove_cat((308, 136, "distributed_computing",
                               "Distributed Computing", "Topic :: System :: Distributed Computing", True))
        self.create_trove_cat(
            (142, 136, "filesystems", "Filesystems", "Topic :: System :: Filesystems", True))
        self.create_trove_cat(
            (154, 18, "printing", "Printing", "Topic :: Printing", True))
        self.create_trove_cat(
            (87, 18, "internet", "Internet", "Topic :: Internet", True))
        self.create_trove_cat((118, 116, "cdripping", "CD Ripping",
                               "Topic :: Multimedia :: Sound/Audio :: CD Audio :: CD Ripping", True))
        self.create_trove_cat((119, 113, "audio-conversion", "Audio Conversion",
                               "Topic :: Multimedia :: Sound/Audio :: Audio Conversion", True))
        self.create_trove_cat(
            (120, 113, "editors", "Editors", "Topic :: Multimedia :: Sound/Audio :: Editors", True))
        self.create_trove_cat(
            (121, 113, "mixers", "Mixers", "Topic :: Multimedia :: Sound/Audio :: Mixers", True))
        self.create_trove_cat(
            (100, 99, "graphics", "Graphics", "Topic :: Multimedia :: Graphics", True))
        self.create_trove_cat((109, 100, "3dmodeling", "3D Modeling",
                               "Topic :: Multimedia :: Graphics :: 3D Modeling", True))
        self.create_trove_cat((110, 100, "3drendering", "3D Rendering",
                               "Topic :: Multimedia :: Graphics :: 3D Rendering", True))
        self.create_trove_cat((111, 100, "presentation", "Presentation",
                               "Topic :: Multimedia :: Graphics :: Presentation", True))
        self.create_trove_cat(
            (112, 100, "viewers", "Viewers", "Topic :: Multimedia :: Graphics :: Viewers", True))
        self.create_trove_cat(
            (101, 100, "capture", "Capture", "Topic :: Multimedia :: Graphics :: Capture", True))
        self.create_trove_cat((104, 101, "screencapture", "Screen Capture",
                               "Topic :: Multimedia :: Graphics :: Capture :: Screen Capture", True))
        self.create_trove_cat((103, 101, "cameras", "Digital Camera",
                               "Topic :: Multimedia :: Graphics :: Capture :: Digital Camera", True))
        self.create_trove_cat((102, 101, "scanners", "Scanners",
                               "Topic :: Multimedia :: Graphics :: Capture :: Scanners", True))
        self.create_trove_cat((105, 100, "conversion", "Graphics Conversion",
                               "Topic :: Multimedia :: Graphics :: Graphics Conversion", True))
        self.create_trove_cat(
            (106, 100, "editors", "Editors", "Topic :: Multimedia :: Graphics :: Editors", True))
        self.create_trove_cat((108, 106, "raster", "Raster-Based",
                               "Topic :: Multimedia :: Graphics :: Editors :: Raster-Based", True))
        self.create_trove_cat((107, 106, "vector", "Vector-Based",
                               "Topic :: Multimedia :: Graphics :: Editors :: Vector-Based", True))
        self.create_trove_cat(
            (97, 18, "scientific", "Scientific/Engineering", "Topic :: Scientific/Engineering", True))
        self.create_trove_cat(
            (609, 97, "molecular_science", "Molecular Science",
             "Topic :: Scientific/Engineering :: Molecular Science", True))
        self.create_trove_cat(
            (602, 97, "robotics", "Robotics", "Topic :: Scientific/Engineering :: Robotics", True))
        self.create_trove_cat((600, 97, "simulations", "Simulations",
                               "Topic :: Scientific/Engineering :: Simulations", True))
        self.create_trove_cat(
            (568, 97, "ecosystem_sciences", "Ecosystem Sciences",
             "Topic :: Scientific/Engineering :: Ecosystem Sciences", True))
        self.create_trove_cat(
            (386, 97, "interfaceengine", "Interface Engine/Protocol Translator",
             "Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator", True))
        self.create_trove_cat(
            (384, 97, "chemistry", "Chemistry", "Topic :: Scientific/Engineering :: Chemistry", True))
        self.create_trove_cat((252, 97, "bioinformatics", "Bio-Informatics",
                               "Topic :: Scientific/Engineering :: Bio-Informatics", True))
        self.create_trove_cat(
            (246, 97, "eda", "Electronic Design Automation (EDA)",
             "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)", True))
        self.create_trove_cat((135, 97, "visualization", "Visualization",
                               "Topic :: Scientific/Engineering :: Visualization", True))
        self.create_trove_cat(
            (134, 97, "astronomy", "Astronomy", "Topic :: Scientific/Engineering :: Astronomy", True))
        self.create_trove_cat((133, 97, "ai", "Artificial Intelligence",
                               "Topic :: Scientific/Engineering :: Artificial Intelligence", True))
        self.create_trove_cat(
            (591, 133, "intelligent_agents", "Intelligent Agents",
             "Topic :: Scientific/Engineering :: Artificial Intelligence :: Intelligent Agents", True))
        self.create_trove_cat((98, 97, "mathematics", "Mathematics",
                               "Topic :: Scientific/Engineering :: Mathematics", True))
        self.create_trove_cat((272, 97, "HMI", "Human Machine Interfaces",
                               "Topic :: Scientific/Engineering :: Human Machine Interfaces", True))
        self.create_trove_cat((266, 97, "medical", "Medical Science Apps.",
                               "Topic :: Scientific/Engineering :: Medical Science Apps.", True))
        self.create_trove_cat(
            (383, 97, "gis", "GIS", "Topic :: Scientific/Engineering :: GIS", True))
        self.create_trove_cat(
            (385, 97, "informationanalysis", "Information Analysis",
             "Topic :: Scientific/Engineering :: Information Analysis", True))
        self.create_trove_cat(
            (387, 97, "physics", "Physics", "Topic :: Scientific/Engineering :: Physics", True))
        self.create_trove_cat((567, 97, "earth_science", "Earth Sciences",
                               "Topic :: Scientific/Engineering :: Earth Sciences", True))
        self.create_trove_cat(
            (282, 18, "Sociology", "Sociology", "Topic :: Sociology", True))
        self.create_trove_cat(
            (284, 282, "Genealogy", "Genealogy", "Topic :: Sociology :: Genealogy", True))
        self.create_trove_cat(
            (283, 282, "History", "History", "Topic :: Sociology :: History", True))
        self.create_trove_cat(
            (71, 18, "education", "Education", "Topic :: Education", True))
        self.create_trove_cat(
            (73, 71, "testing", "Testing", "Topic :: Education :: Testing", True))
        self.create_trove_cat(
            (72, 71, "cai", "Computer Aided Instruction (CAI)",
             "Topic :: Education :: Computer Aided Instruction (CAI)", True))
        self.create_trove_cat((18, 0, "topic", "Topic", "Topic", True))
        self.create_trove_cat(
            (125, 99, "video", "Video", "Topic :: Multimedia :: Video", True))
        self.create_trove_cat((594, 125, "still_capture", "Still Capture",
                               "Topic :: Multimedia :: Video :: Still Capture", True))
        self.create_trove_cat(
            (596, 125, "codec", "Codec", "Topic :: Multimedia :: Video :: Codec", True))
        self.create_trove_cat(
            (127, 125, "video-conversion", "Video Conversion", "Topic :: Multimedia :: Video :: Video Conversion", True))
        self.create_trove_cat(
            (128, 125, "display", "Display", "Topic :: Multimedia :: Video :: Display", True))
        self.create_trove_cat(
            (256, 125, "nonlineareditor", "Non-Linear Editor",
             "Topic :: Multimedia :: Video :: Non-Linear Editor", True))
        self.create_trove_cat((595, 125, "special_effects", "Special Effects",
                               "Topic :: Multimedia :: Video :: Special Effects", True))
        self.create_trove_cat(
            (623, 125, "video_realtime", "Realtime Processing",
             "Topic :: Multimedia :: Video :: Realtime Processing", True))
        self.create_trove_cat((126, 125, "vidcapture", "Video Capture",
                               "Topic :: Multimedia :: Video :: Video Capture", True))
        self.create_trove_cat(
            (113, 99, "sound", "Sound/Audio", "Topic :: Multimedia :: Sound/Audio", True))
        self.create_trove_cat(
            (123, 122, "mp3", "MP3", "Topic :: Multimedia :: Sound/Audio :: Players :: MP3", True))
        self.create_trove_cat(
            (124, 113, "speech", "Speech", "Topic :: Multimedia :: Sound/Audio :: Speech", True))
        self.create_trove_cat(
            (114, 113, "analysis", "Analysis", "Topic :: Multimedia :: Sound/Audio :: Analysis", True))
        self.create_trove_cat((115, 113, "capture", "Capture/Recording",
                               "Topic :: Multimedia :: Sound/Audio :: Capture/Recording", True))
        self.create_trove_cat(
            (248, 113, "midi", "MIDI", "Topic :: Multimedia :: Sound/Audio :: MIDI", True))
        self.create_trove_cat((249, 113, "synthesis", "Sound Synthesis",
                               "Topic :: Multimedia :: Sound/Audio :: Sound Synthesis", True))
        self.create_trove_cat(
            (116, 113, "cdaudio", "CD Audio", "Topic :: Multimedia :: Sound/Audio :: CD Audio", True))
        self.create_trove_cat((117, 116, "cdplay", "CD Playing",
                               "Topic :: Multimedia :: Sound/Audio :: CD Audio :: CD Playing", True))
        self.create_trove_cat(
            (99, 18, "multimedia", "Multimedia", "Topic :: Multimedia", True))
        self.create_trove_cat((670, 14, "agpl", "Affero GNU Public License",
                               "License :: OSI-Approved Open Source :: Affero GNU Public License", True))
        self.create_trove_cat((862, 14, "lppl", "LaTeX Project Public License",
                               "License :: OSI-Approved Open Source :: LaTeX Project Public License", True))
        self.create_trove_cat((655, 432, "win64", "64-bit MS Windows",
                               "Operating System :: Grouping and Descriptive Categories :: 64-bit MS Windows", True))
        self.create_trove_cat(
            (657, 418, "vista", "Vista",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Vista", True))
        self.create_trove_cat(
            (851, 418, "win7", "Windows 7",
             "Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Windows 7", True))
        self.create_trove_cat(
            (
            728, 315, "android", "Android", "Operating System :: Handheld/Embedded Operating Systems :: Android", True))  # nopep8
        self.create_trove_cat((780, 315, "ios", "Apple iPhone",
                               "Operating System :: Handheld/Embedded Operating Systems :: Apple iPhone", True))
        self.create_trove_cat((863, 534, "architects", "Architects",
                               "Intended Audience :: by End-User Class :: Architects", False))
        self.create_trove_cat(
            (864, 534, "auditors", "Auditors", "Intended Audience :: by End-User Class :: Auditors", False))
        self.create_trove_cat(
            (865, 534, "testers", "Testers", "Intended Audience :: by End-User Class :: Testers", False))
        self.create_trove_cat((866, 534, "secpros", "Security Professionals",
                               "Intended Audience :: by End-User Class :: Security Professionals", False))
        self.create_trove_cat((867, 535, "secindustry", "Security",
                               "Intended Audience :: by Industry or Sector :: Security", False))
        session(M.TroveCategory).flush()

        for name in self.migrations:
            getattr(self, 'm__' + name)()
            session(M.TroveCategory).flush()

    def m__sync(self):
        self.create_trove_cat(
            (639, 14, "cpal", "Common Public Attribution License 1.0 (CPAL)",
             "License :: OSI-Approved Open Source :: Common Public Attribution License 1.0 (CPAL)"))
        self.create_trove_cat(
            (640, 99, "dvd", "DVD", "Topic :: Multimedia :: DVD"))
        self.create_trove_cat(
            (641, 576, "workflow", "Workflow", "Topic :: Office/Business :: Enterprise :: Workflow"))
        self.create_trove_cat((642, 292, "linuxdrivers", "Linux",
                               "Topic :: System :: Hardware :: Hardware Drivers :: Linux"))
        self.create_trove_cat(
            (643, 582, "uml", "UML", "Topic :: Software Development :: Design :: UML"))
        self.create_trove_cat(
            (644, 92, "cms", "CMS Systems", "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CMS Systems"))
        self.create_trove_cat(
            (645, 92, "blogging", "Blogging", "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Blogging"))
        self.create_trove_cat((646, 52, "subversion", "Subversion",
                               "Topic :: Software Development :: Version Control :: Subversion"))
        self.create_trove_cat((647, 612, "webservices", "Web Services",
                               "Topic :: Formats and Protocols :: Protocols :: Web Services"))
        self.create_trove_cat(
            (648, 554, "json", "JSON", "Topic :: Formats and Protocols :: Data Formats :: JSON"))
        self.create_trove_cat((649, 100, "imagegalleries", "Image Galleries",
                               "Topic :: Multimedia :: Graphics :: Image Galleries"))
        self.create_trove_cat(
            (650, 612, "ajax", "AJAX", "Topic :: Formats and Protocols :: Protocols :: AJAX"))
        self.create_trove_cat(
            (651, 92, "wiki", "Wiki", "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Wiki"))
        self.create_trove_cat((652, 45, "appservers", "Application Servers",
                               "Topic :: Software Development :: Application Servers"))
        self.create_trove_cat(
            (653, 20, "rssreaders", "RSS Feed Readers", "Topic :: Communications :: RSS Feed Readers"))
        self.create_trove_cat((654, 129, "ecommerce", "E-Commerce / Shopping",
                               "Topic :: Office/Business :: E-Commerce / Shopping"))
        self.create_trove_cat(
            (656, 99, "htpc", "Home Theater PC", "Topic :: Multimedia :: Home Theater PC"))
        self.create_trove_cat(
            (658, 22, "xmpp", "XMPP", "Topic :: Communications :: Chat :: XMPP"))
        self.create_trove_cat(
            (659, 576, "enterprisebpm", "Business Performance Management",
             "Topic :: Office/Business :: Enterprise :: Business Performance Management"))
        self.create_trove_cat(
            (660, 576, "enterprisebi", "Business Intelligence",
             "Topic :: Office/Business :: Enterprise :: Business Intelligence"))
        self.create_trove_cat(
            (661, 75, "budgetingandforecasting", "Budgeting and Forecasting",
             "Topic :: Office/Business :: Financial :: Budgeting and Forecasting"))
        self.create_trove_cat(
            (662, 497, "ingres", "Ingres", "Database Environment :: Network-based DBMS :: Ingres"))
        self.create_trove_cat(
            (663, 92, "socialnetworking", "Social Networking",
             "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Social Networking"))
        self.create_trove_cat(
            (664, 199, "virtualization", "Virtualization", "Operating System :: Virtualization"))
        self.create_trove_cat(
            (665, 664, "vmware", "VMware", "Operating System :: Virtualization :: VMware"))
        self.create_trove_cat(
            (666, 664, "xen", "Xen", "Operating System :: Virtualization :: Xen"))
        self.create_trove_cat(
            (667, 247, "voip", "VoIP", "Topic :: Communications :: Telephony :: VoIP"))
        self.create_trove_cat((668, 92, "ticketing", "Ticketing Systems",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Ticketing Systems"))
        self.create_trove_cat((669, 315, "blackberryos", "Blackberry RIM OS",
                               "Operating System :: Handheld/Embedded Operating Systems :: Blackberry RIM OS"))
        self.create_trove_cat((671, 14, "ms-pl", "Microsoft Public License",
                               "License :: OSI-Approved Open Source :: Microsoft Public License"))
        self.create_trove_cat(
            (672, 14, "ms-rl", "Microsoft Reciprocal License",
             "License :: OSI-Approved Open Source :: Microsoft Reciprocal License"))
        self.create_trove_cat((673, 576, "bsm", "Business Service Management",
                               "Topic :: Office/Business :: Enterprise :: Business Service Management"))
        self.create_trove_cat((674, 673, "servicesupport", "Service Support",
                               "Topic :: Office/Business :: Enterprise :: Business Service Management :: Service Support"))  # nopep8
        self.create_trove_cat(
            (675, 673, "serviceassurance", "Service Assurance",
             "Topic :: Office/Business :: Enterprise :: Business Service Management :: Service Assurance"))
        self.create_trove_cat(
            (676, 673, "serviceautomation", "Service Automation",
             "Topic :: Office/Business :: Enterprise :: Business Service Management :: Service Automation"))
        self.create_trove_cat((677, 14, "artisticv2", "Artistic License 2.0",
                               "License :: OSI-Approved Open Source :: Artistic License 2.0"))
        self.create_trove_cat(
            (678, 14, "boostlicense", "Boost Software License (BSL1.0)",
             "License :: OSI-Approved Open Source :: Boost Software License (BSL1.0)"))
        self.create_trove_cat(
            (681, 14, "isclicense", "ISC License", "License :: OSI-Approved Open Source :: ISC License"))
        self.create_trove_cat((682, 14, "multicslicense", "Multics License",
                               "License :: OSI-Approved Open Source :: Multics License"))
        self.create_trove_cat(
            (683, 14, "ntplicense", "NTP License", "License :: OSI-Approved Open Source :: NTP License"))
        self.create_trove_cat(
            (684, 14, "nposl3", "Non-Profit Open Software License 3.0 (Non-Profit OSL 3.0)",
             "License :: OSI-Approved Open Source :: Non-Profit Open Software License 3.0 (Non-Profit OSL 3.0)"))
        self.create_trove_cat(
            (685, 14, "rpl15", "Reciprocal Public License 1.5 (RPL1.5)",
             "License :: OSI-Approved Open Source :: Reciprocal Public License 1.5 (RPL1.5)"))
        self.create_trove_cat(
            (686, 14, "splicense2", "Simple Public License 2.0",
             "License :: OSI-Approved Open Source :: Simple Public License 2.0"))
        self.create_trove_cat(
            (687, 673, "cmdb", "Configuration Management Database (CMDB)",
             "Topic :: Office/Business :: Enterprise :: Business Service Management :: Configuration Management Database (CMDB)"))  # nopep8
        self.create_trove_cat(
            (688, 18, "mobileapps", "Mobile", "Topic :: Mobile"))
        self.create_trove_cat((689, 315, "winmobile", "Windows Mobile",
                               "Operating System :: Handheld/Embedded Operating Systems :: Windows Mobile"))
        self.create_trove_cat(
            (690, 315, "brew", "BREW (Binary Runtime Environment for Wireless)",
             "Operating System :: Handheld/Embedded Operating Systems :: BREW (Binary Runtime Environment for Wireless)"))  # nopep8
        self.create_trove_cat(
            (691, 315, "j2me", "J2ME (Java Platform, Micro Edition)",
             "Operating System :: Handheld/Embedded Operating Systems :: J2ME (Java Platform, Micro Edition)"))
        self.create_trove_cat(
            (692, 315, "maemo", "Maemo", "Operating System :: Handheld/Embedded Operating Systems :: Maemo"))
        self.create_trove_cat((693, 315, "limo", "LiMo (Linux Mobile)",
                               "Operating System :: Handheld/Embedded Operating Systems :: LiMo (Linux Mobile)"))
        self.create_trove_cat(
            (694, 160, "clean", "Clean", "Programming Language :: Clean"))
        self.create_trove_cat(
            (695, 160, "lasso", "Lasso", "Programming Language :: Lasso"))
        self.create_trove_cat(
            (696, 160, "turing", "Turing", "Programming Language :: Turing"))
        self.create_trove_cat(
            (697, 160, "glsl", "GLSL (OpenGL Shading Language)",
             "Programming Language :: GLSL (OpenGL Shading Language)"))
        self.create_trove_cat(
            (698, 160, "lazarus", "Lazarus", "Programming Language :: Lazarus"))
        self.create_trove_cat(
            (699, 160, "freepascal", "Free Pascal", "Programming Language :: Free Pascal"))
        self.create_trove_cat(
            (700, 160, "scriptol", "Scriptol", "Programming Language :: Scriptol"))
        self.create_trove_cat(
            (701, 160, "pl-i", "PL/I (Programming Language One)",
             "Programming Language :: PL/I (Programming Language One)"))
        self.create_trove_cat(
            (702, 160, "oz", "Oz", "Programming Language :: Oz"))
        self.create_trove_cat(
            (703, 160, "limbo", "Limbo", "Programming Language :: Limbo"))
        self.create_trove_cat(
            (704, 160, "scala", "Scala", "Programming Language :: Scala"))
        self.create_trove_cat(
            (705, 160, "blitzmax", "BlitzMax", "Programming Language :: BlitzMax"))
        self.create_trove_cat(
            (706, 160, "xbaseclipper", "XBase/Clipper", "Programming Language :: XBase/Clipper"))
        self.create_trove_cat(
            (707, 160, "curl", "Curl", "Programming Language :: Curl"))
        self.create_trove_cat(
            (708, 160, "flex", "Flex", "Programming Language :: Flex"))
        self.create_trove_cat(
            (709, 160, "mathematica", "Mathematica", "Programming Language :: Mathematica"))
        self.create_trove_cat(
            (710, 160, "visualdataflex", "Visual DataFlex", "Programming Language :: Visual DataFlex"))
        self.create_trove_cat(
            (711, 160, "fenix", "Fenix", "Programming Language :: Fenix"))
        self.create_trove_cat(
            (713, 456, "vexi", "Vexi", "User Interface :: Graphical :: Vexi"))
        self.create_trove_cat(
            (714, 160, "kaya", "Kaya", "Programming Language :: Kaya"))
        self.create_trove_cat((715, 160, "transcript-revolution",
                               "Transcript/Revolution", "Programming Language :: Transcript/Revolution"))
        self.create_trove_cat(
            (716, 160, "haXe", "haXe", "Programming Language :: haXe"))
        self.create_trove_cat(
            (717, 160, "proglangmeta", "Project is a programming language",
             "Programming Language :: Project is a programming language"))
        self.create_trove_cat((718, 634, "msxb360", "Microsoft Xbox 360",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Microsoft Xbox 360"))  # nopep8
        self.create_trove_cat((719, 634, "nintendogc", "Nintendo GameCube",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Nintendo GameCube"))  # nopep8
        self.create_trove_cat((720, 634, "nintendowii", "Nintendo Wii",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Nintendo Wii"))  # nopep8
        self.create_trove_cat((721, 634, "sonyps3", "Sony PlayStation 3",
                               "Operating System :: Other Operating Systems :: Console-based Platforms :: Sony PlayStation 3"))  # nopep8
        self.create_trove_cat(
            (722, 634, "sonypsp", "Sony PlayStation Portable (PSP)",
             "Operating System :: Other Operating Systems :: Console-based Platforms :: Sony PlayStation Portable (PSP)"))  # nopep8
        self.create_trove_cat(
            (723, 160, "scilab", "Scilab", "Programming Language :: Scilab"))
        self.create_trove_cat(
            (724, 160, "scicos", "Scicos", "Programming Language :: Scicos"))
        self.create_trove_cat((725, 534, "management", "Management",
                               "Intended Audience :: by End-User Class :: Management"))
        self.create_trove_cat(
            (726, 71, "edadministration", "Administration", "Topic :: Education :: Administration"))
        self.create_trove_cat(
            (727, 97, "mechcivileng", "Mechanical and Civil Engineering",
             "Topic :: Scientific/Engineering :: Mechanical and Civil Engineering"))
        self.create_trove_cat((729, 535, "audienceengineering", "Engineering",
                               "Intended Audience :: by Industry or Sector :: Engineering"))
        self.create_trove_cat(
            (730, 274, "basque", "Basque (Euskara)", "Translations :: Basque (Euskara)"))
        self.create_trove_cat(
            (731, 14, "classpath", "GNU General Public License with Classpath exception (Classpath::License)",
             "License :: OSI-Approved Open Source :: GNU General Public License with Classpath exception (Classpath::License)"))  # nopep8
        self.create_trove_cat(
            (732, 727, "caddcam", "Computer-aided technologies (CADD/CAM/CAE)",
             "Topic :: Scientific/Engineering :: Mechanical and Civil Engineering :: Computer-aided technologies (CADD/CAM/CAE)"))  # nopep8
        self.create_trove_cat((733, 576, "humanresources", "Human Resources",
                               "Topic :: Office/Business :: Enterprise :: Human Resources"))
        self.create_trove_cat(
            (734, 554, "mcml", "Media Center Markup Language (MCML)",
             "Topic :: Formats and Protocols :: Data Formats :: Media Center Markup Language (MCML)"))
        self.create_trove_cat(
            (735, 461, "nsis", "Nullsoft Scriptable Install System (NSIS)",
             "User Interface :: Plugins :: Nullsoft Scriptable Install System (NSIS)"))
        self.create_trove_cat(
            (736, 97, "scada", "SCADA", "Topic :: Scientific/Engineering :: SCADA"))
        self.create_trove_cat(
            (737, 461, "autohotkey", "AutoHotkey", "User Interface :: Plugins :: AutoHotkey"))
        self.create_trove_cat(
            (738, 160, "autoit", "AutoIt", "Programming Language :: AutoIt"))
        self.create_trove_cat((739, 132, "humanitarianism", "Humanitarianism",
                               "Topic :: Religion and Philosophy :: Humanitarianism"))
        self.create_trove_cat(
            (740, 129, "insurance", "Insurance", "Topic :: Office/Business :: Insurance"))
        self.create_trove_cat(
            (741, 97, "linguistics", "Linguistics", "Topic :: Scientific/Engineering :: Linguistics"))
        self.create_trove_cat(
            (742, 741, "machinetranslation", "Machine Translation",
             "Topic :: Scientific/Engineering :: Linguistics :: Machine Translation"))
        self.create_trove_cat(
            (743, 43, "antispam", "Anti-Spam", "Topic :: Security :: Anti-Spam"))
        self.create_trove_cat(
            (744, 43, "antivirus", "Anti-Virus", "Topic :: Security :: Anti-Virus"))
        self.create_trove_cat(
            (745, 43, "antimalware", "Anti-Malware", "Topic :: Security :: Anti-Malware"))
        self.create_trove_cat((746, 554, "autocaddxf", "AutoCAD DXF",
                               "Topic :: Formats and Protocols :: Data Formats :: AutoCAD DXF"))
        self.create_trove_cat(
            (747, 75, "billing", "Billing", "Topic :: Office/Business :: Financial :: Billing"))
        self.create_trove_cat(
            (748, 576, "processmanagement", "Business Process Management",
             "Topic :: Office/Business :: Enterprise :: Business Process Management"))
        self.create_trove_cat(
            (749, 136, "embedded", "Embedded systems", "Topic :: System :: Embedded systems"))
        self.create_trove_cat(
            (750, 456, "magicui", "Magic User Interface (MUI)",
             "User Interface :: Graphical :: Magic User Interface (MUI)"))
        self.create_trove_cat(
            (751, 237, "xul", "XUL", "User Interface :: Web-based :: XUL"))
        self.create_trove_cat(
            (752, 80, "flightsim", "Flight simulator", "Topic :: Games/Entertainment :: Flight simulator"))
        self.create_trove_cat(
            (753, 63, "vivim", "Vi/Vim", "Topic :: Text Editors :: Vi/Vim"))
        self.create_trove_cat(
            (754, 45, "sourceanalysis", "Source code analysis",
             "Topic :: Software Development :: Source code analysis"))
        self.create_trove_cat(
            (755, 45, "sourcebrowsing", "Source code browsing",
             "Topic :: Software Development :: Source code browsing"))
        self.create_trove_cat(
            (756, 576, "plm", "Product lifecycle management (PLM)",
             "Topic :: Office/Business :: Enterprise :: Product lifecycle management (PLM)"))
        self.create_trove_cat(
            (757, 274, "breton", "Breton", "Translations :: Breton"))
        self.create_trove_cat((758, 498, "db4o", "db4objects (db4o)",
                               "Database Environment :: File-based DBMS :: db4objects (db4o)"))
        self.create_trove_cat(
            (759, 497, "nexusdb", "NexusDB", "Database Environment :: Network-based DBMS :: NexusDB"))
        self.create_trove_cat(
            (760, 160, "prism", "Prism", "Programming Language :: Prism"))
        self.create_trove_cat(
            (761, 45, "collaborative", "Collaborative development tools",
             "Topic :: Software Development :: Collaborative development tools"))
        self.create_trove_cat((762, 91, "pluginsaddons", "Plugins and add-ons",
                               "Topic :: Internet :: WWW/HTTP :: Browsers :: Plugins and add-ons"))
        self.create_trove_cat(
            (763, 456, "winaero", "Windows Aero", "User Interface :: Graphical :: Windows Aero"))
        self.create_trove_cat((764, 45, "agile", "Agile development tools",
                               "Topic :: Software Development :: Agile development tools"))
        self.create_trove_cat((765, 535, "agriculture", "Agriculture",
                               "Intended Audience :: by Industry or Sector :: Agriculture"))
        self.create_trove_cat(
            (766, 100, "animation", "Animation", "Topic :: Multimedia :: Graphics :: Animation"))
        self.create_trove_cat(
            (767, 45, "assemblers", "Assemblers", "Topic :: Software Development :: Assemblers"))
        self.create_trove_cat((768, 535, "automotive", "Automotive",
                               "Intended Audience :: by Industry or Sector :: Automotive"))
        self.create_trove_cat((769, 554, "CSV", "Comma-separated values (CSV)",
                               "Topic :: Formats and Protocols :: Data Formats :: Comma-separated values (CSV)"))
        self.create_trove_cat(
            (770, 45, "softdevlibraries", "Libraries", "Topic :: Software Development :: Libraries"))
        self.create_trove_cat((771, 45, "sourcereview", "Source code review",
                               "Topic :: Software Development :: Source code review"))
        self.create_trove_cat(
            (772, 80, "hobbies", "Hobbies", "Topic :: Games/Entertainment :: Hobbies"))
        self.create_trove_cat(
            (773, 772, "collectionmanage", "Collection management",
             "Topic :: Games/Entertainment :: Hobbies :: Collection management"))
        self.create_trove_cat(
            (774, 80, "multiplayer", "Multiplayer", "Topic :: Games/Entertainment :: Multiplayer"))
        self.create_trove_cat(
            (775, 80, "mmorpg", "MMORPG", "Topic :: Games/Entertainment :: MMORPG"))
        self.create_trove_cat(
            (776, 97, "mapping", "Mapping", "Topic :: Scientific/Engineering :: Mapping"))
        self.create_trove_cat(
            (777, 776, "gps", "GPS (Global Positioning System)",
             "Topic :: Scientific/Engineering :: Mapping :: GPS (Global Positioning System)"))
        self.create_trove_cat(
            (778, 43, "passwordmanage", "Password manager", "Topic :: Security :: Password manager"))
        self.create_trove_cat(
            (779, 315, "linksyswrt54g", "Linksys WRT54G series",
             "Operating System :: Handheld/Embedded Operating Systems :: Linksys WRT54G series"))
        self.create_trove_cat((781, 576, "medhealth", "Medical/Healthcare",
                               "Topic :: Office/Business :: Enterprise :: Medical/Healthcare"))
        self.create_trove_cat(
            (782, 45, "bined", "Binary editors", "Topic :: Software Development :: Binary editors"))
        self.create_trove_cat(
            (783, 99, "mmcatalog", "Cataloguing", "Topic :: Multimedia :: Cataloguing"))
        self.create_trove_cat(
            (784, 113, "composition", "Composition", "Topic :: Multimedia :: Sound/Audio :: Composition"))
        self.create_trove_cat(
            (785, 772, "cooking", "Cooking", "Topic :: Games/Entertainment :: Hobbies :: Cooking"))
        self.create_trove_cat(
            (786, 136, "cron", "Cron and scheduling", "Topic :: System :: Cron and scheduling"))
        self.create_trove_cat(
            (787, 638, "recovery", "Data recovery", "Topic :: System :: Storage :: Data recovery"))
        self.create_trove_cat(
            (788, 87, "otherfile", "Other file transfer protocol",
             "Topic :: Internet :: Other file transfer protocol"))
        self.create_trove_cat((789, 581, "digpreserve", "Digital preservation",
                               "Topic :: Education :: Library :: Digital preservation"))
        self.create_trove_cat((790, 251, "directconnect", "Direct Connect",
                               "Topic :: Communications :: File Sharing :: Direct Connect"))
        self.create_trove_cat(
            (791, 129, "dtp", "Desktop Publishing", "Topic :: Office/Business :: Desktop Publishing"))
        self.create_trove_cat(
            (792, 580, "etl", "ETL", "Topic :: Office/Business :: Enterprise :: Data Warehousing :: ETL"))
        self.create_trove_cat(
            (793, 55, "fonts", "Fonts", "Topic :: Desktop Environment :: Fonts"))
        self.create_trove_cat(
            (794, 80, "gameframeworks", "Game development framework",
             "Topic :: Games/Entertainment :: Game development framework"))
        self.create_trove_cat((795, 100, "handrec", "Handwriting recognition",
                               "Topic :: Multimedia :: Graphics :: Handwriting recognition"))
        self.create_trove_cat(
            (796, 136, "homeauto", "Home Automation", "Topic :: System :: Home Automation"))
        self.create_trove_cat(
            (797, 63, "translation", "Computer Aided Translation (CAT)",
             "Topic :: Text Editors :: Computer Aided Translation (CAT)"))
        self.create_trove_cat(
            (798, 136, "osdistro", "OS distribution", "Topic :: System :: OS distribution"))
        self.create_trove_cat(
            (799, 798, "livecd", "Live CD", "Topic :: System :: OS distribution :: Live CD"))
        self.create_trove_cat((800, 497, "lotusnotes", "Lotus Notes/Domino",
                               "Database Environment :: Network-based DBMS :: Lotus Notes/Domino"))
        self.create_trove_cat(
            (801, 160, "lotusscript", "LotusScript", "Programming Language :: LotusScript"))
        self.create_trove_cat((802, 133, "machinelearning", "Machine Learning",
                               "Topic :: Scientific/Engineering :: Artificial Intelligence :: Machine Learning"))
        self.create_trove_cat((803, 106, "metadata", "Metadata editors",
                               "Topic :: Multimedia :: Graphics :: Editors :: Metadata editors"))
        self.create_trove_cat(
            (804, 236, "riscos", "RISC OS", "Operating System :: Other Operating Systems :: RISC OS"))
        self.create_trove_cat(
            (805, 282, "politics", "Politics", "Topic :: Social sciences :: Politics"))
        self.create_trove_cat(
            (806, 80, "sports", "Sports", "Topic :: Games/Entertainment :: Sports"))
        self.create_trove_cat(
            (807, 282, "psychology", "Psychology", "Topic :: Social sciences :: Psychology"))
        self.create_trove_cat(
            (808, 458, "ogre3d", "Ogre3D", "User Interface :: Toolkits/Libraries :: Ogre3D"))
        self.create_trove_cat(
            (809, 45, "orm", "ORM (Object-relational mapping)",
             "Topic :: Software Development :: ORM (Object-relational mapping)"))
        self.create_trove_cat((810, 575, "perftest", "Performance Testing",
                               "Topic :: Software Development :: Testing :: Performance Testing"))
        self.create_trove_cat((811, 75, "personalfinance", "Personal finance",
                               "Topic :: Office/Business :: Financial :: Personal finance"))
        self.create_trove_cat((812, 499, "pearmdb2", "PHP Pear::MDB2",
                               "Database Environment :: Database API :: PHP Pear::MDB2"))
        self.create_trove_cat(
            (813, 461, "intellij", "IntelliJ", "User Interface :: Plugins :: IntelliJ"))
        self.create_trove_cat((814, 554, "postscript", "PostScript",
                               "Topic :: Formats and Protocols :: Data Formats :: PostScript"))
        self.create_trove_cat(
            (815, 100, "fractals", "Fractals and Procedural Generation",
             "Topic :: Multimedia :: Graphics :: Fractals and Procedural Generation"))
        self.create_trove_cat((816, 554, "w3cvoice", "W3C Voice",
                               "Topic :: Formats and Protocols :: Data Formats :: W3C Voice"))
        self.create_trove_cat((817, 97, "quantumcomp", "Quantum Computing",
                               "Topic :: Scientific/Engineering :: Quantum Computing"))
        self.create_trove_cat(
            (818, 129, "reportgen", "Report Generators", "Topic :: Office/Business :: Report Generators"))
        self.create_trove_cat(
            (819, 581, "research", "Research", "Topic :: Education :: Library :: Research"))
        self.create_trove_cat(
            (820, 87, "ssh", "SSH (Secure SHell)", "Topic :: Internet :: SSH (Secure SHell)"))
        self.create_trove_cat(
            (821, 554, "semantic", "Semantic Web (RDF, OWL, etc.)",
             "Topic :: Formats and Protocols :: Data Formats :: Semantic Web (RDF, OWL, etc.)"))
        self.create_trove_cat(
            (822, 90, "socialbookmarking", "Social Bookmarking",
             "Topic :: Internet :: WWW/HTTP :: Social Bookmarking"))
        self.create_trove_cat(
            (823, 20, "synchronization", "Synchronization", "Topic :: Communications :: Synchronization"))
        self.create_trove_cat(
            (824, 45, "templates", "Templates", "Topic :: Software Development :: Templates"))
        self.create_trove_cat((825, 97, "testmeasure", "Test and Measurement",
                               "Topic :: Scientific/Engineering :: Test and Measurement"))
        self.create_trove_cat((826, 98, "statistics", "Statistics",
                               "Topic :: Scientific/Engineering :: Mathematics :: Statistics"))
        self.create_trove_cat(
            (827, 129, "knowledgemanagement", "Knowledge Management",
             "Topic :: Office/Business :: Knowledge Management"))
        self.create_trove_cat(
            (828, 147, "unattended", "Unattended", "Topic :: System :: Installation/Setup :: Unattended"))
        self.create_trove_cat(
            (829, 457, "emailinterface", "Email-based interface",
             "User Interface :: Textual :: Email-based interface"))
        self.create_trove_cat(
            (830, 282, "voting", "Voting", "Topic :: Social sciences :: Voting"))
        self.create_trove_cat((831, 27, "webconferencing", "Web Conferencing",
                               "Topic :: Communications :: Conferencing :: Web Conferencing"))
        self.create_trove_cat(
            (832, 27, "videoconferencing", "Video Conferencing",
             "Topic :: Communications :: Conferencing :: Video Conferencing"))
        self.create_trove_cat(
            (833, 160, "objectivec2", "Objective-C 2.0", "Programming Language :: Objective-C 2.0"))
        self.create_trove_cat(
            (834, 274, "georgian", "Georgian", "Translations :: Georgian"))
        self.create_trove_cat(
            (835, 499, "adonet", "ADO.NET", "Database Environment :: Database API :: ADO.NET"))
        self.create_trove_cat(
            (836, 554, "xbrl", "XBRL", "Topic :: Formats and Protocols :: Data Formats :: XBRL"))
        self.create_trove_cat(
            (837, 461, "excel", "Excel", "User Interface :: Plugins :: Excel"))
        self.create_trove_cat(
            (838, 160, "visualbasicforapplications", "Visual Basic for Applications (VBA)",
             "Programming Language :: Visual Basic for Applications (VBA)"))
        self.create_trove_cat(
            (839, 160, "booprogramminglang", "Boo", "Programming Language :: Boo"))
        self.create_trove_cat(
            (840, 52, "git", "Git", "Topic :: Software Development :: Version Control :: Git"))
        self.create_trove_cat((841, 52, "mercurial", "Mercurial",
                               "Topic :: Software Development :: Version Control :: Mercurial"))
        self.create_trove_cat(
            (842, 52, "bazaar", "Bazaar", "Topic :: Software Development :: Version Control :: Bazaar"))
        self.create_trove_cat(
            (843, 14, "eupublicense", "European Union Public License",
             "License :: OSI-Approved Open Source :: European Union Public License"))
        self.create_trove_cat((844, 14, "ipafontlicense", "IPA Font License",
                               "License :: OSI-Approved Open Source :: IPA Font License"))
        self.create_trove_cat((845, 14, "miroslicense", "MirOS License",
                               "License :: OSI-Approved Open Source :: MirOS License"))
        self.create_trove_cat(
            (846, 14, "openfontlicense11", "Open Font License 1.1 (OFL 1.1)",
             "License :: OSI-Approved Open Source :: Open Font License 1.1 (OFL 1.1)"))
        self.create_trove_cat(
            (847, 80, "realtimetactical", "Real Time Tactical",
             "Topic :: Games/Entertainment :: Real Time Tactical"))
        self.create_trove_cat(
            (848, 160, "algol68", "ALGOL 68", "Programming Language :: ALGOL 68"))
        self.create_trove_cat((849, 92, "groupware", "Groupware",
                               "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Groupware"))
        self.create_trove_cat(
            (850, 576, "businesscontinuity", "Business Continuity",
             "Topic :: Office/Business :: Enterprise :: Business Continuity"))
        self.create_trove_cat(
            (852, 554, "teiformat", "TEI", "Topic :: Formats and Protocols :: Data Formats :: TEI"))
        self.create_trove_cat(
            (853, 160, "clarion", "Clarion", "Programming Language :: Clarion"))
        self.create_trove_cat(
            (854, 576, "sales", "Sales", "Topic :: Office/Business :: Enterprise :: Sales"))
        self.create_trove_cat((855, 97, "buildingauto", "Building Automation",
                               "Topic :: Scientific/Engineering :: Building Automation"))
        self.create_trove_cat(
            (856, 129, "businessmodelling", "Modelling", "Topic :: Office/Business :: Modelling"))
        self.create_trove_cat(
            (857, 150, "routing", "Routing", "Topic :: System :: Networking :: Routing"))
        self.create_trove_cat((858, 97, "medicalphysics", "Medical Physics",
                               "Topic :: Scientific/Engineering :: Medical Physics"))
        self.create_trove_cat(
            (859, 71, "edlanguage", "Languages", "Topic :: Education :: Languages"))
        self.create_trove_cat((860, 97, "molecularmech", "Molecular Mechanics",
                               "Topic :: Scientific/Engineering :: Molecular Mechanics"))
        self.create_trove_cat(
            (861, 148, "loganalysis", "Log Analysis", "Topic :: System :: Logging :: Log Analysis"))

    def m__set_parent_only(self):
        parent_only_ids = [1, 225, 274, 160, 496, 6, 13, 199, 18, 535, 534, 14,
                           611, 612, 432, 500, 426, 315, 418, 236, 457, 458, 456, 497, 499, 498]
        troves = M.TroveCategory.query.find(
            dict(trove_cat_id={'$in': parent_only_ids})).all()
        for t in troves:
            t.parent_only = True

    def m__add_license(self):
        self.update_trove_cat(
            16, dict(
                fullname="GNU Library or Lesser General Public License version 2.0 (LGPLv2)",
                fullpath="License :: OSI-Approved Open Source :: GNU Library or Lesser General Public License version 2.0 (LGPLv2)"))  # nopep8
        self.update_trove_cat(
            15, dict(fullname="GNU General Public License version 2.0 (GPLv2)",
                     fullpath="License :: OSI-Approved Open Source :: GNU General Public License version 2.0 (GPLv2)"))
        self.update_trove_cat(
            670, dict(trove_cat_id=628, fullname="Affero GNU Public License"))

        self.create_trove_cat(
            (868, 13, "ccal", "Creative Commons Attribution License",
             "License :: Creative Commons Attribution License"))
        self.create_trove_cat(
            (869, 868, "ccaslv2", "Creative Commons Attribution ShareAlike License V2.0",
             "License :: Creative Commons Attribution License :: Creative Commons Attribution ShareAlike License V2.0"))  # nopep8
        self.create_trove_cat(
            (870, 868, "ccaslv3", "Creative Commons Attribution ShareAlike License V3.0",
             "License :: Creative Commons Attribution License :: Creative Commons Attribution ShareAlike License V3.0"))  # nopep8
        self.create_trove_cat(
            (871, 868, "ccanclv2", "Creative Commons Attribution Non-Commercial License V2.0",
             "License :: Creative Commons Attribution License :: Creative Commons Attribution Non-Commercial License V2.0"))  # nopep8
        self.create_trove_cat(
            (680, 14, "lgplv3", "GNU Library or Lesser General Public License version 3.0 (LGPLv3)",
             "License :: OSI-Approved Open Source :: GNU Library or Lesser General Public License version 3.0 (LGPLv3)"))  # nopep8
        self.create_trove_cat(
            (679, 14, "gplv3", "GNU General Public License version 3.0 (GPLv3)",
             "License :: OSI-Approved Open Source :: GNU General Public License version 3.0 (GPLv3)"))
        M.TroveCategory(trove_cat_id=905,
                        trove_parent_id=14,
                        shortname='mpl20',
                        fullname='Mozilla Public License 2.0 (MPL 2.0)',
                        fullpath='License :: OSI-Approved Open Source :: Mozilla Public License 2.0 (MPL 2.0)')

    def m__set_show_as_skills(self):
        categories_regex = '|'.join([
            'Translations',
            'Programming Language',
            'User Interface',
            'Database Environment',
            'Operating System',
            'Topic',
        ])
        M.TroveCategory.query.update(
            {'fullname': re.compile(r'^(%s)' % categories_regex)},
            {'$set': {'show_as_skill': True}},
            multi=True)
