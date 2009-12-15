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
from gettext import gettext as _

from sugar.activity.activity import Activity, ActivityToolbox
from sugar.graphics.objectchooser import ObjectChooser
from sugar.graphics.alert import NotifyAlert
from sugar.presence.tubeconn import TubeConnection
from sugar import network

from TubeSpeak import TubeSpeak
from hashlib import sha1

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
        gobject.idle_add( self._doInit, None )

    def _doInit(self, handle):
        _logger.info("activity running")

        # Make a temp directory to hold all files
        temp_path = os.path.join(self.get_activity_root(), 'instance')
        self._filepath = tempfile.mkdtemp(dir=temp_path)

        # Port the file server will do http transfers
        self.port = 1024 + (hash(self._activity_id) % 64511)

        # Data structures for holding file list
        self.sharedFiles = {}

        # Holds the controll tube
        self.controlTube = None

        # Holds tubes for transfers
        self.unused_download_tubes = set()
        self.addr=None

        # Are we the ones creating the control tube
        self.initiating = False

        # Build and display gui
        self._buildGui()

        # Connect to shared and join calls
        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)


    def requestAddFile(self, widget, data=None):
        _logger.info('Requesting to add file')

        chooser = ObjectChooser()
        try:
            if chooser.run() == gtk.RESPONSE_ACCEPT:
                # get object and build file
                jobject = chooser.get_selected_object()

                if jobject.metadata.has_key("activity_id") and str(jobject.metadata['activity_id']):
                    objectHash = str(jobject.metadata['activity_id'])
                    bundle_path = os.path.join(self._filepath, '%s.xoj' % objectHash)

                    # If file in share, return don't build file
                    if os.path.exists(bundle_path):
                        self._alert(_("File Not Added"), _("File already shaired"))
                        return

                    journalentrybundle.from_jobject(jobject, bundle_path )

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
                            self._alert(_("File Not Added"), _("File already shaired"))
                            return

                        journalentrybundle.from_jobject(jobject, bundle_path )

                    else:
                        # UNKOWN ACTIVTIY, No activity id, no file hash, just add it
                        # FIXME
                        _logger.warn("Unknown File Data. Can't check if file is already shaired.")
                        objectHash = sha1(time.time()).hexdigest()
                        bundle_path = os.path.join(self._filepath, '%s.xoj' % objectHash)

                        journalentrybundle.from_jobject(jobject, bundle_path )
                        return

                # Build file array
                desc =  "" if not jobject.metadata.has_key('description') else str( jobject.metadata['description'] )
                title = _("Untitled") if str(jobject.metadata['title']) == "" else str(jobject.metadata['title'])
                tags = "" if not jobject.metadata.has_key('tags') else str( jobject.metadata['tags'] )
                size = os.path.getsize( bundle_path )

                self._addFileToUIList( [objectHash, title, desc, tags, size, 0, ''] )

        finally:
            chooser.destroy()
            del chooser

    def requestRemFile(self, widget, data=None):
        """Removes file from memory then calls rem file from ui"""
        _logger.info('Requesting to delete file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()
            key = model.get_value(iter, 0)
            self._remFileFromUIList(key)

            # Attempt to remove file from system
            bundle_path = os.path.join(self._filepath, '%s.xoj' % key)

            try:
                os.remove( bundle_path )
            except:
                _logger.warn("Could not remove file from system: %d",bundle_path)

    def requestInsFile(self, widget, data=None):
        _logger.info('Requesting to install file back to journal')

        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()
            key = model.get_value(iter, 0)

            # Attempt to remove file from system
            bundle_path = os.path.join(self._filepath, '%s.xoj' % key)

            self._installBundle( bundle_path )
            self._alert(_("Installed bundle to Jorunal"))




    def requestDownloadFile(self, widget, data=None):
        _logger.info('Requesting to Download file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()

            if model.get_value(iter, 6) == "":
                self._get_document(str( model.get_value(iter, 0)))
            else:
                self._alert(_("File has already or is currently being downloaded"))
        else:
            self._alert(_("You must select a file to download"))


    def _addFileToUIList(self, listDict):
        self.sharedFiles[listDict[0]] = listDict
        modle = self.treeview.get_model()

        modle.append( None, listDict )

        # Notify connected users
        if self.initiating:
                self.controlTube.FileAdd( simplejson.dumps(listDict) )

    def _remFileFromUIList(self, id):
        _logger.info('Requesting to delete file')

        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
            if model.get_value( iter, 0 ) == id:
                break
            iter = model.iter_next( iter )

        # DO NOT DELETE IF TRANSFER IN PROGRESS/COMPLETE
        if model.get_value(iter, 6) == "":
            key = model.get_value(iter, 0)
            del self.sharedFiles[key]
            model.remove( iter )

        # Notify connected users
        if self.initiating:
            self.controlTube.FileRem( simplejson.dumps(key) )

    def getFileList(self):
        return simplejson.dumps(self.sharedFiles)

    def filePathBuilder(self, path):
        if self.sharedFiles.has_key( path[1:] ):
            return os.path.join(self._filepath, '%s.xoj' % path[1:])
        else:
            _logger.debug("INVALID PATH",path[1:])

    def _buildGui(self):
        self.set_title('File Share')

        # Create Toolbox
        ################
        toolbox = ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        # Create button bar
        ###################
        hbbox = gtk.HButtonBox()

        if not self._shared_activity:
            addFileButton = gtk.Button(_("Add File"))
            addFileButton.connect("clicked", self.requestAddFile, None)
            hbbox.add(addFileButton)

            insFileButton = gtk.Button(_("Copy to Journal"))
            insFileButton.connect("clicked", self.requestInsFile, None)
            hbbox.add(insFileButton)

            remFileButton = gtk.Button(_("Remove Selected File"))
            remFileButton.connect("clicked", self.requestRemFile, None)
            hbbox.add(remFileButton)

        else:
            downloadFileButton = gtk.Button(_("Download File"))
            downloadFileButton.connect("clicked", self.requestDownloadFile, None)
            hbbox.add(downloadFileButton)

        # Create File Tree
        ##################
        table = gtk.Table(rows=10, columns=1, homogeneous=False)
        self.treeview = gtk.TreeView(gtk.TreeStore(str,str,str,str,int,int,str))

        # create the TreeViewColumn to display the data
        colName = gtk.TreeViewColumn(_('File Name'))
        colDesc = gtk.TreeViewColumn(_('Description'))
        colTags = gtk.TreeViewColumn(_('Tags'))
        colSize = gtk.TreeViewColumn(_('File Size'))
        colProg = gtk.TreeViewColumn('')

        self.treeview.append_column(colName)
        self.treeview.append_column(colDesc)
        self.treeview.append_column(colTags)
        self.treeview.append_column(colSize)

        # Don't show progress bar if server
        if self._shared_activity:
            self.treeview.append_column(colProg)

        # create a CellRendererText to render the data
        cell = gtk.CellRendererText()
        pbar = gtk.CellRendererProgress()

        # add the cell to the tvcolumn and allow it to expand
        colName.pack_start(cell, True)
        colDesc.pack_start(cell, True)
        colTags.pack_start(cell, True)
        colSize.pack_start(cell, True)
        colProg.pack_start(pbar, True)

        # set the cell "text" attribute- retrieve text
        # from that column in treestore
        colName.add_attribute(cell, 'text', 1)
        colDesc.add_attribute(cell, 'text', 2)
        colTags.add_attribute(cell, 'text', 3)
        colSize.add_attribute(cell, 'text', 4)
        colProg.add_attribute(pbar, 'text', 6)
        colProg.add_attribute(pbar, 'value', 5)

        # make it searchable
        self.treeview.set_search_column(1)

        # Allow sorting on the column
        colName.set_sort_column_id(1)

        # Put table into scroll window to allow it to scroll
        window = gtk.ScrolledWindow()
        window.add_with_viewport(self.treeview)

        table.attach(hbbox,0,1,0,1)
        table.attach(window,0,1,1,10)

        self.set_canvas(table)
        self.show_all()

    def progress_set(self, id, progress, value ):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
            if model.get_value( iter, 0 ) == id:
                break
            iter = model.iter_next( iter )

        if iter:
            model.set_value( iter, 5, progress )
            model.set_value( iter, 6, value )

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

    def _get_document(self,fileId):
        if not self.addr:
            try:
                tube_id = self.unused_download_tubes.pop()
            except (ValueError, KeyError), e:
                _logger.debug('No tubes to get the document from right now: %s', e)
                self._alert(_("All tubes are busy, file download cannot start"),_("Please wait and try again"))
                return False
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
        gobject.idle_add(self._download_document, self.addr, fileId)
        return False

    def _alert(self, title, text=None, timeout=5):
        alert = NotifyAlert(timeout=timeout)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)

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
                                         self.incomingRequest,
                                         self._alert, self.getFileList)
        elif (type == telepathy.TUBE_TYPE_STREAM and service == DIST_STREAM_SERVICE):
                # Data tube, store for later
                _logger.debug("New data tube added")
                self.unused_download_tubes.add(id)


    def incomingRequest(self,action,request):
        if action == "filelist":
            filelist = simplejson.loads( request )
            for key in filelist:
                self._addFileToUIList(filelist[key])
        elif action == "fileadd":
            self._addFileToUIList( simplejson.loads( request ) )
        elif action == "filerem":
            self._remFileFromUIList( simplejson.loads( request ) )
        else:
            _logger.debug("Incoming tube Request: %s. Data: %s" % (action, request) )

    def _download_document(self, addr, documentId):
        _logger.debug('Requesting to download document')
        bundle_path = os.path.join(self._filepath, '%s.xoj' % documentId)
        port = int(self.addr[1])

        getter = network.GlibURLDownloader("http://%s:%d/%s"
                                           % (addr[0], port,documentId))
        getter.connect("finished", self._download_result_cb, documentId)
        getter.connect("progress", self._download_progress_cb, documentId)
        getter.connect("error", self._download_error_cb, documentId)
        _logger.debug("Starting download to %s...", bundle_path)
        self._alert(_("Starting file download"))
        getter.start(bundle_path)
        return False

    def _download_result_cb(self, getter, tmp_file, suggested_name, fileId):
        _logger.debug("Got document %s (%s)", tmp_file, suggested_name)

        # Set status to downloaded
        self.progress_set( fileId, 100, _("Saving File"))

        metadata = self._installBundle( tmp_file )

        self._alert( _("File Downloaded"), metadata['title'])
        self.progress_set( fileId, 100, _("Download Complete"))



    def _download_progress_cb(self, getter, bytes_downloaded, fileId):
        # FIXME: signal the expected size somehow, so we can draw a progress
        # bar
        _logger.debug("Downloaded %u bytes for document id %d...",bytes_downloaded, fileId)

        fileInQuestion = self.sharedFiles[fileId]
        downloadPercent = (float(bytes_downloaded)/float(fileInQuestion[4]))*100.0

        self.progress_set( fileId, downloadPercent,
            "%s %d%% (%d %s)"%(_("Downloading"), downloadPercent, bytes_downloaded, _("bytes")))

        # Force gui to update if there are actions pending
        # Fixes bug where system appears to hang on FAST connections
        while gtk.events_pending():
            gtk.main_iteration()

    def _download_error_cb(self, getter, err, fileId):
        _logger.debug("Error getting document from tube. %s",  err )
        self._alert(_("Error getting document"), err)
        #gobject.idle_add(self._get_document)


    def _installBundle(self, tmp_file):
        """Installs a file to the journal"""
        _logger.debug("Saving %s to datastore...", tmp_file)
        bundle = journalentrybundle.JournalEntryBundle(tmp_file)
        bundle.install()
        return bundle.get_metadata()


    def write_file(self, file_path):
        _logger.debug('Writing activity file')

        # Create zip of tmp directory
        file = zipfile.ZipFile(file_path, "w")

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
                self._addFileToUIList(filelist[key])
        zip_file.close()
