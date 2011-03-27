import BaseHTTPServer
import SocketServer
import simplejson
import os
import cgi

# Version string for future protocol change as well as server verification
s_version = 2
port = 14623

class FileManager:
    """
    This class is used to hold file data for the server
    """
    def __init__(self, file_path = "shared_files"):
        self.fileList = {}
        self.userList = {}
        self.file_path = file_path
        self.load()

    def load(self):
        """
        Loads file data from __json_data.json if it exists in the
        file_path
        """
        settings_path = os.path.join(self.file_path, "__file_data.json")
        if os.path.exists( settings_path ):
            self.fileList = simplejson.loads( open( settings_path, 'r' ).read() )

        settings_path = os.path.join(self.file_path, "__user_data.json")
        if os.path.exists( settings_path ):
            self.userList = simplejson.loads( open( settings_path, 'r' ).read() )

    def save(self):
        """
        Saves the current file list into __json_data.json
        """
        settings_path = os.path.join(self.file_path, "__file_data.json")
        f = open( settings_path, 'w' )
        f.write( simplejson.dumps( self.fileList ) )
        f.close()

        settings_path = os.path.join(self.file_path, "__user_data.json")
        f = open( settings_path, 'w' )
        f.write( simplejson.dumps( self.userList ) )
        f.close()

    def add_file(self, key, dict, data):
        """
        Adds a file to the file list and saves the file to the file_path
        (data should hold the data of the file to be written)
        """
        try:
            # If new file (aka, data passed in, write file)
            path = os.path.join(self.file_path, '%s.xoj' % key)
            f = open( path, 'w' )
            f.write(data)
            f.close()

            self.fileList[key] = dict
        except:
            print "Error writing file", path

        self.save()

    def rem_file(self, key):
        """
        Deletes a file from the filepath and removes it from the list
        """
        del self.fileList[key]

        path = os.path.join(self.file_path, '%s.xoj' % key)
        try:
            os.remove( path )
        except:
            print "Unable to remove",  path
        self.save()

    def get_share_file_str(self):
        """
        Dumps a json string of the file list
        """
        return simplejson.dumps(self.fileList)

    def get_user_str(self):
        """
        Dumps a json string of the user list
        """
        return simplejson.dumps(self.userList)

    def get_file_contents(self, key):
        """
        Returns the file data based off its key
        """
        f = open( os.path.join(self.file_path, '%s.xoj' % key))
        data = f.read()
        f.close()
        return data

    def has_file_key(self, key):
        """
        Checks to see if a key is stored in the file list
        """
        return self.fileList.has_key( key )

    def user_permissions(self, id, nick):
        print "GOT USER REQUEST %s (%s)" % (nick, id)
        if self.userList.has_key(id) == False:
            permission = 0
            if len( self.userList ) == 0:
                permission = 2
            self.userList[id] = [nick, permission]
            self.save()

        if self.userList[id][0] != nick:
            self.userList[id][0] = nick
            self.save()

        return self.userList[id][1]

    def change_user_permissions(self, id, level):
        if self.userList.has_key(id):
            self.userList[id][1] = int(level)
            self.save()

    def can_rem(self, id):
        return self.userList.has_key(id) and self.userList[id][1] != 0

    def can_upload(self, id):
        return self.userList.has_key(id) and self.userList[id][1] != 0

    def can_admin(self, id):
        return self.userList.has_key(id) and self.userList[id][1] == 2


class MyServer(BaseHTTPServer.BaseHTTPRequestHandler):
    """
    Simple http server:

        Pages:
            GET:
                * /, /index.html    A page saying that the system is running
                * /version          Returns server revision number
                * /fileList         A json string of the file list
                * /{ANY_ID}         Downloads the file if the id matches
            POST:
                * /upload           Adds file (expects id, jdata and file)
                * /remove           Removes file (expects id and fid)
                * /announce_user    Adds user to list (and responds with permission level)
                                    (expects id, nick)
                * /user_list        Returns user list (expects id, must have admin permission level)
                * /user_mod         Changes user permissions (expects id (ADMIN), userId, level)
    """
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write( "FileShare.server instance running." )

        elif self.path == "/version":
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write( s_version )

        elif self.path == "/filelist":
            data = fileMan.get_share_file_str()
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'text/json')
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write( data )

        elif fileMan.has_file_key( self.path[1:] ):
            try:
                data = fileMan.get_file_contents( self.path[1:] )
                self.send_response( 200, 'OK')
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header("Content-Length",str(len(data)))
                self.end_headers()
                self.wfile.write( data )

            except IOError, err:
                self.send_error(500,'Server IO Error: %s' % str(err))
                self.end_headers()
        else:
            self.send_error(404,'File Not Found: %s' % self.path)
            self.end_headers()

    def do_POST(self):
        #http://blog.doughellmann.com/2007/12/pymotw-basehttpserver.html
        # Parse the form data posted
        form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD':'POST',
                         'CONTENT_TYPE':self.headers['Content-Type'],
                         })

        if self.path == "/upload":
            if form.has_key('id') and fileMan.can_upload( form['id'].value ):
                # Begin the response
                self.send_response(200, 'OK')
                self.end_headers()

                if( form.has_key('jdata') and form.has_key('file') ):
                    try:
                        data = simplejson.loads( form['jdata'].value )
                        file_data = form['file'].file.read()
                        fileMan.add_file(data[0], data, file_data)

                        # Begin the response
                        self.send_response(200)
                        self.end_headers()

                    except IOError, err:
                        self.send_error(500,'Server IO Error: %s' % str(err))

                    except Exception, err:
                        self.send_error(500,'Server Error or Invalid Request: %s' % str(err))
                        self.end_headers()
                return
            else:
                self.send_error(403, "Forbidden")
                self.end_headers()
        elif self.path == "/remove":
            if( form.has_key('id') and fileMan.can_rem( form['id'].value ) ):
                self.send_response(200, 'OK')
                self.end_headers()

                if( form.has_key('fid') and fileMan.has_file_key( form['fid'].value ) ):
                    fileMan.rem_file( form['fid'].value )
            else:
                self.send_error(403, "Forbidden")
                self.end_headers()

        elif self.path == "/announce_user":
            if( form.has_key('id') and form.has_key('nick') ):
                self.send_response(200, 'OK')
                self.end_headers()
                self.wfile.write( fileMan.user_permissions(form['id'].value, form['nick'].value) )
            else:
                self.send_error(400, 'Bad Request')
                self.end_headers()

        elif self.path == "/user_list":
            if form.has_key('id'):
                if fileMan.can_admin( form['id'].value ):
                    self.send_response(200, 'OK')
                    self.end_headers()
                    self.wfile.write( fileMan.get_user_str() )
                else:
                    self.send_error(403, "Forbidden")
                    self.end_headers()
            else:
                self.send_error(400, 'Bad Request')
                self.end_headers()

        elif self.path == "/user_mod":
            if form.has_key('id') and form.has_key('userid') and form.has_key('level'):
                if fileMan.can_admin( form['id'].value ):
                    if form['id'].value != form['userid'].value:
                        self.send_response(200, 'OK')
                        self.end_headers()
                        fileMan.change_user_permissions(form['userid'].value, form['level'].value)
                    else:
                        self.send_error(400, 'Bad Request, Can not modify yourself')
                        self.end_headers()
                else:
                    self.send_error(403, "Forbidden")
                    self.end_headers()
            else:
                self.send_error(400, 'Bad Request')
                self.end_headers()

        else:
            self.send_error(404,'File Not Found (POST): %s' % self.path)
            self.end_headers()




class myWebServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass



def run(server_class=BaseHTTPServer.HTTPServer, handler_class=BaseHTTPServer.BaseHTTPRequestHandler):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

if __name__ == '__main__':
    fileMan = FileManager()
    run(myWebServer, MyServer)

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()
