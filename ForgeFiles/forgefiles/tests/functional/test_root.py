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
from tg import tmpl_context as c

from allura import model as M
from alluratest.controller import TestController


from forgefiles.model.files import UploadFolder
from forgefiles.model.files import UploadFiles

from testfixtures import TempDirectory


class TestFiles(TestController):
    def test_files(self):
        c.user = M.User.by_username('test-admin')
        r = self.app.get('/files/')
        assert 'p/test' in r

    def test_create_folder(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/files/')
        data1 = {'folder_name': 'NewTestFolder'}
        folder_object = self.app.post('/p/test/files/create_folder/', data1)
        assert folder_object is not None

    def test_upload_file(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/files/')
        dir = TempDirectory()
        path = dir.write('myfile.txt', b'Testing Upload')
        with open(path, 'rb') as f:
            file_upload = [('file_upload', 'myfile.txt', f.read())]
            filename_dict = {'filename': 'myfile.txt'}
            file_object = self.app.post('/p/test/files/upload_file', filename_dict, upload_files=file_upload)
        dir.cleanup()
        assert file_object is not None

    def test_edit_folder(self):
        folder = create_folder(self)
        folder_object = UploadFolder.query.get(folder_name=folder.folder_name)
        data1 = {'folder_id': str(folder_object._id), 'folder_name': 'NewFolderName'}
        self.app.post('/p/test/files/edit_folder', data1)
        resp = self.app.get('/files/')
        assert 'NewFolderName' in resp

    def test_edit_file(self):
        file_object = upload_file(self)
        db_file_object = UploadFiles.query.get(filename=file_object.filename)
        data1 = {'file_id': str(db_file_object._id), 'file_name': 'NewFileName'}
        self.app.post('/p/test/files/edit_file', data1)
        resp = self.app.get('/files/')
        assert 'NewFileName' in resp

    def test_publish_folder(self):
        create_folder(self)
        folder_object = UploadFolder.query.get(folder_name='TestFolder')
        data1 = {'folder_id': str(folder_object._id), 'remarks': 'Publishing new Version'}
        self.app.post('/p/test/files/publish_folder', data1)
        resp = self.app.get('/files/')
        assert folder_object.published is True

    def test_link_file(self):
        file_object = upload_file(self)
        db_file_object = UploadFiles.query.get(filename=file_object.filename)
        data1 = {'file_id': str(db_file_object._id)}
        self.app.post('/p/test/files/link_file', data1)
        resp = self.app.get('/files/')
        assert str(db_file_object.linked_to_download) in resp

    def test_disable_folder(self):
        create_folder(self)
        folder_object = UploadFolder.query.get(folder_name='TestFolder')
        data1 = {'folder_id': str(folder_object._id), 'status': 'True'}
        self.app.post('/p/test/files/disable_folder', data1)
        resp = self.app.get('/files/')
        assert str(folder_object.disabled) in resp

    def test_disable_file(self):
        file_object = upload_file(self)
        db_file_object = UploadFiles.query.get(filename=file_object.filename)
        data1 = {'file_id': str(db_file_object._id), 'status': 'True'}
        self.app.post('/p/test/files/disable_file', data1)
        resp = self.app.get('/files/')
        assert str(db_file_object.disabled) in resp

    def test_delete_folder(self):
        create_folder(self)
        folder_object = UploadFolder.query.get(folder_name='TestFolder')
        data1 = {'folder_id': str(folder_object._id)}
        self.app.post('/p/test/files/delete_folder', data1)
        new_folder_object = UploadFolder.query.get(_id=folder_object._id)
        assert new_folder_object is None

    def test_delete_file(self):
        file_object = upload_file(self)
        db_file_object = UploadFiles.query.get(filename=file_object.filename)
        data1 = {'file_id': str(db_file_object._id)}
        self.app.post('/p/test/files/delete_file', data1)
        new_file_object = UploadFiles.query.get(_id=db_file_object._id)
        assert new_file_object is None


def create_folder(self):
    c.user = M.User.by_username('test-admin')
    self.app.get('/files/')
    data = {'folder_name': 'TestFolder'}
    self.app.post('/p/test/files/create_folder/', data)
    folder_object = UploadFolder.query.get(folder_name='TestFolder')
    return folder_object


def upload_file(self):
    c.user = M.User.by_username('test-admin')
    self.app.get('/files/')
    dir = TempDirectory()
    path = dir.write('myfile.txt', b'Testing Upload')
    with open(path, 'rb') as f:
        file_upload = [('file_upload', 'myfile.txt', f.read())]
        filename_dict = {'filename':'myfile.txt'}
        self.app.post('/p/test/files/upload_file', filename_dict, upload_files=file_upload)
    file_object = UploadFiles.query.get(filename='myfile.txt')
    dir.cleanup()
    return file_object
