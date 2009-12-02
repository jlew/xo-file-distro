from sugar.activity import activity
import logging
import sys, os

import gtk

class FileShareActivity(activity.Activity):
    def requestAddFile(self, widget, data=None):
        logging.info('Requesting to add file')

    def requestRemFile(self, widget, data=None):
        logging.info('Requesting to delete file')
	print "REQUEST DEL"
	print self.treeview.get_selection().get_selected()
        
    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
	
        print "activity running"
        self.set_title('File Share')
        
	# Create Toolbox
	toolbox = activity.ActivityToolbox(self)
	self.set_toolbox(toolbox)
	toolbox.show()

	# Add button to add file
	self.addFileButton = gtk.Button("Add File")
	self.addFileButton.connect("clicked", self.requestAddFile, None)

	self.remFileButton = gtk.Button("Remove Selected File")
	self.remFileButton.connect("clicked", self.requestRemFile, None)

	# Button Container
	hbbox = gtk.HButtonBox()
	hbbox.add(self.addFileButton)
	hbbox.add(self.remFileButton)

	table = gtk.Table(rows=10, columns=1, homogeneous=False)


	self.treestore = gtk.TreeStore(str)
	
	fileDisplayList = gtk.ListStore(str,int)

	for name in range(4):
	    self.treestore.append(None, ['Fake File %i' % name])

	self.treeview = gtk.TreeView(self.treestore)

	# create the TreeViewColumn to display the data
	self.tvcolumn = gtk.TreeViewColumn('Shared Files')
	self.treeview.append_column(self.tvcolumn)

	# create a CellRendererText to render the data
	self.cell = gtk.CellRendererText()

	# add the cell to the tvcolumn and allow it to expand
	self.tvcolumn.pack_start(self.cell, True)

	# set the cell "text" attribute to column 0 - retrieve text
	# from that column in treestore
	self.tvcolumn.add_attribute(self.cell, 'text', 0)
	
	# make it searchable
   	#self.treeview.set_search_column(0)

	# Allow sorting on the column
	#self.tvcolumn.set_sort_column_id(0)
	
   	# Allow drag and drop reordering of rows
   	#self.treeview.set_reorderable(True)

	table.attach(hbbox,0,1,0,1)
	table.attach(self.treeview,0,1,1,10)
	
	self.set_canvas(table)
	self.show_all()
