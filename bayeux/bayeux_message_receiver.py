import collections
import json
import logging

from twisted.internet.protocol import Protocol

class BayeuxMessageReceiver(Protocol):
    """Protocol class that handles incoming messages from the bayeux server.

    Attributes:
        listeners: Dictionary of listeners for different events
        buf: The current message buffer
    """
    def __init__(self):
        """Initialize the message receiver."""
        self.listeners = collections.defaultdict(set)
        self.buf = ''

    def register(self, event, callback):
        """Register a callback for a particular event

        Args:
            event: The event to register for (e.g. '/foo/bar')
            callback: The callback to trigger upon receipt of the message
        """
        self.listeners[event].add(callback)

    def deregister(self, event, callback):
        """Deregister a callback for a particular event.

        Args:
            event: The event to deregister for (e.g. 'foo/bar')
            callback: The callback to deregister

        Returns:
            The number of remaining listeners for the specified event
        """
        if event in self.listeners and callback in self.listeners[event]:
            self.listeners[event].remove(callback)

        return len(self.listeners[event])

    def dataReceived(self, data):
        """Called when data is received from the bayeux server.
    
        This is called by the Twisted protocol classes when 
        data is received from the server. This can potentially be called 
        multiple times per message so buffer up the data.

        Args:
            data: The data string that was sent from the bayeux server
        """
        logging.debug('dataReceived: %s' % data)
        self.buf += data

    def connectionLost(self, reason):
        """Called after an entire message is received.

        This is called by the Twisted protocol classes after all data has 
        been received. Parses the data that was received and issues callbacks 
        to listeners based on the content of the message.

        Args:
            reason: The reason why the connection was lost
        """        
        try:
            data = json.loads(self.buf)
            logging.debug('connectionLost: %s' % data)
            for msg in data:
                if 'channel' in msg:
                    self.notify(msg['channel'], msg)
        except ValueError as e:
            print 'Error parsing data: ', self.buf
            print e
        self.buf = ''

    def notify(self, event, data):
        """Notify listeners that data was received for the specified event.

        Args:
            event: The event
            data: The data
        """
        logging.debug('notify: %s' % event)
        for listener in self.listeners.get(event, []):
            listener(data)