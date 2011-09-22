import sys
import logging

from pylons import c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

def main():
    M.TroveCategory(trove_cat_id=655,
                    trove_parent_id=14,
                    shortname="lppl",
                    fullname="LaTeX Project Public License",
                    fullpath="License :: OSI-Approved Open Source :: LaTeX Project Public License")
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=432,
                    shortname="win64",
                    fullname="64-bit MS Windows",
                    fullpath="Operating System :: Grouping and Descriptive Categories :: 64-bit MS Windows")
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=418,
                    shortname="vista",
                    fullname="Vista",
                    fullpath="Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Vista")
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=418,
                    shortname="win7",
                    fullname="Windows 7",
                    fullpath="Operating System :: Modern (Vendor-Supported) Desktop Operating Systems :: Windows 7")
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=315,
                    shortname="android",
                    fullname="Android",
                    fullpath="Operating System :: Handheld/Embedded Operating Systems :: Android")
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=315,
                    shortname="ios",
                    fullname="Apple iPhone",
                    fullpath="Operating System :: Handheld/Embedded Operating Systems :: Apple iPhone")
    M.TroveCategory(trove_cat_id=863,
                    trove_parent_id=534,
                    shortname="architects",
                    fullname="Architects",
                    fullpath="Intended Audience :: by End-User Class :: Architects")
    M.TroveCategory(trove_cat_id=864,
                    trove_parent_id=534,
                    shortname="auditors",
                    fullname="Auditors",
                    fullpath="Intended Audience :: by End-User Class :: Auditors")
    M.TroveCategory(trove_cat_id=865,
                    trove_parent_id=534,
                    shortname="testers",
                    fullname="Testers",
                    fullpath="Intended Audience :: by End-User Class :: Testers")
    M.TroveCategory(trove_cat_id=866,
                    trove_parent_id=534,
                    shortname="secpros",
                    fullname="Security Professionals",
                    fullpath="Intended Audience :: by End-User Class :: Security Professionals")
    M.TroveCategory(trove_cat_id=867,
                    trove_parent_id=535,
                    shortname="secindustry",
                    fullname="Security",
                    fullpath="Intended Audience :: by Industry or Sector :: Security")
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()