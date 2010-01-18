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

import logging
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

SERVICE = "org.laptop.FileShare"
IFACE = SERVICE
PATH = "/org/laptop/FileShare"

class TubeSpeak(ExportedGObject):
    def __init__(self, tube, is_initiator, text_received_cb, get_fileList):
        super(TubeSpeak, self).__init__(tube, PATH)
        self._logger = logging.getLogger('fileshare-activity.TubeSpeak')
        self.tube = tube
        self.is_initiator = is_initiator
        self.text_received_cb = text_received_cb
        self.entered = False  # Have we set up the tube?
        self.getFileList = get_fileList
        self.still_serving = True
        self.tube.watch_participants(self.participant_change_cb)

    def switch_to_server_mode(self):
        self.still_serving = False

    def participant_change_cb(self, added, removed):
        if not self.entered:
            if self.is_initiator:
                self._logger.debug("I'm initiating the tube.")
                self.add_join_handler()
            else:
                self._logger.debug('Requesting file data')
                self.add_file_change_handler()
                self.announceJoin()
        self.entered = True

    #Signals
    @signal(dbus_interface=IFACE, signature='')
    def announceJoin(self):
        self._logger.debug('Announced join.')

    @signal(dbus_interface=IFACE, signature='s')
    def FileAdd(self, addFile):
        self._logger.debug('Announced addFile.')
        self.addFile = addFile

    @signal(dbus_interface=IFACE, signature='s')
    def FileRem(self, remFile):
        self._logger.debug('Announced remFile.')
        self.remFile = remFile

    # Methods
    @method(dbus_interface=IFACE, in_signature='s', out_signature='')
    def FileList(self, fileList):
        """To be called on the incoming XO after they Hello."""
        self._logger.debug('Somebody called FileList and sent me %s', fileList)
        self.text_received_cb('filelist',fileList)

    # Handelers
    def add_join_handler(self):
        self._logger.debug('Adding join handler.')
        # Watch for announceJoin
        self.tube.add_signal_receiver(self.announceJoin_cb, 'announceJoin', IFACE,
            path=PATH, sender_keyword='sender')

    def add_file_change_handler(self):
        self._logger.debug('Adding file change handlers.')

        self.tube.add_signal_receiver(self.file_add_cb, 'FileAdd', IFACE,
            path=PATH, sender_keyword='sender')

        self.tube.add_signal_receiver(self.file_rem_cb, 'FileRem', IFACE,
            path=PATH, sender_keyword='sender')

    # Callbacks
    def announceJoin_cb(self, sender=None):
        """Somebody joined."""
        if sender == self.tube.get_unique_name() or not self.still_serving:
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('Welcoming %s and sending them data', sender)

        self.tube.get_object(sender, PATH).FileList(self.getFileList(), dbus_interface=IFACE)

    def file_add_cb(self, addFile, sender=None):
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('File Add Noticed')
        self.text_received_cb('fileadd',addFile)

    def file_rem_cb(self, remFile, sender=None):
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('File Rem Noticed')
        self.text_received_cb('filerem',remFile)
