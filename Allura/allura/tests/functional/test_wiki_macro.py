from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.tests import TestController
from allura.tests import decorators as td

class TestWikiMacro(TestController):

    @staticmethod
    def get_project_names(r):
        """
        Extracts a list of project names from a wiki page HTML.
        """
        # projects short names are in h2 elements without any attributes
        # there is one more h2 element, but it has `class` attribute
        return [e.text for e in r.html.findAll('h2') if not e.attrs]

    @staticmethod
    def get_projects_property_in_the_same_order(names, prop):
        """
        Returns a list of projects properties `prop` in the same order as
        project `names`.
        It is required because results of the query are not in the same order as names.
        """
        projects = M.Project.query.find(dict(name={'$in': names})).all()
        projects_dict = dict([(p['name'],p[prop]) for p in projects])
        return [projects_dict[name] for name in names]

    @td.with_wiki
    def test_sort_alpha(self):
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects sort=alpha]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        project_list = self.get_project_names(r)
        assert project_list == sorted(project_list)

    @td.with_wiki
    def test_sort_registered(self):
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects sort=last_registred]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        project_names = self.get_project_names(r)
        ids = self.get_projects_property_in_the_same_order(project_names, '_id')
        assert ids == sorted(ids, reverse=True)

    @td.with_wiki
    def test_sort_updated(self):
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects sort=last_updated]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        project_names = self.get_project_names(r)
        updated_at = self.get_projects_property_in_the_same_order(project_names, 'last_updated')
        assert updated_at == sorted(updated_at, reverse=True)

    @td.with_wiki
    def test_filtering(self):
        # set up for test
        from random import choice
        trove_count = M.TroveCategory.query.find().count()
        random_trove = M.TroveCategory.query.get(trove_cat_id=choice(range(trove_count)) + 1)
        test_project = M.Project.query.get(name='test')
        test_project_troves = getattr(test_project, 'trove_' + random_trove.type)
        test_project_troves.append(random_trove._id)
        ThreadLocalORMSession.flush_all()
        # test itself
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects category="' + random_trove.fullpath + '"]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        project_names = self.get_project_names(r)
        assert [test_project.name, ] == project_names


    @td.with_wiki
    def test_projects_macro(self):
        # test columns
        two_column_style = 'width: 330px;'
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list columns=2]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert two_column_style in r

        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list columns=3]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert two_column_style not in r

        # test project icon
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list show_proj_icon=on]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert 'test Logo' in r
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list show_proj_icon=off]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert 'test Logo' not in r

        # test project download button
        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list show_download_button=on]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert 'download-button' in r

        r = self.app.post('/p/wiki/Home/update',
                          params={
                                  'title': 'Home',
                                  'text': '[[projects display_mode=list show_download_button=off]]'
                                  },
                          extra_environ=dict(username='root'), upload_files=[]).follow()
        assert 'download-button' not in r
