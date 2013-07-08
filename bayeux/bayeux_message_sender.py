import bayeux_constants
import logging

from twisted.internet import defer, reactor
from twisted.internet.defer import succeed
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements

#TODO Use join for string building or 'msg'.format formatting

class BayeuxMessageSender(object):
    """Responsible for sending messages to the bayeux server from the client.

    Attributes:
        agent: The twisted agent to use to send the data
        client_id: The client id to use when sending messages
        msg_id: A message id counter
        server: The bayeux server to send messages to
        receiver: The message receiver
    """
    def __init__(self, server, receiver):
        """Initialize the message sender.

        Args:
            server: The bayeux server to send messages to
            receiver: The message receiver to pass the responses to
        """
        self.agent = Agent(reactor, pool=HTTPConnectionPool(reactor))
        self.client_id = -1 #Will be set upon receipt of the handshake response
        self.msg_id = 0
        self.server = server
        self.receiver = receiver

    def connect(self, errback=None):
        """Sends a connect request message to the server

        Args:
            errback: Optional callback issued if there is an error 
                     during sending.
        """
        message = 'message={{"channel":"{0}","clientId":"{1}","id":"{2}",\
            "connectionType":"long-polling"}}'.format(
                bayeux_constants.CONNECT_CHANNEL,
                self.client_id,
                self.get_next_id())
        logging.debug('connect: %s' % message)
        self.send_message(message, errback)

    def disconnect(self, errback=None):
        """Sends a disconnect request message to the server.
    
        Args:
            errback: Optional callback issued if there is an error 
                during sending.
        """
        message = 'message={{"channel":"{0}","clientId":"{1}","id":"{2}"}}'.format(
            bayeux_constants.DISCONNECT_CHANNEL,
            self.client_id,
            self.get_next_id())        
        logging.debug('disconnect: %s' % message)
        self.send_message(message, errback)

    def get_next_id(self):
        """Increments and returns the next msg id to use.

        Returns:
            The next message id to use
        """
        self.msg_id += 1
        return self.msg_id

    def handshake(self, errback=None):
        """Sends a handshake request to the server.

        Args:
            errback: Optional callback issued if there is an error
                during sending.
        """
        message = '''message={{"channel":"{0}","id":"{1}",
            "supportedConnectionTypes":["callback-polling" "long-polling"],
            "version":"1.0","minimumVersion":"1.0"}}'''.format(
                bayeux_constants.HANDSHAKE_CHANNEL,
                self.get_next_id())
        logging.debug('handshake: %s' % message)
        self.send_message(message, errback)

    def send_message(self, message, errback=None):
        """Helper method to send a message.
        
        Args:
            message: The message to send
            errback: Optional callback issued if there is an error 
                during sending.
        """
        def do_send():
            d = self.agent.request('POST',
                self.server,
                Headers({'Content-Type': ['application/x-www-form-urlencoded'],
                    'Host': [self.server]}),
                BayeuxProducer(str(message)))

            def cb(response):
                response.deliverBody(self.receiver)
                return d
            
            def error(reason):
                logging.error('Error sending msg: %s' % reason)
                logging.error(reason.getErrorMessage())                
                #logging.debug(reason.value.reasons[0].printTraceback())
                if errback is not None:
                    errback(reason)
            
            d.addCallback(cb)
            d.addErrback(error)
        #Make sure that our send happens on the reactor thread
        reactor.callFromThread(do_send)

    def set_client_id(self, client_id):
        """Sets the client id to use for request messages that are sent.

        The client id is embedded in  all request messages sent by the 
        client to the server. This must be set prior to sending any request 
        other than a handshake request. The client id is returned by the server 
        in response to a handshake request.

        Args:
            client_id: The client id to use when sending requests to the server
        """
        self.client_id = client_id
    
    def subscribe(self, subscription, errback=None):
        """Sends a subscribe request to the server.
    
        Args:
            subscription: The subscription path (e.g. '/foo/bar')
            errback: Optional callback issued if there is an error 
                during sending
        """
        message = 'message={{"channel":"{0}","clientId":"{1}","id":"{2}",\
            "subscription":"{3}"}}'.format(
                bayeux_constants.SUBSCRIBE_CHANNEL,
                self.client_id, self.get_next_id(), subscription)
        logging.debug('subscribe: %s' % message)        
        self.send_message(message, errback)

    def unsubscribe(self, subscription, errback=None):
        """Sends an unsubscribe request to the server.
    
        Args:
            subscription: The subscription path (e.g. '/foo/bar')
            errback: Optional callback issued if there is an error 
                during sending
        """
        message = 'message={{"channel":"{0}","clientId":"{1}","id":"{2}",\
            "subscriptions":"{3}"}}'.format(
                bayeux_constants.UNSUBSCRIBE_CHANNEL,
                self.clientId, self.get_next_id(), subscriptions)        
        logging.debug('unsubscribe: %s' % message)
        self.send_message(message, errback)

class BayeuxProducer(object):
    implements(IBodyProducer)
    """Producer class used by the BayeuxMessageSender to write data.

    Attributes:
        body: The data to send
        length: The length of the data to send
    """
    def __init__(self, body):
        """Initialize the BayeuxProducer
        
        Args:
            body: The data to send
        """
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        """Writes the data.

        Args:
            consumer: The consumer to write to
        Returns:
        """
        consumer.write(self.body)
        return succeed(None)
    
    def pauseProducing(self):
        """No Op"""
        pass
        
    def stopProducing(self):
        """No Op"""
        pass
        