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

from gettext import gettext as _

class FileInfo(object):
    def __init__(self, id, title, desc, tags, size, have_file = False):
        self.id = id
        self.title = title
        self.desc = desc
        self.tags = tags
        self.size = size
        self.had_file = have_file
        self.installed = have_file

        if have_file:
            self.aquired = size
            self.percent = 100
            self.status = _("Shared")
        else:
            self.aquired = 0
            self.percent = 0
            self.status = _("Pending")

    def have_file(self):
        if self.size == self.aquired:
            return True
        else:
            return False

    def update_aquired(self, aquired_size):
        self.aquired = aquired_size
        self.percent = (float(aquired_size)/float(self.size))*100.0
        if self.aquired == self.size:
            self.status = _("File Downloaded, Installing...")
        else:
            self.status="%s %d%% (%d %s)"%(_("Downloading"), self.percent, aquired_size, _("bytes"))

    def set_installed(self):
        self.status = _("Download Complete")
        self.aquired = self.size
        self.installed = True

    def set_failed(self):
        self.status = _("Download Failed")
        self.aquired = 0
        self.installed = False

    def share_dump(self):
        return [self.id, self.title, self.desc, self.tags, self.size]

def share_load(list, has_file = False):
    return FileInfo(list[0], list[1], list[2], list[3], list[4], has_file)


# Gui Tree View Stuff
def file_name(column, cell, model, iter):
    cell.set_property('text', model.get_value(iter, 1).title)
    return

def file_desc(column, cell, model, iter):
    cell.set_property('text', model.get_value(iter, 1).desc)
    return

def file_tags(column, cell, model, iter):
    cell.set_property('text', model.get_value(iter, 1).tags)
    return

def file_size(column, cell, model, iter):
    cell.set_property('text', model.get_value(iter, 1).size)
    return

def load_bar(column, cell, model, iter):
    obj = model.get_value(iter, 1)
    cell.set_property('text', obj.status)
    cell.set_property('value', obj.percent)
    return
