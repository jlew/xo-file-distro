import BaseHTTPServer
import SocketServer
import simplejson
import os
import cgi

# Version string for future protocol change as well as server verification
s_version = 1
port = 14623

class FileManager:
    """
    This class is used to hold file data for the server
    """
    def __init__(self, file_path = "shared_files"):
        self.fileList = {}
        self.file_path = file_path
        self.load()

    def load(self):
        """
        Loads file data from __json_data.json if it exists in the
        file_path
        """
        settings_path = os.path.join(self.file_path, "__json_data.json")
        if os.path.exists( settings_path ):
            self.fileList = simplejson.loads( open( settings_path, 'r' ).read() )

    def save(self):
        """
        Saves the current file list into __json_data.json
        """
        settings_path = os.path.join(self.file_path, "__json_data.json")
        f = open( settings_path, 'w' )
        f.write( simplejson.dumps( self.fileList ) )
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


class MyServer(BaseHTTPServer.BaseHTTPRequestHandler):
    """
    Simple http server:

        Pages:
            * /, /index.html    A page saying that the system is running
            * /version          Returns server revision number
            * /fileList         A json string of the file list
            * /ANYFILEID        Downloads the file if the id matches
            * POST /upload      Expects an upload jdata and file
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

            except IOError:
                self.send_error(500,'Server Error')
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
            # Begin the response
            self.send_response(200)
            self.end_headers()

            if( form.has_key('jdata') and form.has_key('file') ):
                try:
                    data = simplejson.loads( form['jdata'].value )
                    file_data = form['file'].file.read()
                    fileMan.add_file(data[0], data, file_data)

                    # Begin the response
                    self.send_response(200)
                    self.end_headers()
                except:
                    self.send_error(500,'Server Error or Invalid Request')
                    self.end_headers()
            return
        elif self.path == "/remove":
            self.send_response(200)
            self.end_headers()

            print form.keys()

            if( form.has_key('id') and fileMan.has_file_key( form['id'].value ) ):
                fileMan.rem_file( form['id'].value )

        else:
            self.send_error(404,'File Not Found (POST): %s' % self.path)




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
