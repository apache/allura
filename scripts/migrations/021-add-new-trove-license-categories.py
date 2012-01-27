import sys
import logging

from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

def create_trove_cat(cat_data):
    M.TroveCategory(trove_cat_id=cat_data[0], trove_parent_id=cat_data[1],
                    shortname=cat_data[2], fullname=cat_data[3], fullpath=cat_data[4])

def update_trove_cat(trove_cat_id, attr_dict):
    t = M.TroveCategory.query.get(trove_cat_id=trove_cat_id)
    if not t:
        sys.exit("Couldn't find TroveCategory with trove_cat_id=%s" % trove_cat_id)
    for k, v in attr_dict.iteritems():
        setattr(t, k, v)

def main():
    update_trove_cat(16, dict(fullname="GNU Library or Lesser General Public License version 2.0 (LGPLv2)", fullpath="License :: OSI-Approved Open Source :: GNU Library or Lesser General Public License version 2.0 (LGPLv2)"))
    update_trove_cat(15, dict(fullname="GNU General Public License version 2.0 (GPLv2)", fullpath="License :: OSI-Approved Open Source :: GNU General Public License version 2.0 (GPLv2)"))
    update_trove_cat(670, dict(trove_cat_id=628, fullname="Affero GNU Public License"))

    create_trove_cat((868,13,"ccal","Creative Commons Attribution License","License :: Creative Commons Attribution License"))
    create_trove_cat((869,868,"ccaslv2","Creative Commons Attribution ShareAlike License V2.0","License :: Creative Commons Attribution License :: Creative Commons Attribution ShareAlike License V2.0"))
    create_trove_cat((870,868,"ccaslv3","Creative Commons Attribution ShareAlike License V3.0","License :: Creative Commons Attribution License :: Creative Commons Attribution ShareAlike License V3.0"))
    create_trove_cat((871,868,"ccanclv2","Creative Commons Attribution Non-Commercial License V2.0","License :: Creative Commons Attribution License :: Creative Commons Attribution Non-Commercial License V2.0"))
    create_trove_cat((680,14,"lgplv3","GNU Library or Lesser General Public License version 3.0 (LGPLv3)","License :: OSI-Approved Open Source :: GNU Library or Lesser General Public License version 3.0 (LGPLv3)"))
    create_trove_cat((679,14,"gplv3","GNU General Public License version 3.0 (GPLv3)","License :: OSI-Approved Open Source :: GNU General Public License version 3.0 (GPLv3)"))

    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
