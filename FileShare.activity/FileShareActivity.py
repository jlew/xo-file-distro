import gtk
import telepathy
import pickle
import tempfile
import os
import journalentrybundle
import dbus
import gobject

from sugar.activity.activity import Activity, ActivityToolbox
from sugar.graphics.objectchooser import ObjectChooser
from sugar.graphics.alert import NotifyAlert
from sugar.presence.tubeconn import TubeConnection
from sugar import network

from TubeSpeak import TubeSpeak

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
        self._filepath = tempfile.mkdtemp()

        # Port the file server will do http transfers
        self.port = 1024 + (hash(self._activity_id) % 64511)

        # Data structures for holding file lists
        self.sharedFiles = {}
        self.sharedFileObjects = {}
        self.fileIndex = 0

        # Holds the controll tube
        self.controlTube = None

        # Holds tubes for transfers
        self.unused_download_tubes = set()

        # Are we the ones creating the control tube
        self.initiating = False

        # Build and display gui
        self._buildGui()

        # Connect to shaied and join calls
        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)


    def requestAddFile(self, widget, data=None):
        _logger.info('Requesting to add file')

        chooser = ObjectChooser()
        try:
            if chooser.run() == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                self.fileIndex = self.fileIndex + 1
                self.sharedFileObjects[self.fileIndex] = jobject


                bundle_path = os.path.join(self._filepath, '%i.xoj' % self.fileIndex)

                journalentrybundle.from_jobject(jobject, bundle_path)

                desc =  "" if not jobject.metadata.has_key('description') else str( jobject.metadata['description'] )
                title = "Untitled" if str(jobject.metadata['title']) == "" else str(jobject.metadata['title'])
                tags = "" if not jobject.metadata.has_key('tags') else str( jobject.metadata['tags'] )
                size = os.path.getsize( bundle_path )

                self._addFileToUIList( [self.fileIndex, title, desc, tags, size] )

                #TODO: IF SHARED, SEND NEW FILE LIST
        finally:
            chooser.destroy()
            del chooser

    def requestRemFile(self, widget, data=None):
        _logger.info('Requesting to delete file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()
            key = model.get_value(iter, 0)
            del self.sharedFiles[key]
            del self.sharedFileObjects[key]
            model.remove( iter )

    def requestDownloadFile(self, widget, data=None):
        _logger.info('Requesting to Download file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()

            self._get_document(str( model.get_value(iter, 0)))


    def _addFileToUIList(self, listDict):
        self.sharedFiles[listDict[0]] = listDict
        modle = self.treeview.get_model()

        modle.append( None, listDict )

    def getFileList(self):
        return pickle.dumps(self.sharedFiles)

    def getFileObject(self, id):
        return self.sharedFileObjects[id]

    def filePathBuilder(self, path):
        if self.sharedFiles.has_key( int(path[1:]) ):
            return os.path.join(self._filepath, '%s.xoj' % path[1:])
        else:
            self._alert("INVALID PATH",path[1:])

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
            addFileButton = gtk.Button("Add File")
            addFileButton.connect("clicked", self.requestAddFile, None)
            hbbox.add(addFileButton)

            remFileButton = gtk.Button("Remove Selected File")
            remFileButton.connect("clicked", self.requestRemFile, None)
            hbbox.add(remFileButton)

        else:
            downloadFileButton = gtk.Button("Download File")
            downloadFileButton.connect("clicked", self.requestDownloadFile, None)
            hbbox.add(downloadFileButton)

        # Create File Tree
        ##################
        table = gtk.Table(rows=10, columns=1, homogeneous=False)
        self.treeview = gtk.TreeView(gtk.TreeStore(int,str,str,str,int))

        # create the TreeViewColumn to display the data
        colName = gtk.TreeViewColumn('File Name')
        colDesc = gtk.TreeViewColumn('Description')
        colTags = gtk.TreeViewColumn('Tags')
        colSize = gtk.TreeViewColumn('File Size')

        self.treeview.append_column(colName)
        self.treeview.append_column(colDesc)
        self.treeview.append_column(colTags)
        self.treeview.append_column(colSize)

        # create a CellRendererText to render the data
        self.cell = gtk.CellRendererText()

        # add the cell to the tvcolumn and allow it to expand
        colName.pack_start(self.cell, True)
        colDesc.pack_start(self.cell, True)
        colTags.pack_start(self.cell, True)
        colSize.pack_start(self.cell, True)

        # set the cell "text" attribute- retrieve text
        # from that column in treestore
        colName.add_attribute(self.cell, 'text', 1)
        colDesc.add_attribute(self.cell, 'text', 2)
        colTags.add_attribute(self.cell, 'text', 3)
        colSize.add_attribute(self.cell, 'text', 4)

        # make it searchable
        self.treeview.set_search_column(1)

        # Allow sorting on the column
        colName.set_sort_column_id(1)

        table.attach(hbbox,0,1,0,1)
        table.attach(self.treeview,0,1,1,10)

        self.set_canvas(table)
        self.show_all()


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
        # Pick an arbitrary tube we can try to download the document from
        try:
            tube_id = self.unused_download_tubes.pop()
        except (ValueError, KeyError), e:
            _logger.debug('No tubes to get the document from right now: %s', e)
            self._alert("File Download Cannot start","The tubes are clogged. Wait for empty tube")
            return False

        # Download the file at next avaialbe time.
        gobject.idle_add(self._download_document, tube_id, fileId)
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
            filelist = pickle.loads( request )
            for key in filelist:
                self._addFileToUIList(filelist[key])

        else:
            self._alert("Incoming tube Request: %s. Data: %s" % (action, request) )

    def _download_document(self, tube_id, documentId):
        _logger.debug('Requesting to download document')
        bundle_path = os.path.join(self._filepath, '%s.xoj' % documentId)

        # FIXME: should ideally have the CM listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)
        chan = self._shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        addr = iface.AcceptStreamTube(tube_id,
                telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0,
                utf8_strings=True)
        _logger.debug('Accepted stream tube: listening address is %r', addr)
        # SOCKET_ADDRESS_TYPE_IPV4 is defined to have addresses of type '(sq)'
        assert isinstance(addr, dbus.Struct)
        assert len(addr) == 2
        assert isinstance(addr[0], str)
        assert isinstance(addr[1], (int, long))
        assert addr[1] > 0 and addr[1] < 65536
        port = int(addr[1])

        getter = network.GlibURLDownloader("http://%s:%d/%s"
                                           % (addr[0], port,documentId))
        getter.connect("finished", self._download_result_cb, tube_id, documentId)
        getter.connect("progress", self._download_progress_cb, tube_id, documentId)
        getter.connect("error", self._download_error_cb, tube_id, documentId)
        _logger.debug("Starting download to %s...", bundle_path)
        #self._alert("Starting file download")
        getter.start(bundle_path)
        return False

    def _download_result_cb(self, getter, tmp_file, suggested_name, tube_id, fileId):
        _logger.debug("Got document %s (%s) from tube %u", tempfile, suggested_name, tube_id)

        bundle = journalentrybundle.JournalEntryBundle(tmp_file)
        _logger.debug("Saving %s to datastore...", tmp_file)
        self._alert( "Saving %s to datastore..."% tmp_file, timeout=500)
        bundle.install()
        self._alert( "File Downloaded", bundle.get_metadata()['title'])

    def _download_progress_cb(self, getter, bytes_downloaded, tube_id, fileId):
        # FIXME: signal the expected size somehow, so we can draw a progress
        # bar
        _logger.debug("Downloaded %u bytes from tube %u...",bytes_downloaded, tube_id)

    def _download_error_cb(self, getter, err, tube_id, fileId):
        _logger.debug("Error getting document from tube %u: %s", tube_id, err )
        self._alert("Error getting document", err)
        #gobject.idle_add(self._get_document)
