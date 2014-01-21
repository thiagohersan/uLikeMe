#! /usr/bin/env python

from getopt import getopt
from sys import exit, argv
from os import remove
from threading import Thread
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
        global observerName, observerId
        data = loads(str(m))
        if('observer' in data):
            graph = graphs.queue[0]
            observerId = data['observer']
            observerName = graph.get_object(observerId)['name']
            if (isinstance(observerName, unicode)):
                observerName = observerName.encode('utf-8')

            print "got request from %s (%s)" % (observerName.decode('utf-8'), str(observerId))
            ## TODO: send something back to observer ??

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
    global userName, userId, observerName, observerId, myWebSocket
    graph = graphs.queue[0]
    if (userName is None):
        userName = graph.get_object("me")['name'].encode('utf-8')
    if (userId is None):
        userId = int(graph.get_object("me")['id'])
    if(myWebSocket is None):
        host = 'ws://ulikeme-server.herokuapp.com/client?id=%s'%(userId)
        myWebSocket = uLikeMeWebSocketClient(host, heartbeat_freq=10)
        myWebSocket.connect()
        t = Thread(target=myWebSocket.run_forever)
        t.daemon = True
        t.start()
    if((observerId is not None) and (observerName is not None)):
        print "take pic"
        postPicture()
        observerName = None
        observerId = None

def setup():
    oauthDom = minidom.parse('./oauth.xml')
    for app in oauthDom.getElementsByTagName('app'):
        secrets = {}
        secrets['APP_ID'] = app.attributes['app_id'].value
        secrets['APP_SECRET'] = app.attributes['app_secret'].value
        graphs.put(facebook.GraphAPI(setupOneApp(secrets)))

def postPicture():
    graph = graphs.queue[0]
    ## TODO: tag name of observer
    message = "%s was looking at me ..." % (observerName)

    album = graph.put_object("me", "albums", name="%s, uLikeMe (on facebook)..."%(observerName), message=message)

    posts = {}
    posts['observer'] = observerId
    posts['ids'] = []

    if(enableCamera):
        cv.SaveImage('camera.png', cv.QueryFrame(cv.CaptureFromCAM(0)))
        imgFile = open('camera.png')
        photo = graph.put_photo(image=imgFile,
                                message=message,
                                album_id=int(album['id']),
                                tags=dumps([{'x':33, 'y':33, 'tag_uid':userId}, {'x':66, 'y':66, 'tag_uid':observerId}]))
        graph.put_object(photo['id'], "likes")
        graph.put_object(photo['post_id'], "likes")
        posts['ids'].append(photo['id'])
        posts['ids'].append(photo['post_id'])
        remove('camera.png')

    if(enableScreen):
        grab(backend="pyqt").save("screen.png")
        imgFile = open('screen.png')
        photo = graph.put_photo(image=imgFile,
                                message=message,
                                album_id=int(album['id']),
                                tags=dumps([{'x':33, 'y':33, 'tag_uid':userId}, {'x':66, 'y':66, 'tag_uid':observerId}]))
        graph.put_object(photo['id'], "likes")
        graph.put_object(photo['post_id'], "likes")
        posts['ids'].append(photo['id'])
        posts['ids'].append(photo['post_id'])
        remove('screen.png')

    if(len(posts['ids']) > 0):
        myWebSocket.send(dumps(posts))

if __name__ == '__main__':
    enableScreen = False
    enableCamera = False

    try:
        opts, args = getopt(argv[1:],"sc", ["screen","camera"])
    except:
        opts = []

    if(len(opts) < 1):
        print "Usage: ./client.py [-s] [-c] [--screen] [--camera]\n(either screen or camera or both have to be enabled"
        exit(0)

    for opt,arg in opts:
        if(opt in ("--camera","-c")):
            enableCamera = True
        elif(opt in ("--screen","-s")):
            enableScreen = True

    userName = None
    userId = None
    observerName = None
    observerId = None
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
        if(myWebSocket is not None):
            myWebSocket.close()
        exit(0)
