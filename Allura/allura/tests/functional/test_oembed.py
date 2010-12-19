from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from allura.tests import TestController
from allura import model as M

class TestOEmbedController(TestController):

    def test_oembed(self):
        urls = [
            'http://www.youtube.com/watch?v=LGRycUpBLS4',
            'http://www.flickr.com/photos/wizardbt/2584979382/',
            'http://www.viddler.com/explore/cdevroe/videos/424/',
            'http://qik.com/qiknews',
            'http://qik.com/video/49565',
            #'http://revision3.com/diggnation/2008-04-17xsanned/',
            'http://www.hulu.com/watch/20807/late-night-with-conan-obrein-wed-may-21-2008',
            # 'http://www.vimeo.com/757219',
            'http://www.amazon.com/Essential-SQLAlchemy-Rick-Copeland/dp/0596516142/',
            'http://www.polleverywhere.com/multiple_choice_polls/LTIwNzM1NTczNTE',
            'http://my.opera.com/cstrep/albums/show.dml?id=504322',
            # 'http://www.clearspring.com/widgets/480fbb38b51cb736',
            'http://twitter.com/mai_co_jp/statuses/822499364',
            ]
        for href in urls:
            r = self.app.get('/oembed/', params=dict(href=href), status=[200,503], validate_skip=True)

