# Copyright (C) 2009, Justin Lewis  (jtl1728@rit.edu)
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

import gtk
import telepathy
import simplejson
import tempfile
import os
import time
import journalentrybundle
import dbus
import gobject
import zipfile
from hashlib import sha1
from gettext import gettext as _

from sugar.activity.activity import Activity

from sugar.presence.tubeconn import TubeConnection
from sugar import network
from sugar import profile

from GuiView import GuiView
from MyExceptions import InShareException, FileUploadFailure, ServerRequestFailure, NoFreeTubes, TimeOut

from TubeSpeak import TubeSpeak
import FileInfo
from hashlib import sha1

import urllib, urllib2, MultipartPostHandler, httplib
import threading

import logging
_logger = logging.getLogger('fileshare-activity')

SERVICE = "org.laptop.FileShare"
IFACE = SERVICE
PATH = "/org/laptop/FileShare"
DIST_STREAM_SERVICE = 'fileshare-activity-http'

class MyHTTPRequestHandler(network.ChunkedGlibHTTPRequestHandler):
    def translate_path(self, path):
        return self.server._pathBuilder( path )

class MyHTTPServer(network.GlibTCPServer):
    def __init__(self, server_address, pathBuilder):
        self._pathBuilder = pathBuilder
        network.GlibTCPServer.__init__(self, server_address, MyHTTPRequestHandler)

class FileShareActivity(Activity):
    def __init__(self, handle):
        Activity.__init__(self, handle)
        #wait a moment so that our debug console capture mistakes
        gobject.threads_init()
        gobject.idle_add( self._doInit, None )

    def _doInit(self, handle):
        _logger.info("activity running")

        # Make a temp directory to hold all files
        temp_path = os.path.join(self.get_activity_root(), 'instance')
        self._filepath = tempfile.mkdtemp(dir=temp_path)

        # Set if they started the activity
        self.isServer = not self._shared_activity

        # Port the file server will do http transfers
        self.port = 1024 + (hash(self._activity_id) % 64511)

        # Data structures for holding file list
        self.sharedFiles = {}

        # Holds the controll tube
        self.controlTube = None

        # Holds tubes for transfers
        self.unused_download_tubes = set()
        self.addr=None

        # Are we the ones that created the control tube
        self.initiating = False

        # Set to true when closing for keep cleanup
        self._close_requested = False

        # Set up internals for server mode if later requested
        self._mode = "P2P"
        prof = profile.get_profile()
        self._user_key_hash = sha1(prof.pubkey).hexdigest()
        self._user_nick = profile.get_nick_name()
        self._user_permissions = 0
        self.server_ip = None

        jabber_serv = None
        prof = profile.get_profile()
        #Need to check if on 82 or higher
        if hasattr(prof, 'jabber_server'):
            jabber_serv = prof.jabber_server
        else:
            #Higher, everything was moved to gconf
            import gconf
            client = gconf.client_get_default()
            jabber_serv = client.get_string("/desktop/sugar/collaboration/jabber_server")

        if jabber_serv:
            self.server_ip = jabber_serv
            self.server_port= 14623
            self.s_version = 0


        # INITIALIZE GUI
        ################
        self.set_title('File Share')

        # Set gui display object
        self.disp = GuiView(self)

        # Set Toolbars
        self.disp.build_toolbars()

        # Build table and display the gui
        self.disp.build_table()

        # Connect to shared and join calls
        self._sh_hnd = self.connect('shared', self._shared_cb)
        self._jo_hnd = self.connect('joined', self._joined_cb)

        self.set_canvas(self.disp)
        self.show_all()

    def switch_to_server(self):
        if self.server_ip and self.isServer:
            self._mode = "SERVER"
            self.isServer = False

            # Remove shared mode
            # Disable handlers incase not shared yet
            self.disconnect( self._sh_hnd )
            self.disconnect( self._jo_hnd )

            # Disable notify the tube of changes
            self.initiating = False

            # Disable greeting people joining tube
            if self.controlTube:
                self.controlTube.switch_to_server_mode()

            # Set activity to private mode if shared
            if self._shared_activity:
                ##TODO:
                pass

            # Clear file List (can't go to server mode after sharing, clear list)
            # Will not delete files so connected people can still download files.
            self.disp.clear_files(False)

            # Rebuild gui, now we are in server mode
            self.disp.build_toolbars()

            #self.set_canvas(self.disp)
            #self.show_all()

            #IN SERVER MODE, GET SERVER FILE LIST
            def call():
                try:
                    conn = httplib.HTTPConnection( self.server_ip, self.server_port)
                    conn.request("GET", "/filelist")
                    r1 = conn.getresponse()
                    if r1.status == 200:
                        data = r1.read()
                        conn.close()
                        self.incomingRequest('filelist',data)
                    else:
                        self.disp.guiHandler._alert(str(r1.status), _("Error getting file list") )
                except:
                    self.disp.guiHandler._alert(_("Error getting file list"))
                self.disp.guiHandler.show_throbber(False)

            self.disp.guiHandler.show_throbber(True, _("Requesting file list from server"))
            threading.Thread(target=call).start()

    def check_for_server(self):
        s_version = None
        try:
            conn = httplib.HTTPConnection( self.server_ip, self.server_port)
            conn.request("GET", "/version")
            r1 = conn.getresponse()
            if r1.status == 200:
                s_version= r1.read()
                conn.close()

                if int(s_version) >= 2:
                    # Version 2 supports permissions, announce user so server
                    # can cache user info and be added to the access list if allowed

                    params =  { 'id': self._user_key_hash,
                                'nick': self._user_nick
                              }
                    try:
                        opener = urllib2.build_opener( MultipartPostHandler.MultipartPostHandler)
                        f = opener.open("http://%s:%d/announce_user"%(self.server_ip, self.server_port), params)
                        self._user_permissions = int(f.read())
                    except:
                        raise ServerRequestFailure

                else:
                    # Older version didn't have permissions, set 1 as default (upload/remove)
                    self._user_permissions = 1
                self.s_version = s_version
                return True
            else:
                return False
        except:
            return False

    def get_server_user_list(self):
        params =  { 'id': self._user_key_hash }
        try:
            opener = urllib2.build_opener( MultipartPostHandler.MultipartPostHandler)
            f = opener.open("http://%s:%d/user_list"%(self.server_ip, self.server_port), params)
            response = f.read()
            return simplejson.loads(response)
        except Exception:
            raise ServerRequestFailure

    def change_server_user(self, userId, level):
        params = { 'id': self._user_key_hash,
                   'userid': userId,
                   'level': level
                 }
        try:
            opener = urllib2.build_opener( MultipartPostHandler.MultipartPostHandler)
            f = opener.open("http://%s:%d/user_mod"%(self.server_ip, self.server_port), params)
        except:
            raise ServerRequestFailure

    def build_file(self, jobject):
        #If object has activity id and it is filled in, use that as hash
        if jobject.metadata.has_key("activity_id") and str(jobject.metadata['activity_id']):
            objectHash = str(jobject.metadata['activity_id'])
            bundle_path = os.path.join(self._filepath, '%s.xoj' % objectHash)

            # If file in share, return don't build file
            if os.path.exists(bundle_path):
                raise InShareException()

        else:
            # Unknown activity id, must be a file
            if jobject.get_file_path():
                # FIXME: This just checks the file hash should check for
                # identity by compairing metadata, but this will work for now
                # Problems are that if you have one file multiple times it will
                # only allow one copy of that file regardless of the metadata
                objectHash = sha1(open(jobject.get_file_path() ,'rb').read()).hexdigest()
                bundle_path = os.path.join(self._filepath, '%s.xoj' % objectHash)

                if os.path.exists(bundle_path):
                    raise InShareException()

            else:
                # UNKOWN ACTIVTIY, No activity id, no file hash, just add it
                # FIXME
                _logger.warn("Unknown File Data. Can't check if file is already shared.")
                objectHash = sha1(time.time()).hexdigest()
                bundle_path = os.path.join(self._filepath, '%s.xoj' % objectHash)

        journalentrybundle.from_jobject(jobject, bundle_path )

        # Build file information
        desc =  "" if not jobject.metadata.has_key('description') else str( jobject.metadata['description'] )
        title = _("Untitled") if str(jobject.metadata['title']) == "" else str(jobject.metadata['title'])
        tags = "" if not jobject.metadata.has_key('tags') else str( jobject.metadata['tags'] )
        size = os.path.getsize( bundle_path )

        #File Info Block
        return FileInfo.FileInfo(objectHash, title, desc, tags, size, True)

    def send_file_to_server(self, id, file_info):
        bundle_path = os.path.join(self._filepath, '%s.xoj' % id)
        params = { 'jdata': simplejson.dumps(file_info.share_dump()),
                    'file':  open(bundle_path, 'rb')
                }

        if self.s_version >= 2:
            params['id'] = self._user_key_hash

        try:
            opener = urllib2.build_opener( MultipartPostHandler.MultipartPostHandler)
            opener.open("http://%s:%d/upload"%(self.server_ip, self.server_port), params)
        except:
            raise FileUploadFailure()

    def remove_file_from_server( self, file_id ):
        params =  { 'fid': file_id }

        if self.s_version >= 2:
            params['id'] = self._user_key_hash

        try:
            opener = urllib2.build_opener( MultipartPostHandler.MultipartPostHandler)
            opener.open("http://%s:%d/remove"%(self.server_ip, self.server_port), params)
        except:
            raise ServerRequestFailure


    def updateFileObj( self, key, file_obj ):
        if self.sharedFiles.has_key( key ):
            self.sharedFiles[key] = file_obj

    def _registerShareFile( self, key, file_obj ):
        self.sharedFiles[key] = file_obj

        # Notify connected users
        if self.initiating:
                self.controlTube.FileAdd( simplejson.dumps(fileinfo.share_dump()) )

    def _unregisterShareFile( self, key ):
        del self.sharedFiles[key]

        # Notify connected users
        if self.initiating:
            self.controlTube.FileRem( simplejson.dumps(id) )



    def delete_file( self, id ):
        bundle_path = os.path.join(self._filepath, '%s.xoj' % id)
        try:
            os.remove( bundle_path )
        except:
            _logger.warn("Could not remove file from system: %s",bundle_path)

    def server_ui_del_overide(self):
        return self.isServer or self._mode=="SERVER"

    def getFileList(self):
        ret = {}
        for key in self.sharedFiles:
            ret[key] = self.sharedFiles[key].share_dump()
        return simplejson.dumps(ret)

    def filePathBuilder(self, path):
        if self.sharedFiles.has_key( path[1:] ):
            return os.path.join(self._filepath, '%s.xoj' % path[1:])
        else:
            _logger.debug("INVALID PATH",path[1:])

    def _shared_cb(self, activity):
        _logger.debug('Activity is now shared')
        self.initiating = True

        # Add hooks for new tubes.
        self.watch_for_tubes()

        #Create Shared tube
        _logger.debug('This is my activity: making a tube...')

        # Offor control tube (callback will put it into crontrol tube var)
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube( SERVICE, {})

        #Get ready to share files
        self._share_document()

    def _joined_cb(self, activity):

        _logger.debug('Joined an existing shared activity')
        self.initiating = False

        # Add hooks for new tubes.
        self.watch_for_tubes()

        # Normally, we would just ask for the document.
        # This activity allows the user to request files.
        # The server will send us the file list and then we
        # can use any new tubes to download the file



    def watch_for_tubes(self):
        """This method sets up the listeners for new tube connections"""
        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal('NewTube',
            self._new_tube_cb)

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _share_document(self):
        _logger.info("Ready to share document, starting file server")
        # FIXME: should ideally have the fileserver listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)

        # Create a fileserver to serve files
        self._fileserver = MyHTTPServer(("", self.port), self.filePathBuilder)

        # Make a tube for it
        chan = self._shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        self._fileserver_tube_id = iface.OfferStreamTube(DIST_STREAM_SERVICE,
                {},
                telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                ('127.0.0.1', dbus.UInt16(self.port)),
                telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0)

    def _server_download_document( self, fileId ):
        addr = [self.server_ip, self.server_port]
        self._download_document(addr, fileId)
        # Download the file at next avaialbe time.
        #gobject.idle_add(self._download_document, addr, fileId)
        #return False


    def _get_document(self,fileId):
        if not self.addr:
            try:
                tube_id = self.unused_download_tubes.pop()
            except (ValueError, KeyError), e:
                _logger.debug('No tubes to get the document from right now: %s', e)
                raise NoFreeTubes()

            # FIXME: should ideally have the CM listen on a Unix socket
            # instead of IPv4 (might be more compatible with Rainbow)
            chan = self._shared_activity.telepathy_tubes_chan
            iface = chan[telepathy.CHANNEL_TYPE_TUBES]
            self.addr = iface.AcceptStreamTube(tube_id,
                    telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                    telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0,
                    utf8_strings=True)

            _logger.debug('Accepted stream tube: listening address is %r', self.addr)
            # SOCKET_ADDRESS_TYPE_IPV4 is defined to have addresses of type '(sq)'
            assert isinstance(self.addr, dbus.Struct)
            assert len(self.addr) == 2
            assert isinstance(self.addr[0], str)
            assert isinstance(self.addr[1], (int, long))
            assert self.addr[1] > 0 and self.addr[1] < 65536

        # Download the file at next avaialbe time.
        self._download_document(self.addr, fileId)
        #gobject.idle_add(self._download_document, self.addr, fileId)
        #return False

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        _loggerg.error('ListTubes() failed: %s', e)

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        _logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                     'params=%r state=%d', id, initiator, type, service, params, state)
        if (type == telepathy.TUBE_TYPE_DBUS and service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)
            # Control tube
            _logger.debug("Connecting to Control Tube")
            tube_conn = TubeConnection(self.conn,
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES], id,
                group_iface=self.tubes_chan[telepathy.CHANNEL_INTERFACE_GROUP])

            self.controlTube = TubeSpeak(tube_conn, self.initiating,
                                         self.incomingRequest, self.getFileList)
        elif (type == telepathy.TUBE_TYPE_STREAM and service == DIST_STREAM_SERVICE):
                # Data tube, store for later
                _logger.debug("New data tube added")
                self.unused_download_tubes.add(id)


    def incomingRequest(self,action,request):
        if action == "filelist":
            filelist = simplejson.loads( request )
            for key in filelist:
                if not self.sharedFiles.has_key(key):
                    fi = FileInfo.share_load(filelist[key])
                    self.disp.guiHandler._addFileToUIList(fi.id, fi)
                    # Register File with activity share list
                    self._registerShareFile( fi.id, fi )
        elif action == "fileadd":
            addList = simplejson.loads( request )
            fi = FileInfo.share_load( addList )
            self.disp.guiHandler._addFileToUIList( fi.id, fi )
            self._registerShareFile( fi.id, fi )
        elif action == "filerem":
            id =  simplejson.loads( request )
            # DO NOT DELETE IF TRANSFER IN PROGRESS/COMPLETE
            if self.fileShare[id].aquired == 0:
                self.disp.guiHandler._remFileFromUIList( id )
                # UnRegister File with activity share list
                self._unregisterShareFile( key )

        else:
            _logger.debug("Incoming tube Request: %s. Data: %s" % (action, request) )

    def _download_document(self, addr, documentId):
        _logger.debug('Requesting to download document')
        bundle_path = os.path.join(self._filepath, '%s.xoj' % documentId)
        port = int(addr[1])

        getter = network.GlibURLDownloader("http://%s:%d/%s" % (addr[0], port,documentId))
        getter.connect("finished", self._download_result_cb, documentId)
        getter.connect("progress", self._download_progress_cb, documentId)
        getter.connect("error", self._download_error_cb, documentId)
        _logger.debug("Starting download to %s...", bundle_path)
        getter.start(bundle_path)
        return False

    def _download_result_cb(self, getter, tmp_file, suggested_name, fileId):
        _logger.debug("Got document %s (%s)", tmp_file, suggested_name)

        try:
            metadata = self._installBundle( tmp_file )
            self.disp.guiHandler._alert( _("File Downloaded"), metadata['title'])
            self.disp.set_installed( fileId )
        except:
            self.disp.guiHandler._alert( _("File Download Failed") )
            self.disp.set_installed( fileId, False )

    def _download_progress_cb(self, getter, bytes_downloaded, fileId):
        self.disp.update_progress( fileId, bytes_downloaded )

        # Force gui to update if there are actions pending
        # Fixes bug where system appears to hang on FAST connections
        while gtk.events_pending():
            gtk.main_iteration()

    def _download_error_cb(self, getter, err, fileId):
        _logger.debug("Error getting document from tube. %s",  err )
        self.disp.guiHandler._alert(_("Error getting document"), err)
        #gobject.idle_add(self._get_document)


    def _installBundle(self, tmp_file):
        """Installs a file to the journal"""
        _logger.debug("Saving %s to datastore...", tmp_file)
        bundle = journalentrybundle.JournalEntryBundle(tmp_file)
        bundle.install()
        return bundle.get_metadata()


    def can_close( self ):
        #TODO: HAVE SERVER CHECK IF IT CAN CLOSE
        self._close_requested = True
        return True

    def write_file(self, file_path):
        _logger.debug('Writing activity file')

        file = zipfile.ZipFile(file_path, "w")

        # If no files to save save empty list
        if len(self.sharedFiles) == 0:
            #hack to empty file if existed before
            file.writestr("_filelist.json", simplejson.dumps({}))
            file.close()
            return

        if self._close_requested:
            dialog = gtk.MessageDialog(self, gtk.DIALOG_MODAL,
                    gtk.MESSAGE_INFO, gtk.BUTTONS_YES_NO,
                    _("Saving files in activity allows the activity to resume with the current file list but takes up more space.") )
            dialog.set_title("Do you wish to save files within activity?")

            response = dialog.run()
            dialog.destroy()

            # Return not allowing files to be saved
            if response == gtk.RESPONSE_NO:
                #hack to empty file if existed before
                file.writestr("_filelist.json", simplejson.dumps({}))
                file.close()
                return

        # Save, requested, write files into zip and save file list
        try:
            for name in os.listdir(self._filepath):
                file.write(os.path.join( self._filepath, name), name, zipfile.ZIP_DEFLATED)

            file.writestr("_filelist.json", self.getFileList())
        finally:
            file.close()

    def read_file(self, file_path):
        logging.debug('RELOADING ACTIVITY DATA...')

        # Read file list from zip
        zip_file = zipfile.ZipFile(file_path,'r')
        filelist = simplejson.loads(zip_file.read("_filelist.json"))
        namelist = zip_file.namelist()
        for key in filelist:
            fileName = '%s.xoj' % key
            # Only extract and add files that we have (needed if client when saved)
            if fileName in namelist:
                bundle_path = os.path.join(self._filepath, fileName)
                open(bundle_path, "wb").write(zip_file.read(fileName))

                fi = FileInfo.share_load(filelist[key], True)
                self._addFileToUIList(fi.id, fi)

        zip_file.close()
