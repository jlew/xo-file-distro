import logging
import gtk
import telepathy

from sugar.activity.activity import Activity, ActivityToolbox
from sugar.graphics.objectchooser import ObjectChooser
from sugar.graphics.alert import NotifyAlert
from sugar.presence import presenceservice
from sugar.presence.tubeconn import TubeConnection

from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

SERVICE = "org.laptop.FileShare"
IFACE = SERVICE
PATH = "/org/laptop/FileShare"

class FileShareActivity(Activity):
    def requestAddFile(self, widget, data=None):
        self._logger.info('Requesting to add file')

        chooser = ObjectChooser()
        try:
            if chooser.run() == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                self.fileIndex = self.fileIndex + 1
                self._addFileToList(self.fileIndex,jobject)
                #TODO: IF SHARED, SEND NEW FILE LIST
        finally:
            chooser.destroy()
            del chooser

    def requestRemFile(self, widget, data=None):
        self._logger.info('Requesting to delete file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()
            del self.sharedFiles[model.get_value(iter, 0)]
            model.remove( iter )

    def requestDownloadFile(self, widget, data=None):
        self._logger.info('Requesting to Download file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()

            if self.fcTube:
                self.fcTube.RequestFile( model.get_value(iter, 0) )

    def _addFileToList(self, id, jObject):
        self.sharedFiles[id] = jObject
        modle = self.treeview.get_model()

        modle.append( None, [id,jObject.metadata['title'],jObject.metadata['activity_id']])

    def getFileList(self):
        return self.sharedFiles

    def _buildGui(self):
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
        self.treeview = gtk.TreeView(gtk.TreeStore(int,str,str))

        # create the TreeViewColumn to display the data
        colName = gtk.TreeViewColumn('File Name')
        colHash = gtk.TreeViewColumn('File Hash')

        self.treeview.append_column(colName)
        self.treeview.append_column(colHash)

        # create a CellRendererText to render the data
        self.cell = gtk.CellRendererText()

        # add the cell to the tvcolumn and allow it to expand
        colName.pack_start(self.cell, True)
        colHash.pack_start(self.cell, True)

        # set the cell "text" attribute- retrieve text
        # from that column in treestore
        colName.add_attribute(self.cell, 'text', 1)
        colHash.add_attribute(self.cell, 'text', 2)

        # make it searchable
        self.treeview.set_search_column(1)

        # Allow sorting on the column
        colName.set_sort_column_id(1)

        table.attach(hbbox,0,1,0,1)
        table.attach(self.treeview,0,1,1,10)

        self.set_canvas(table)
        self.show_all()

    def __init__(self, handle):
        Activity.__init__(self, handle)
        self._logger = logging.getLogger('FileShare-activity')

        self._logger.info("activity running")

        self.sharedFiles = {}
        self.fileIndex = 0

        self.set_title('File Share')
        self._buildGui()

        self.fcTube = None  # Shared session
        self.initiating = False

        # get the Presence Service
        self.pservice = presenceservice.get_instance()

        # Buddy object for you
        owner = self.pservice.get_owner()
        self.owner = owner

        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)

    def _shared_cb(self, activity):
        self._logger.debug('Activity is now shared')
        self._alert('Shared', 'The activity is shared')
        self.initiating = True
        self._sharing_setup()

        self._logger.debug('This is my activity: making a tube...')
        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
            SERVICE, {})

    def _joined_cb(self, activity):
        if not self._shared_activity:
            return

        self._logger.debug('Joined an existing shared activity')
        self._alert('Joined', 'Joined a shared activity')
        self.initiating = False
        self._sharing_setup()

        self._logger.debug('This is not my activity: waiting for a tube...')
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)




    def _sharing_setup(self):
        if self._shared_activity is None:
            self._logger.error('Failed to share or join activity')
            return

        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal('NewTube',
            self._new_tube_cb)

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)


    def _buddy_joined_cb (self, activity, buddy):
        """Called when a buddy joins the shared activity."""
        self._logger.debug('Buddy %s joined', buddy.props.nick)
        self._alert('Buddy joined', '%s joined' % buddy.props.nick)

    def _buddy_left_cb (self, activity, buddy):
        """Called when a buddy leaves the shared activity."""
        self._logger.debug('Buddy %s left', buddy.props.nick)
        self._alert('Buddy left', '%s left' % buddy.props.nick)

    def _alert(self, title, text=None):
        alert = NotifyAlert(timeout=5)
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
        self._logger.error('ListTubes() failed: %s', e)

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        self._logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                     'params=%r state=%d', id, initiator, type, service,
                     params, state)
        if (type == telepathy.TUBE_TYPE_DBUS and service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)
            tube_conn = TubeConnection(self.conn,
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES],
                id, group_iface=self.tubes_chan[telepathy.CHANNEL_INTERFACE_GROUP])
            self.fcTube = TubeSpeak(tube_conn, self.initiating,
                                      self.incomingRequest,
                                      self._alert,
                                      self._get_buddy,
                                      self.getFileList)

    def incomingRequest(self,action,request):
        self._alert("Incoming tube Request: %s. Data: %s" % (action, request) )
        pass

    def _get_buddy(self, cs_handle):
        """Get a Buddy from a channel specific handle."""
        self._logger.debug('Trying to find owner of handle %u...', cs_handle)
        group = self.tubes_chan[telepathy.CHANNEL_INTERFACE_GROUP]
        my_csh = group.GetSelfHandle()
        self._logger.debug('My handle in that group is %u', my_csh)
        if my_csh == cs_handle:
            handle = self.conn.GetSelfHandle()
            self._logger.debug('CS handle %u belongs to me, %u', cs_handle, handle)
        elif group.GetGroupFlags() & telepathy.CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
            handle = group.GetHandleOwners([cs_handle])[0]
            self._logger.debug('CS handle %u belongs to %u', cs_handle, handle)
        else:
            handle = cs_handle
            self._logger.debug('non-CS handle %u belongs to itself', handle)
            # XXX: deal with failure to get the handle owner
            assert handle != 0
        return self.pservice.get_buddy_by_telepathy_handle(
            self.conn.service_name, self.conn.object_path, handle)


class TubeSpeak(ExportedGObject):

    def __init__(self, tube, is_initiator, text_received_cb, alert, get_buddy, get_fileList):
        super(TubeSpeak, self).__init__(tube, PATH)
        self._logger = logging.getLogger('FileShare-activity.TubeSpeak')
        self.tube = tube
        self.is_initiator = is_initiator
        self.text_received_cb = text_received_cb
        self._alert = alert
        self.entered = False  # Have we set up the tube?
        self._get_buddy = get_buddy  # Converts handle to Buddy object
        self.getFileList = get_fileList
        self.tube.watch_participants(self.participant_change_cb)

    def participant_change_cb(self, added, removed):
        self._logger.debug('Tube: Added participants: %r', added)
        self._logger.debug('Tube: Removed participants: %r', removed)
        for handle, bus_name in added:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Tube: Handle %u (Buddy %s) was added',
                                   handle, buddy.props.nick)
        for handle in removed:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Buddy %s was removed' , buddy.props.nick)
        if not self.entered:
            if self.is_initiator:
                self._logger.debug("I'm initiating the tube.")
                self.add_join_handler()
            else:
                self._logger.debug('Requesting file data')
                self.announceJoin()
        self.entered = True

    @signal(dbus_interface=IFACE, signature='')
    def announceJoin(self):
        self._logger.debug('Announced join.')

    def add_join_handler(self):
        self._logger.debug('Adding join handler.')
        # Watch for announceJoin
        self.tube.add_signal_receiver(self.announceJoin_cb, 'announceJoin', IFACE,
            path=PATH, sender_keyword='sender')
        self.tube.add_signal_receiver(self.requestFile_cb, 'RequestFile', IFACE,
            path=PATH, sender_keyword='sender')

    def announceJoin_cb(self, sender=None):
        """Somebody joined."""
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('Newcomer %s has joined', sender)
        self._logger.debug('Welcoming newcomer and sending them data')

        self._alert('Newcomer %s has joined', sender)
        ##TODO THIS SHOULD BE THE FILE LIST
        self.tube.get_object(sender, PATH).FileList("File List should go here", dbus_interface=IFACE)

    def requestFile_cb(self, fileId, sender=None):
        """Somebody requested a file."""
        self._logger.debug('A file was requeted by %s' % sender)
        self.alert('A file (id: %d) was requeted by %s' % (fileId,sender) )
        ##TOD) SEND FILE
        #self.tube.get_object(sender, PATH).FileList("TEST FILE LIST", dbus_interface=IFACE)


    @method(dbus_interface=IFACE, in_signature='s', out_signature='')
    def FileList(self, fileList):
        """To be called on the incoming XO after they Hello."""
        self._logger.debug('Somebody called FileList and sent me %s', fileList)
        self._alert('FileList', 'Received %s' % fileList)
        self.text_received_cb('filelist',fileList)


    #def sendMesg_cb(self, text, sender=None):
    #    """Handler for somebody sending SendText"""
    #    if sender == self.tube.get_unique_name():
    #        # sender is my bus name, so ignore my own signal
    #        return
    #    self._logger.debug('%s sent text %s', sender, text)
    #    self._alert('sendMesg_cb', 'Received %s', text)
    #    self.text = text
    #    self.text_received_cb(text)

    @signal(dbus_interface=IFACE, signature='s')
    def RequestFile(self, fileId):
        """Send some text to all participants."""
        self.fileId = fileId
        self._logger.debug('Request File: %s' % text)
        self._alert('Reuqest File', 'Requested %s' % text)
