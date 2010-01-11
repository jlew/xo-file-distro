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
import FileInfo
import threading
from gettext import gettext as _

from sugar.graphics.objectchooser import ObjectChooser
from sugar.graphics.alert import NotifyAlert

from MyExceptions import InShareException, FileUploadFailure, ServerRequestFailure, NoFreeTubes
import logging
_logger = logging.getLogger('fileshare-activity')




class GuiHandler():
    def __init__(self, activity, tree):
        self.activity = activity
        self.treeview = tree

    def requestAddFile(self, widget, data=None):
        _logger.info('Requesting to add file')

        chooser = ObjectChooser()
        if chooser.run() == gtk.RESPONSE_ACCEPT:
            # get object and build file
            jobject = chooser.get_selected_object()

            self.show_throbber(True, _("Please Wait... Packaging File") )
            try:
                file_obj = self.activity.build_file( jobject )
            except InShareException:
                self._alert(_("File Not Added"), _("File already shared"))
                self.show_throbber( False )
                return

            # No problems continue
            self.show_throbber( False )

            # Add To UI
            self._addFileToUIList( file_obj.id, file_obj )

            # Register File with activity share list
            self.activity._registerShareFile( file_obj.id, file_obj )

            # Upload to server?
            if data and data.has_key('upload'):
                self.show_throbber(True, _("Please Wait... Uploading file to server"))
                def send():
                    try:
                        self.activity.send_file_to_server( file_obj.id, file_obj )
                    except FileUploadFailure:
                        self._alert( _("Failed to upload file") )
                        self._remFileFromUIList( file_obj.id )
                        self.activity.delete_file( file_obj.id )
                    self.show_throbber( False )
                threading.Thread(target=send).start()

        chooser.destroy()
        del chooser

    def requestInsFile(self, widget, data=None):
        _logger.info('Requesting to install file back to journal')

        model, iterlist = self.treeview.get_selection().get_selected_rows()
        for path in iterlist:
            iter = model.get_iter(path)
            key = model.get_value(iter, 0)

            # Attempt to remove file from system
            bundle_path = os.path.join(self._filepath, '%s.xoj' % key)

            self.activity._installBundle( bundle_path )
            self._alert(_("Installed bundle to Jorunal"))

    def requestRemFile(self, widget, data=None):
        """Removes file from memory then calls rem file from ui"""
        _logger.info('Requesting to delete file')

        model, iterlist = self.treeview.get_selection().get_selected_rows()
        for path in iterlist:
            iter = model.get_iter(path)
            key = model.get_value(iter, 0)

            # DO NOT DELETE IF TRANSFER IN PROGRESS/COMPLETE
            if model.get_value(iter, 1).aquired == 0 or self.activity.server_ui_del_overide():

                # Remove file from UI
                self._remFileFromUIList(key)

                # UnRegister File with activity share list
                self.activity._unregisterShareFile( key )

                # Attempt to remove file from system
                self.activity.delete_file( key )

                # If added by rem from server button, data will have remove key
                if data and data.has_key('remove'):
                    def call():
                        try:
                            self.activity.remove_file_from_server( key )
                        except ServerRequestFailure:
                            self._alert( _("Failed to send remove request to server") )
                        self.show_throbber( False )
                    self.show_throbber(True, _("Please Wait... Sending request to server"))
                    threading.Thread(target=call).start()

    def requestDownloadFile(self, widget, data=None):
        _logger.info('Requesting to Download file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iterlist = self.treeview.get_selection().get_selected_rows()
            for path in iterlist:
                iter = model.get_iter(path)
                fi = model.get_value(iter, 1)
                def do_down():
                    if fi.aquired == 0:
                        if self.activity._mode == 'SERVER':
                            self.activity._server_download_document( str( model.get_value(iter, 0)) )
                        else:
                            try:
                                self.activity._get_document(str( model.get_value(iter, 0)))
                            except NoFreeTubes:
                                self._alert(_("All tubes are busy, file download cannot start"),_("Please wait and try again"))
                    else:
                        self._alert(_("File has already or is currently being downloaded"))
                threading.Thread(target=do_down).start()
        else:
            self._alert(_("You must select a file to download"))


    def _addFileToUIList(self, fileid, fileinfo):
        modle = self.treeview.get_model()
        modle.append( None, [fileid, fileinfo])

    def _remFileFromUIList(self, id):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
            if model.get_value( iter, 0 ) == id:
                break
            iter = model.iter_next( iter )
        model.remove( iter )



    def show_throbber(self, show, mesg=""):
        if show:
            #Build Throbber
            throbber = gtk.VBox()
            img = gtk.Image()
            img.set_from_file('throbber.gif')
            throbber.pack_start(img)
            throbber.pack_start(gtk.Label(mesg))

            self.activity.set_canvas(throbber)
            self.activity.show_all()
        else:
            self.activity.set_canvas(self.activity.disp)
            self.activity.show_all()

        while gtk.events_pending():
            gtk.main_iteration()

    def _alert(self, title, text=None, timeout=5):
        alert = NotifyAlert(timeout=timeout)
        alert.props.title = title
        alert.props.msg = text
        self.activity.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.activity.remove_alert(alert)

    def showAdmin(self, widget, data=None):
        def call():
            try:
                userList = self.activity.get_server_user_list()

            except ServerRequestFailure:
                    self._alert(_("Failed to get user list from server"))
                    self.show_throbber( False )
            else:
                level = [_("Download Only"), _("Upload/Remove"), _("Admin")]

                myTable = gtk.Table(10, 1, False)
                hbbox = gtk.HButtonBox()
                returnBut = gtk.Button(_("Return to Main Screen"))
                returnBut.connect("clicked",self.restore_view, None)
                hbbox.add(returnBut)

                listbox = gtk.VBox()

                for key in userList:
                    holder = gtk.HBox()
                    label = gtk.Label(userList[key][0])
                    label.set_alignment(0, 0)
                    holder.pack_start(label)

                    if key == self.activity._user_key_hash:
                        mode_box = gtk.Label(level[userList[key][1]])
                        mode_box.set_alignment(1,0)
                    else:
                        mode_box = gtk.combo_box_new_text()
                        for option in level:
                            mode_box.append_text( option )

                        mode_box.set_active(userList[key][1])
                        mode_box.connect("changed", self.user_changed, key)

                    holder.pack_start(mode_box, False, False, 0)
                    listbox.pack_start(holder, False, False, 0)

                window = gtk.ScrolledWindow()
                window.add_with_viewport(listbox)

                myTable.attach(hbbox,0,1,0,1)
                myTable.attach(window,0,1,1,10)

                self.activity.set_canvas(myTable)
                self.activity.show_all()

        self.show_throbber(True, _("Please Wait... Requesting user list from server"))
        threading.Thread(target=call).start()


    def user_changed(self, widget, id):
        widget.set_sensitive(False)
        def change():
            try:
                self.activity.change_server_user(id, widget.get_active())
                widget.set_sensitive(True)
            except ServerRequestFailure:
                parent = widget.get_parent()
                parent.remove(widget)
                lbl = gtk.Label(_("User Change Failed"))
                lbl.set_alignment(1,0)
                lbl.show()
                parent.add( lbl )

        threading.Thread(target=change).start()

    def restore_view(self, widget, data = None):
        self.show_throbber( False )


class GuiView(gtk.Table):
    """
    This class is used to just remove the table setup from the main file
    """
    def __init__(self, activity):
        gtk.Table.__init__(self, rows=10, columns=1, homogeneous=False)
        self.activity = activity
        self.treeview = gtk.TreeView(gtk.TreeStore(str,object))
        self.guiHandler = GuiHandler( activity, self.treeview )
        self.build_table(activity)

    def build_table(self, activity):
        # Create button bar
        ###################
        hbbox = gtk.HButtonBox()

        if activity.isServer:
            addFileButton = gtk.Button(_("Add File"))
            addFileButton.connect("clicked", self.guiHandler.requestAddFile, None)
            hbbox.add(addFileButton)

            insFileButton = gtk.Button(_("Copy to Journal"))
            insFileButton.connect("clicked", self.guiHandler.requestInsFile, None)
            hbbox.add(insFileButton)

            remFileButton = gtk.Button(_("Remove Selected File"))
            remFileButton.connect("clicked", self.guiHandler.requestRemFile, None)
            hbbox.add(remFileButton)

        else:
            if activity._mode == 'SERVER' and activity._user_permissions != 0:
                addFileButton = gtk.Button(_("Upload A File"))
                addFileButton.connect("clicked", self.guiHandler.requestAddFile, {'upload':True})
                hbbox.add(addFileButton)

                remFileButton = gtk.Button(_("Remove From Server"))
                remFileButton.connect("clicked", self.guiHandler.requestRemFile, {'remove':True})
                hbbox.add(remFileButton)

                if activity._user_permissions == 2:
                    adminButton = gtk.Button(_("Server Settings"))
                    adminButton.connect("clicked", self.guiHandler.showAdmin, None)
                    hbbox.add(adminButton)

            downloadFileButton = gtk.Button(_("Download File"))
            downloadFileButton.connect("clicked", self.guiHandler.requestDownloadFile, None)
            hbbox.add(downloadFileButton)

        # Create File Tree
        ##################

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
        colName.set_cell_data_func(cell, FileInfo.file_name)
        colDesc.set_cell_data_func(cell, FileInfo.file_desc)
        colTags.set_cell_data_func(cell, FileInfo.file_tags)
        colSize.set_cell_data_func(cell, FileInfo.file_size)
        colProg.set_cell_data_func(pbar, FileInfo.load_bar)

        # make it searchable
        self.treeview.set_search_column(1)

        # Allow sorting on the column
        colName.set_sort_column_id(1)

        # Allow Multiple Selections
        self.treeview.get_selection().set_mode( gtk.SELECTION_MULTIPLE )

        # Put table into scroll window to allow it to scroll
        window = gtk.ScrolledWindow()
        window.add_with_viewport(self.treeview)

        self.attach(hbbox,0,1,0,1)
        self.attach(window,0,1,1,10)

    def update_progress(self, id, bytes ):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
            if model.get_value( iter, 0 ) == id:
                break
            iter = model.iter_next( iter )

        if iter:
            obj = model.get_value( iter, 1 )
            obj.update_aquired( bytes )

            # Store updated versoin of the object
            self.activity.updateFileObj( id, obj )
            model.set_value( iter, 1, obj)

            model.row_changed(model.get_path(iter), iter)

    def set_installed( self, id, sucessful=True ):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
            if model.get_value( iter, 0 ) == id:
                break
            iter = model.iter_next( iter )

        if iter:
            obj = model.get_value( iter, 1 )
            if sucessful:
                obj.set_installed()
            else:
                obj.set_failed()

            # Store updated versoin of the object
            self.activity.updateFileObj( id, obj )
            model.set_value( iter, 1, obj)
            model.row_changed(model.get_path(iter), iter)
