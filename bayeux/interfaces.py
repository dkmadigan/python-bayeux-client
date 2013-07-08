import zope.interface

class IMessengerService(zope.interface.Interface):
	"""Messenger Service Interface"""
	
	def start():
		"""Starts the messenger service"""

	def stop():
		"""Stops the messenger service"""

	def register(id, callback):
		"""Register a callback for a specific message id.

		Args:
			id: The id of the message to register for
			callback: The callback to register
		"""

	def deregister(id, callback):
		"""Deregister a callback for a specific message id.
		
		Args:
			id: The id of the message to deregister for
			callback: The callback to deregister
		"""