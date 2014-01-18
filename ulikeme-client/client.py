#! /usr/bin/env python

from sys import exit
from os import remove
from re import match, sub
from time import time, sleep
from Queue import PriorityQueue
from json import dumps, loads
from xml.dom import minidom
from urllib2 import urlopen
from urllib import urlencode
from urlparse import parse_qs, urlparse
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from ws4py.client.threadedclient import WebSocketClient
from cv2 import cv
from pyscreenshot import grab
import webbrowser
import facebook

class uLikeMeWebSocketClient(WebSocketClient):
    def opened(self):
        print "WebSocket opened"

    def closed(self, code, reason=None):
        print "WebSocket closed: %s %s" %(code, reason)

    def received_message(self, m):
        data = loads(str(m))
        if('observer' in data):
            graph = graphs.queue[0]
            print "got request from %s" % (data['observer'])
            print "aka. %s" % graph.get_object(data['observer'])['name']
            ## TODO:
            ##     1. get info and post to FB (postPicture())
            ##     2. send something back to observer ??

def get_url(path, args=None):
    endpoint = 'graph.facebook.com'
    args = args or {}
    if 'access_token' in args or 'client_secret' in args:
        endpoint = "https://"+endpoint
    else:
        endpoint = "http://"+endpoint
    return endpoint+path+'?'+urlencode(args)

def get(path, args=None):
    return urlopen(get_url(path=path, args=args)).read()

def setupOneApp(secrets):
    secrets['REDIRECT_URI'] = 'http://127.0.0.1:8080/'

    class FacebookRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
     
            code = parse_qs(urlparse(self.path).query).get('code')
            code = code[0] if code else None

            if code is None:
                self.wfile.write("Sorry, authentication failed.")
                return

            response = get('/oauth/access_token', {'client_id':secrets['APP_ID'],
                                                   'redirect_uri':secrets['REDIRECT_URI'],
                                                   'client_secret':secrets['APP_SECRET'],
                                                   'code':code})
            secrets['ACCESS_TOKEN'] = parse_qs(response)['access_token'][0]

            self.wfile.write("You have successfully logged in to facebook. "
                             "You can close this window now.")

    httpd = HTTPServer(('127.0.0.1', 8080), FacebookRequestHandler)

    print "Logging you in to facebook..."
    webbrowser.open(get_url('/oauth/authorize', {'client_id':secrets['APP_ID'],
                                                 'redirect_uri':secrets['REDIRECT_URI'],
                                                 'scope':'read_stream,publish_actions,publish_stream,photo_upload,user_photos,status_update'}))

    while not 'ACCESS_TOKEN' in secrets:
        httpd.handle_request()

    return secrets['ACCESS_TOKEN']

def loop():
    global userName, userId, myWebSocket
    graph = graphs.queue[0]
    if (userName is None):
        userName = str(graph.get_object("me")['name'])
    if (userId is None):
        userId = int(graph.get_object("me")['id'])
    if(myWebSocket is None):
        host = 'ws://ulikeme-server.herokuapp.com/client?id=%s'%(userId)
        myWebSocket = uLikeMeWebSocketClient(host, heartbeat_freq=10)
        myWebSocket.connect()
        myWebSocket.run_forever()

def setup():
    oauthDom = minidom.parse('./oauth.xml')
    for app in oauthDom.getElementsByTagName('app'):
        secrets = {}
        secrets['APP_ID'] = app.attributes['app_id'].value
        secrets['APP_SECRET'] = app.attributes['app_secret'].value
        graphs.put(facebook.GraphAPI(setupOneApp(secrets)))

def postPicture():
    graph = graphs.queue[0]
    message = "%s was looking at me ..." % ('observer')

    ## TODO: fix this
    cv.SaveImage('camera.png', cv.QueryFrame(cv.CaptureFromCAM(0)))
    grab(backend="pyqt").save("screen.png")

    imgFile = open('camera.png')
    photo = graph.put_photo(image=imgFile,
                            message=message,
                            ## album_id=int(album['id']),
                            tags=dumps([{'x':50, 'y':50, 'tag_uid':userId}]))
    graph.put_object(photo['id'], "likes")
    graph.put_object(photo['post_id'], "likes")
    remove('camera.png')
    remove('screen.png')

if __name__ == '__main__':
    userName = None
    userId = None
    myWebSocket = None
    graphs = PriorityQueue()
    setup()

    try:
        while(True):
            ## keep it from looping faster than ~60 times per second
            loopStart = time()
            loop()
            loopTime = time()-loopStart
            if (loopTime < 0.016):
                sleep(0.016 - loopTime)
        exit(0)
    except KeyboardInterrupt:
        if(not myWebSocket is None):
            myWebSocket.close()
        exit(0)
