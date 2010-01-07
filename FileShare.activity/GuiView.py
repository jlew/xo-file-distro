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
from gettext import gettext as _

class GuiView(gtk.Table):
    """
    This class is used to just remove the table setup from the main file
    """
    def __init__(self, activity):
        gtk.Table.__init__(self, rows=10, columns=1, homogeneous=False)
        self.build_table(activity)

    def build_table(self, activity):
        # Create button bar
        ###################
        hbbox = gtk.HButtonBox()

        if activity.isServer:
            addFileButton = gtk.Button(_("Add File"))
            addFileButton.connect("clicked", activity.requestAddFile, None)
            hbbox.add(addFileButton)

            insFileButton = gtk.Button(_("Copy to Journal"))
            insFileButton.connect("clicked", activity.requestInsFile, None)
            hbbox.add(insFileButton)

            remFileButton = gtk.Button(_("Remove Selected File"))
            remFileButton.connect("clicked", activity.requestRemFile, None)
            hbbox.add(remFileButton)

        else:
            if activity._mode == 'SERVER':
                addFileButton = gtk.Button(_("Upload A File"))
                addFileButton.connect("clicked", activity.requestAddFile, {'upload':True})
                hbbox.add(addFileButton)

                remFileButton = gtk.Button(_("Remove From Server"))
                remFileButton.connect("clicked", activity.requestRemFile, {'remove':True})
                hbbox.add(remFileButton)



            downloadFileButton = gtk.Button(_("Download File"))
            downloadFileButton.connect("clicked", activity.requestDownloadFile, None)
            hbbox.add(downloadFileButton)

        # Create File Tree
        ##################
        activity.treeview = gtk.TreeView(gtk.TreeStore(str,object))

        # create the TreeViewColumn to display the data
        colName = gtk.TreeViewColumn(_('File Name'))
        colDesc = gtk.TreeViewColumn(_('Description'))
        colTags = gtk.TreeViewColumn(_('Tags'))
        colSize = gtk.TreeViewColumn(_('File Size'))
        colProg = gtk.TreeViewColumn('')

        activity.treeview.append_column(colName)
        activity.treeview.append_column(colDesc)
        activity.treeview.append_column(colTags)
        activity.treeview.append_column(colSize)
        activity.treeview.append_column(colProg)

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
        activity.treeview.set_search_column(1)

        # Allow sorting on the column
        colName.set_sort_column_id(1)

        # Allow Multiple Selections
        activity.treeview.get_selection().set_mode( gtk.SELECTION_MULTIPLE )

        # Put table into scroll window to allow it to scroll
        window = gtk.ScrolledWindow()
        window.add_with_viewport(activity.treeview)

        self.attach(hbbox,0,1,0,1)
        self.attach(window,0,1,1,10)
