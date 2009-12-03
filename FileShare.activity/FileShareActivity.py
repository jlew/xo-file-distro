from sugar.activity import activity
import logging
import sys, os

import gtk

from sugar.graphics.objectchooser import ObjectChooser

class FileShareActivity(activity.Activity):
    def requestAddFile(self, widget, data=None):
        logging.info('Requesting to add file')

        chooser = ObjectChooser()
        try:
            if chooser.run() == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                self._addFileToList(jobject)

        finally:
            chooser.destroy()
            del chooser

    def requestRemFile(self, widget, data=None):
        logging.info('Requesting to delete file')
        if self.treeview.get_selection().count_selected_rows() != 0:
            model, iter = self.treeview.get_selection().get_selected()
            del self.sharedFiles[model.get_value(iter, 0)]
            model.remove( iter )


    def _addFileToList(self, jObject):
        self.sharedFiles[self.fileIndex] = jObject
        modle = self.treeview.get_model()

        modle.append( None, [self.fileIndex,jObject.metadata['title'],jObject.metadata['activity_id']])
        self.fileIndex = self.fileIndex + 1

    def _buildGui(self):
        # Create Toolbox
        ################
        toolbox = activity.ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        # Create button bar
        ###################
        hbbox = gtk.HButtonBox()
        
        addFileButton = gtk.Button("Add File")
        addFileButton.connect("clicked", self.requestAddFile, None)
        hbbox.add(addFileButton)
        
        remFileButton = gtk.Button("Remove Selected File")
        remFileButton.connect("clicked", self.requestRemFile, None)
        hbbox.add(remFileButton)

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
        activity.Activity.__init__(self, handle)

        print "activity running"

        self.sharedFiles = {}
        self.fileIndex = 0

        self.set_title('File Share')
        self._buildGui()

