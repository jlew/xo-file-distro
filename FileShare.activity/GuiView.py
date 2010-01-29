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


from sugar.activity.activity import ActivityToolbox
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.objectchooser import ObjectChooser
from sugar.graphics.alert import NotifyAlert, Alert

from MyExceptions import InShareException, FileUploadFailure, ServerRequestFailure, NoFreeTubes
import logging
_logger = logging.getLogger('fileshare-activity')

class GuiHandler():
    def __init__(self, activity, tree, handle):
        self.activity = activity
        self.treeview = tree
        self.tb_alert = None
        self.guiView = handle

    def requestAddFile(self, widget, data=None):
        _logger.info('Requesting to add file')

        chooser = ObjectChooser()
        if chooser.run() == gtk.RESPONSE_ACCEPT:
            # get object and build file
            jobject = chooser.get_selected_object()

            self.show_throbber(True, _("Packaging Object") )
            try:
                file_obj = self.activity.build_file( jobject )
            except InShareException:
                self._alert(_("Object Not Added"), _("Object already shared"))
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
                self.show_throbber(True, _("Uploading Object to server"))
                def send():
                    try:
                        self.activity.send_file_to_server( file_obj.id, file_obj )
                    except FileUploadFailure:
                        self._alert( _("Failed to upload object") )
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
                    self.show_throbber(True, _("Sending request to server"))
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
                        self._alert(_("Object has already or is currently being downloaded"))
                threading.Thread(target=do_down).start()
        else:
            self._alert(_("You must select an object to download"))


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



    def show_throbber(self, show, mesg="", addon=None):
        if show:
            #Build Throbber
            throbber = gtk.VBox()
            img = gtk.Image()
            img.set_from_file('throbber.gif')
            throbber.pack_start(img)
            throbber.pack_start(gtk.Label(mesg))

            if addon:
                throbber.pack_start( addon )

            self.activity.set_canvas(throbber)
            self.activity.show_all()

            self.activity.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            self.activity.set_sensitive(False)

        else:
            self.activity.set_canvas(self.activity.disp)
            self.activity.show_all()

            self.activity.window.set_cursor(None)
            self.activity.set_sensitive(True)

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

    def switch_to_server(self, widget, data=None):
        self.activity.switch_to_server()

    def showAdmin(self, widget, data=None):
        def call():
            try:
                userList = self.activity.get_server_user_list()
            except ServerRequestFailure:
                self._alert(_("Failed to get user list from server"))
                self.show_throbber( False )
            else:
                self.show_throbber( False )
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
                window.set_policy( gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC )
                window.add_with_viewport(listbox)

                myTable.attach(hbbox,0,1,0,1)
                myTable.attach(window,0,1,1,10)

                self.lockout_action_menu(True)
                self.activity.set_canvas(myTable)
                self.activity.show_all()

        self.show_throbber(True, _("Requesting user list from server"))
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
        self.lockout_action_menu(False)
        self.activity.set_canvas(self.activity.disp)
        #self.show_throbber( False )

    def lockout_action_menu(self, set_lock = True):
        self.guiView.action_bar.set_sensitive(not set_lock)

class GuiView(gtk.ScrolledWindow):
    """
    This class is used to just remove the table setup from the main file
    """
    def __init__(self, activity):
        gtk.ScrolledWindow.__init__(self)
        self.set_policy( gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC )
        self.activity = activity
        self.treeview = gtk.TreeView(gtk.TreeStore(str,object))
        self.guiHandler = GuiHandler( activity, self.treeview, self )
        #self.build_table(activity)

    def build_toolbars(self):
        self.action_buttons = {}

        # BUILD CUSTOM TOOLBAR
        self.action_bar = gtk.Toolbar()
        self.action_buttons['add'] = ToolButton('fs_gtk-add')
        self.action_buttons['add'].set_tooltip(_("Add Object"))

        self.action_buttons['rem'] = ToolButton('fs_gtk-remove')
        self.action_buttons['rem'].set_tooltip(_("Remove Object(s)"))

        self.action_buttons['save'] = ToolButton('filesave')
        self.action_buttons['save'].set_tooltip( _("Copy Object(s) to Journal") )


        self.action_buttons['down'] = ToolButton('epiphany-download')
        self.action_buttons['down'].set_tooltip( _('Download Object(s)') )

        self.action_buttons['admin'] = ToolButton('gtk-network')
        self.action_buttons['admin'].set_tooltip( _('Server Permissions') )

        self.action_buttons['server'] = ToolButton('gaim-link')
        self.action_buttons['server'].set_tooltip( _('Connect to Server') )
        self.action_buttons['server'].set_sensitive( False )

        if self.activity.isServer:
            self.action_buttons['add'].connect("clicked", self.guiHandler.requestAddFile, None)
            self.action_buttons['save'].connect("clicked", self.guiHandler.requestInsFile, None)
            self.action_buttons['rem'].connect("clicked", self.guiHandler.requestRemFile, None)
            self.action_buttons['server'].connect("clicked", self.guiHandler.switch_to_server, None)

            self.action_bar.insert(self.action_buttons['add'], -1)
            self.action_bar.insert(self.action_buttons['save'], -1)
            self.action_bar.insert(self.action_buttons['rem'], -1)
            self.action_bar.insert(self.action_buttons['server'], -1)

            # Check for server, if found activate connect link
            def check_server_status():
                try:
                    if self.activity.check_for_server():
                        self.action_buttons['server'].set_sensitive( True )
                except ServerRequestFailure:
                    pass
            threading.Thread(target=check_server_status).start()

        else:
            self.action_buttons['down'].connect("clicked", self.guiHandler.requestDownloadFile, None)
            self.action_bar.insert(self.action_buttons['down'], -1)

            if self.activity._mode == 'SERVER' and self.activity._user_permissions != 0:
                self.action_buttons['add'].connect("clicked", self.guiHandler.requestAddFile, {'upload':True})
                self.action_buttons['rem'].connect("clicked", self.guiHandler.requestRemFile, {'remove':True})

                self.action_bar.insert(self.action_buttons['add'], -1)
                self.action_bar.insert(self.action_buttons['rem'], -1)

                if self.activity._user_permissions == 2:
                    self.action_buttons['admin'].connect("clicked", self.guiHandler.showAdmin, None)
                    self.action_bar.insert(self.action_buttons['admin'], -1)

        self.action_bar.show_all()

        self.toolbar_set_selection( False )

        # Create Toolbox
        self.toolbox = ActivityToolbox(self.activity)

        self.toolbox.add_toolbar(_("Actions"), self.action_bar)

        self.activity.set_toolbox(self.toolbox)
        self.toolbox.show()
        self.toolbox.set_current_toolbar(1)

    def on_selection_changed(self, selection):
        if selection.count_selected_rows() == 0:
            self.toolbar_set_selection(False)
        else:
            self.toolbar_set_selection(True)

    def toolbar_set_selection(self, selected):
        require_selection = ['save', 'rem', 'down']
        for key in require_selection:
            if selected:
                self.action_buttons[key].set_sensitive( True )
            else:
                self.action_buttons[key].set_sensitive( False )

    def build_table(self):
        # Create File Tree
        ##################

        #       Name            Cell_data_Func      Expand  Cell Renderer
        text_cells = [
            [ _('Name'),   FileInfo.file_name, False,  gtk.CellRendererText()],
            [ _('Description'), FileInfo.file_desc, True,   gtk.CellRendererText()],
            [ _('Tags'),        FileInfo.file_tags, False,  gtk.CellRendererText()],
            [ _('Size'),   FileInfo.file_size, False,  gtk.CellRendererText()],
            [ '',               FileInfo.load_bar,  False,  gtk.CellRendererProgress()]
        ]

        for col_data in text_cells:
            cell = col_data[3]
            colName = gtk.TreeViewColumn(col_data[0], cell)
            colName.set_cell_data_func(cell, col_data[1])

            # Should the col expand
            colName.set_expand(col_data[2])

            # Add to tree
            self.treeview.append_column(colName)

        # make it searchable by name
        self.treeview.set_search_column(1)

        # Allow Multiple Selections
        self.treeview.get_selection().set_mode( gtk.SELECTION_MULTIPLE )
        self.treeview.get_selection().connect('changed', self.on_selection_changed )

        # Put table into scroll window to allow it to scroll
        self.add_with_viewport(self.treeview)

    def clear_files(self, deleteFile = True):
        model = self.treeview.get_model()
        iter = model.get_iter_root()
        while iter:
            key = model.get_value(iter, 0)

            # Remove file from UI
            self.guiHandler._remFileFromUIList(key)

            # UnRegister File with activity share list
            self.activity._unregisterShareFile( key )

            # Attempt to remove file from system
            if deleteFile:
                self.activity.delete_file( key )

            iter = model.iter_next(iter)

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
