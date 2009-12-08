import logging
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

SERVICE = "org.laptop.FileShare"
IFACE = SERVICE
PATH = "/org/laptop/FileShare"

class TubeSpeak(ExportedGObject):
    def __init__(self, tube, is_initiator, text_received_cb, alert, get_fileList):
        super(TubeSpeak, self).__init__(tube, PATH)
        self._logger = logging.getLogger('fileshare-activity.TubeSpeak')
        self.tube = tube
        self.is_initiator = is_initiator
        self.text_received_cb = text_received_cb
        self._alert = alert
        self.entered = False  # Have we set up the tube?
        self.getFileList = get_fileList
        self.tube.watch_participants(self.participant_change_cb)

    def participant_change_cb(self, added, removed):
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

    def announceJoin_cb(self, sender=None):
        """Somebody joined."""
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('Welcoming %s and sending them data' % sender)

        self.tube.get_object(sender, PATH).FileList(self.getFileList(), dbus_interface=IFACE)

    @method(dbus_interface=IFACE, in_signature='s', out_signature='')
    def FileList(self, fileList):
        """To be called on the incoming XO after they Hello."""
        self._logger.debug('Somebody called FileList and sent me %s' % fileList)
        self.text_received_cb('filelist',fileList)
