import bayeux_constants
import collections
import json
import logging
import zope.interface
from threading import Timer, Thread, RLock
from twisted.internet import reactor
from bayeux_message_receiver import BayeuxMessageReceiver
from bayeux_message_sender import BayeuxMessageSender

from interfaces import IMessengerService

class BayeuxClient(object):
    zope.interface.implements(IMessengerService)
    """Client that implements the bayeux protocol.

    User of this class should call register to register for 
    particular events and then call start to start the client.

    Attributes:
        server: The remote bayeux server to connect to
        receiver: The bayeux message receiver
        sender: The bayeux message sender
        timer: A timer used to retry messaging in cases of errors
        retry_connect_count: Counter for the number of connect retries
        connect_interval: Interval for the connect message in seconds
        is_handshook: Whether or not we have made a successful handshake request
        subscriptions: Set of active subscriptions
        lock: Concurrency lock
    """
    def __init__(self, server):
        """Initialize the client.

        Args:
            server: The remote bayeux server to connect this client to 
                    (e.g. 'http://1.1.1.1:8080/bayeux')
        """
        self.server = server
        self.timer = None
        self.retry_connect_count = 0
        self.connect_interval = 0
        self.receiver = BayeuxMessageReceiver()
        self.is_handshook = False
        self.started = False
        self.destroyed = False
        self.connected = False
        self.subscriptions = set()
        self.lock = RLock()
        self.sender = BayeuxMessageSender(self.server, self.receiver)
        self.receiver.register(bayeux_constants.HANDSHAKE_CHANNEL, 
            self._handshake_cb)
        self.receiver.register(bayeux_constants.CONNECT_CHANNEL, 
            self._connect_cb)
        self.receiver.register(bayeux_constants.DISCONNECT_CHANNEL, 
            self._disconnect_cb)

    def destroy(self):
        """Destroys the client.

        This stops the Twisted Reactor. Once this is called the reactor 
        can no longer be started. Should call this prior to exiting the 
        application.
        """
        with self.lock:
            self.destroyed = True
            if reactor.running:
                if self.started and self.connected:
                    #Currently running and connected so issue a disconnect
                    self.sender.disconnect(self._disconnect_error)
                elif not self.started and self.connected:
                    #There is a pending disconnect so 
                    #wait for response
                    pass
                else:
                    #Not connected so just stop reactor
                    self._stop_reactor()

    def start(self):
        #TODO Take daemon in as arg
        """Starts the client. This methods spawns a new thread to perform 
        messaging tasks.

        The client is started by issuing a handshake request to the server. 
        Once the response for the handshake request is received, maintains 
        the connection to the server by issuing periodic connect requests.
        """
        with self.lock:
            if not self.started:
                #Start up the new thread where the reactor runs
                self.started = True
                self.connected = False
                if not reactor.running:
                    thread = Thread(name='BayeuxClient-Thread',
                        target=reactor.run, 
                        args=(False,))
                    thread.daemon = True
                    thread.start()
                self.sender.handshake(self._handshake_error)
            else:
                #Client already running
                logging.info('Client already running')

    def stop(self):
        """Stops the client.

        The client is stopped by stopping any current connect requests and 
        issuing a disconnect request to the server. 
        """
        with self.lock:
            if self.started:
                self.is_handshook = False
                self.started = False
                self.retry_connect_count = 0
                if self.timer is not None:
                    self.timer.cancel()
                    self.timer = None
                self.sender.disconnect(self._disconnect_error)
            else:
                #Client not running
                logging.info('Client not running')

    def register(self, id, callback):
        """Subscribe for a particular event.

        Args:
            id: The event to subscribe to (e.g. '/foo/bar')
            callback: The callback to trigger upon receipt of the message
        """
        with self.lock:
            if self.is_handshook:
                if id not in self.subscriptions:
                    #Already connected so subscribe for this new event
                    self.subscriptions.add(id)
                    if self.started:
                        self.sender.subscribe(id) #TODO Handle error case
                else:
                    #Event already subscribed for so don't need to do anything
                    pass
            else:
                #Not yet connected so just add to our subscription list. 
                #The subscription list will be used to subscribe once we are
                #connected.
                self.subscriptions.add(id)
            self.receiver.register(id, callback)

    def deregister(self, id, callback):
        """Unsubscribe from a particular event.

        Args:
            id: The event to unsubscribe from
            callback: The callback to unsubscribe
        """
        with self.lock:
            if self.receiver.deregister(id, callback) == 0:
                #No more listeners for this event to unsubscribe from the 
                #server
                self.subscriptions.remove(id)
                if self.started:
                    self.sender.unsubscribe(id)

    def _connect_cb(self, data):
        """Callback for the connect message.

        If this connect message succeeded, then issue another
        connect mesasge based on the interval value in the
        connect response message. The connect messsage acts
        as a heartbeat to the bayeux server. If the connect
        message failed, then try and restart the client again.

        Args:
            data: The connect response data
        """
        logging.debug('_connect_cb: %s' % data)        
        with self.lock:
            if self.started:
                if(data['successful']):
                    self.retry_connect_count = 0
                    self.connected = True
                    if('advice' in data and 'interval' in 
                    data['advice'] and 
                    data['advice']['interval']):
                        #The interval defines how often we need to ping on the 
                        #server with a connect message to keep the connection 
                        #alive
                        self.connect_interval = int(
                            data['advice']['interval']) / 1000
                    self.timer = Timer(self.connect_interval,
                        self.sender.connect, [self._connect_error])
                    self.timer.start()

    def _connect_error(self, reason):
        """Callback if there is an error during the connect request message.

        If there was an error sending the connect message, retry a few times 
        before trying to restart the client again.

        Args:
            reason: The reason that the connect failed
        """
        logging.debug('_connect_error: %s' % reason)
        with self.lock:
            if self.started:
                self.retry_connect_count += 1
                self.connected = False
                if(self.retry_connect_count < 
                    bayeux_constants.CONNECT_FAILURE_THRESHOLD):
                    logging.warning('Trying to reconnect')
                    self.timer = Timer(self.connect_interval, 
                        self.sender.connect, [self._connect_error])
                    self.timer.start()
                else:
                    logging.warning('Failed trying to reconnect...resend handshake request')
                    #Consider this a failed connection and go back to retrying 
                    #handshakes
                    self.is_handshook = False
                    self.retry_connect_count = 0
                    self.sender.handshake(self._handshake_error)

    def _disconnect_cb(self, data):
        """Callback for the disconnect message.
        
        Stops the reactor upon disconnecting from the server.

        Args:
            data: The disconnect response data
        """
        logging.debug('_disconnect_cb: %s' % data)
        with self.lock:
            self.connected = False
            if self.destroyed:
                self._stop_reactor()

    def _disconnect_error(self, reason):
        """Callback if there is an error during the disconnect
        request message.
    
        Args:
            reason: The reason the disconnect failed
        """
        logging.debug('_disconnect_error: %s' % reason)
        with self.lock:
            self.connected = False
            if self.destroyed:
                self._stop_reactor()

    def _handshake_cb(self, data):
        """Callback for the handshake message.
        
        If the callback succeeded, then update the client id in the sender and
        begin issuing connect requests. If the handshake failed, the resend 
        the handshake request after a given timeout.

        Args:
            data: The handshake response data
        """
        logging.debug('_handshake_cb: %s' % data)
        with self.lock:
            if self.started and not self.destroyed:
                if(data['successful']):
                    self.is_handshook = True
                    self.sender.set_client_id(
                        data['clientId'])
                    self.sender.connect(
                        self._connect_error)
                    #On a successful handshake register for pending subscriptions
                    for event in self.subscriptions:
                        #TODO Handle error case
                        self.sender.subscribe(event)
                else:
                    #Connect was not successful for some reason, try again
                    self.is_handshook = False
                    self.timer = Timer(bayeux_constants.HANDSHAKE_RETRY_INTERVAL,
                        self.sender.handshake, [self._handshake_error])
                    self.timer.start()

    def _handshake_error(self, reason):
        """Callback if there is an error during the handshake
        request message.

        If there was an error sending the handshake message, then wait and 
        retry the message until we are able to connect.

        Args:
            reason: The reason that the handshake failed
        """
        with self.lock:
            if self.started and not self.destroyed:
                logging.warning(''.join(['Error sending handshake request',
                    'message...retrying in ', 
                    str(bayeux_constants.HANDSHAKE_RETRY_INTERVAL),
                    ' secs']))                
                self.is_handshook = False
                self.timer = Timer(bayeux_constants.HANDSHAKE_RETRY_INTERVAL,
                    self.sender.handshake, [self._handshake_error])
                self.timer.start()

    def _stop_reactor(self):
        """Helper method to stop the reactor"""
        if reactor.running:
            logging.info('Stopping reactor')
            reactor.callFromThread(reactor.stop)