# Copyright (C) 2007, One Laptop Per Child
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import tempfile
import logging
import shutil
import zipfile
import stat

import simplejson as json

import dbus
from sugar.datastore import datastore
#from sugar.bundle.bundle import Bundle, MalformedBundleException, \
#    NotInstalledException, InvalidPathException

from bundle import Bundle, MalformedBundleException, \
    NotInstalledException, InvalidPathException

RWXR_XR_X = stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
RW_R__R__ = stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH

# FIXME: We should not be doing this for every entry. Cannot get JSON to accept
# the dbus types?
def _sanitize_dbus_dict(dbus_dict):
    base_dict = {}
    for key in dbus_dict.keys():
        k = str(key)
        v = str(dbus_dict[key])
        base_dict[k] = v
    return base_dict

def from_jobject(jobject, bundle_path):
    b = JournalEntryBundle(bundle_path)
    b.set_metadata(jobject.get_metadata())
    if jobject.get_file_path():
        b.set_file(jobject.get_file_path())
    return b

class JournalEntryBundle(Bundle):
    """A Journal entry bundle

    See http://wiki.laptop.org/go/Journal_entry_bundles for details
    """

    MIME_TYPE = 'application/vnd.olpc-journal-entry'

    _zipped_extension = '.xoj'
    _unzipped_extension = None
    _infodir = None

    def __init__(self, path):
        Bundle.__init__(self, path)

    def get_entry_id(self):
        try:
            zip_file = zipfile.ZipFile(self._path,'r')
            file_names = zip_file.namelist()
        except:
            raise MalformedBundleException
        if len(file_names) == 0:
            raise MalformedBundleException('Empty zip file')

        if file_names[0] == 'mimetype':
            del file_names[0]

        zip_root_dir = file_names[0].split('/')[0]
        return zip_root_dir

    def set_entry_id(self, entry_id):
        try:
            zip_file = zipfile.ZipFile(self._path,'a')
        except:
            zip_file = zipfile.ZipFile(self._path,'w')
        file_names = zip_file.namelist()
        if len(file_names) == 0:
            base_dir = zipfile.ZipInfo(entry_id + '/')
            zip_file.writestr(base_dir, '')
        else:
            raise MalformedBundleException("entry_id already set")

    def install(self):
        if os.environ.has_key('SUGAR_ACTIVITY_ROOT'):
            install_dir = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'], 'instance')
        else:
            install_dir = tempfile.gettempdir()
        uid = self.get_entry_id()
        bundle_dir = os.path.join(install_dir, uid)
        self._unzip(install_dir)
        try:
            metadata = self.get_metadata()
            jobject = datastore.create()
            try:
                for key, value in metadata.iteritems():
                    jobject.metadata[key] = value

                preview = self.get_preview()
                if preview != '':
                    jobject.metadata['preview'] = dbus.ByteArray(preview)
                jobject.metadata['uid'] = ''

                if jobject.metadata.has_key('mountpoint'):
                    del jobject.metadata['mountpoint']

                os.chmod(bundle_dir, RWXR_XR_X)

                if( os.path.exists( os.path.join(bundle_dir, uid) ) ):
                    jobject.file_path = os.path.join(bundle_dir, uid)
                    os.chmod(jobject.file_path, RW_R__R__)

                datastore.write(jobject)
            finally:
                jobject.destroy()
        finally:
            shutil.rmtree(bundle_dir, ignore_errors=True)

    def set_preview(self, preview_data):
        entry_id = self.get_entry_id()
        preview_path = os.path.join(entry_id, 'preview', entry_id)
        zip_file = zipfile.ZipFile(self._path,'a')
        zip_file.writestr(preview_path, preview_data)
        zip_file.close()

    def get_preview(self):
        entry_id = self.get_entry_id()
        preview_path = os.path.join(entry_id, 'preview', entry_id)
        zip_file = zipfile.ZipFile(self._path,'r')
        try:
            preview_data = zip_file.read(preview_path)
        except:
            preview_data = ''
        zip_file.close()
        return preview_data

    def is_installed(self):
        # These bundles can be reinstalled as many times as desired.
        return False

    def set_metadata(self, metadata):
        metadata = _sanitize_dbus_dict(metadata)
        try:
            entry_id = self.get_entry_id()
            #if entry_id != metadata[uid]:
            #    raise InvalidPathException("metadata's entry id is different from my entry id")
        except MalformedBundleException:
            entry_id = metadata['activity_id']
            if( entry_id == "" ):
                #If the entry_id is empty, (file not activity) then make an entryid
                import hashlib

                if metadata.has_key('timestamp'):
                    entry_id = hashlib.sha1(metadata['timestamp']).hexdigest()
                else:
                    import time
                    entry_id = hashlib.sha1( str(time.time()) ).hexdigest()
            self.set_entry_id(entry_id)

        if 'preview' in metadata:
            self.set_preview(str(metadata['preview']))
            metadata['preview'] = entry_id

        encoded_metadata = json.dumps(metadata)

        zip_file = zipfile.ZipFile(self._path,'a')
        zip_file.writestr(os.path.join(entry_id, "_metadata.json"), encoded_metadata)
        zip_file.close()

    def get_metadata(self):
        entry_id = self.get_entry_id()
        zip_file = zipfile.ZipFile(self._path,'r')
        metadata_path = os.path.join(entry_id,"_metadata.json")
        try:
            encoded_data = zip_file.read(metadata_path)
        except:
            raise MalformedBundleException('Bundle must contain the file "_metadata.json".')
        zip_file.close()

        return json.loads(encoded_data)

    def set_file(self, infile):
        entry_id = self.get_entry_id()
        file_path = os.path.join(entry_id, entry_id)
        zip_file = zipfile.ZipFile(self._path, 'a')
        zip_file.write(infile, file_path)
        zip_file.close()

    def get_file(self):
        entry_id = self.get_entry_id()
        file_path = os.path.join(entry_id, entry_id)
        try:
            zip_file = zipfile.ZipFile(self._path,'r')
            file_data = zip_file.read(file_path)
            zip_file.close()
        except:
            file_data = ''
        return file_data
