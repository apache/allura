import logging
import allura.model as M

from model.organization import WorkFields
from controller.organization import OrganizationController

log = logging.getLogger(__name__)

class ForgeOrganizationApp:
    root = OrganizationController()
    
    @classmethod
    def bootstrap(self) :
        conn = M.main_doc_session.bind.conn
        if 'allura' in conn.database_names():
            db = conn['allura']
            if 'work_fields' in db.collection_names():
                log.info('Dropping collection allura.work_fields')
                db.drop_collection('work_fields')

        l = [
            ('Home & Entertainment',
             'Applications designed primarily for use in or for the home, '+\
             'or for entertainment.'),
            ('Content & Communication',
             'Office productivity suites, multimedia players, file viewers, '+\
             'Web browsers, collaboration tools, ...'),
            ('Education & Reference',
             'Educational software, learning support tools, ...'),
            ('Operations & Professionals',
             'ERPs, CRMs, SCMs, applications for specific business uses, ...'),
            ('Product manufacturing and service delivery',
             'Software to support specific product manufacturing and '+\
             'service delivery'),
            ('Platform & Management',
             'Operating systems, security, infrastructure services, ' + \
             'hardware components controllers, ...'),
            ('Mobile apps',
             'Applications for mobile devices, such as telephones, PDAs, ...'),
            ('Web applications','Applications available on the web')]

        for (n, d) in l: 
            log.info('Added work field %s.' % n)
            WorkFields.insert(n,d)
